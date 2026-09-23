"""Copy-route policy, fork provenance, journal recovery, locks, supervisor."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from bb_launcher.integrated import fork_identity
from bb_launcher.integrated.journal import (
    append_entry,
    decide_recovery,
    plan_activation,
    read_journal,
)
from bb_launcher.integrated.policy import (
    require_copy_activation,
    require_fork_provenance,
)
from bb_launcher.integrated.protocol import ProtocolError
from bb_launcher.integrated.sessions import (
    install_lock,
    load_remembered,
    remember_session,
)
from bb_launcher.integrated.supervisor import (
    SupervisorSession,
    claim_client,
    existing_session_for_play,
    reattach_session,
    register_session,
    release_client,
)
from bb_launcher.core import ValidationError


@dataclass
class FakeFile:
    path: str
    installation: str


class CopyPolicyTests(unittest.TestCase):
    def test_all_copy_passes(self) -> None:
        require_copy_activation(
            [FakeFile("dvdroot_ps4/a", "copy"), FakeFile("dvdroot_ps4/b", "copy")],
            stage="arming",
        )

    def test_symlink_is_refused_before_arming(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            require_copy_activation(
                [FakeFile("dvdroot_ps4/a", "copy"), FakeFile("dvdroot_ps4/b", "symlink")],
                stage="arming",
            )
        self.assertEqual(caught.exception.code, "activation-route-refused")
        self.assertIn("dvdroot_ps4/b", caught.exception.detail)

    def test_mixed_is_refused_before_connection(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            require_copy_activation([FakeFile("dvdroot_ps4/a", "mixed")], stage="connection")
        self.assertEqual(caught.exception.code, "activation-route-refused")


class ForkProvenanceTests(unittest.TestCase):
    def test_arbitrary_fork_is_never_accepted(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            require_fork_provenance("0" * 40, hashlib.sha256(b"x").hexdigest())
        self.assertEqual(caught.exception.code, "unsupported-build")

    def test_listed_build_is_accepted(self) -> None:
        commit, exe = "a" * 40, hashlib.sha256(b"fork-build").hexdigest()
        with patch.object(fork_identity, "SUPPORTED_FORK_BUILDS", frozenset({(commit, exe)})):
            require_fork_provenance(commit, exe)  # must not raise

    def test_malformed_pin_is_refused_not_loosened(self) -> None:
        with self.assertRaises(ProtocolError):
            require_fork_provenance("not-a-commit", "not-a-digest")


class JournalRecoveryTests(unittest.TestCase):
    def _plan_detail(self) -> dict:
        plan = plan_activation(
            play_id="play_x", package_name="Archipelago-A-1", prior_package=None,
            owned_paths=[{"relative": "a", "before": None, "after": "H1", "size": 10},
                         {"relative": "b", "before": "H0", "after": "H2", "size": 10}],
            third_party_collisions=[], backup_free_bytes=1024,
        )
        return plan.as_dict()

    def test_plan_rejects_destructive_conflict_without_reversible_disable(self) -> None:
        with self.assertRaises(ValidationError):
            plan_activation(
                play_id="play_x", package_name="P", prior_package=None,
                owned_paths=[{"relative": "a", "before": None, "after": "H1"}],
                third_party_collisions=[{"mod": "Other", "path": "a"}],
                backup_free_bytes=1024,
            )

    def test_plan_rejects_insufficient_backup_space(self) -> None:
        with self.assertRaises(ValidationError):
            plan_activation(
                play_id="play_x", package_name="P", prior_package=None,
                owned_paths=[{"relative": "a", "before": None, "after": "H1", "size": 10**9}],
                third_party_collisions=[], backup_free_bytes=10,
            )

    def test_journal_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            game = str(Path(state) / "game")
            append_entry(state, game, "plan", "play_x", self._plan_detail())
            entries = read_journal(state, game)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["kind"], "plan")

    def test_interrupted_tail_with_clean_state_resumes(self) -> None:
        decision = decide_recovery(
            [{"kind": "plan", "detail": self._plan_detail()}], {"a": None, "b": "H0"})
        self.assertEqual(decision.action, "resume")

    def test_committed_files_restore_in_reverse_order(self) -> None:
        entries = [{"kind": "plan", "detail": self._plan_detail()},
                   {"kind": "commit", "detail": {"relative": "a"}},
                   {"kind": "commit", "detail": {"relative": "b"}}]
        decision = decide_recovery(entries, {"a": "H1", "b": "H0"})
        self.assertEqual(decision.action, "restore-owned")
        self.assertEqual(decision.restored, ("b", "a"))

    def test_user_change_since_interruption_is_reported_never_overwritten(self) -> None:
        entries = [{"kind": "plan", "detail": self._plan_detail()},
                   {"kind": "commit", "detail": {"relative": "a"}}]
        decision = decide_recovery(entries, {"a": "USER-EDIT", "b": "H0"})
        self.assertEqual(decision.action, "report-conflict")
        self.assertIn("a", decision.conflicts)


class CopyPolicyAgainstRealVerificationTests(unittest.TestCase):
    """The copy gate runs on real verifier output, not stub shapes."""

    def setUp(self) -> None:
        import shutil
        from datetime import datetime, timezone

        from bb_launcher.core import (
            SERIAL,
            SeedCache,
            SeedIdentity,
            sha256_file,
        )
        from bb_launcher.external import (
            ACTIVE_MODS_DIR_NAME,
            ExternalNamespace,
            LIVE_ACCEPTANCE_CANDIDATES,
            BBLauncherBuildPin,
            export_external_package,
            verify_external_activation,
        )

        self._sha256_file = sha256_file
        self._verify = verify_external_activation
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        game = self.root / "game"
        base = game / SERIAL
        patch_dir = game / f"{SERIAL}-patch"
        mods = game / f"{SERIAL}-mods"
        for directory in (base, patch_dir, mods):
            directory.mkdir(parents=True)
        from bb_launcher.core import GameInstall

        self.install = GameInstall(game, base, patch_dir, mods)
        self.mods_root = self.root / "bblauncher" / "Mods"
        self.mods_root.mkdir(parents=True)
        self.state_root = self.root / "state"
        commit = next(iter(LIVE_ACCEPTANCE_CANDIDATES))
        exe = next(iter(LIVE_ACCEPTANCE_CANDIDATES[commit]))
        pin = BBLauncherBuildPin("local", commit, exe, live_acceptance_candidate=True)

        def make_identity(seed: str) -> SeedIdentity:
            return SeedIdentity(
                seed=seed, slot="Hunter", world_build="w", runtime_build="r",
                shad_build="s",
                source_hashes={"dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx":
                               hashlib.sha256(b"v").hexdigest()},
                suppression_plan_sha256=hashlib.sha256(b"p").hexdigest(),
                suppression_binder_sha256=hashlib.sha256(b"b").hexdigest(),
            )

        from bb_launcher.core import SUPPRESSION_PATH

        identity = make_identity("policy-seed")
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "gameparam.parambnd.dcx").write_bytes(b"binder")
        (inputs / "m24.emevd.dcx").write_bytes(b"event")
        build = SeedCache(self.root / "cache").build(
            identity, inputs / "gameparam.parambnd.dcx",
            cathedral_event=inputs / "m24.emevd.dcx")
        self.exported = export_external_package(
            build, identity, mods_root=self.mods_root, state_root=self.state_root,
            install=self.install, bblauncher=pin, client_version="client-test",
            namespace=ExternalNamespace.for_identity(identity),
            created_at=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
            allow_live_acceptance_candidate=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _activate(self, *, symlink: bool = False):
        from pathlib import PurePosixPath

        from bb_launcher.external import ACTIVE_MODS_DIR_NAME

        active_root = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME)
        active_root.mkdir()
        active = active_root / self.exported.receipt.package_name
        (self.exported.package_path / "dvdroot_ps4").rename(active)
        self.exported.package_path.rmdir()
        for record in self.exported.receipt.files:
            stripped = record.path[len("dvdroot_ps4/"):]
            source = active.joinpath(*PurePosixPath(stripped).parts)
            output = self.install.mods.joinpath(*PurePosixPath(record.path).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            if symlink:
                output.write_bytes(source.read_bytes())
                output.unlink()
                try:
                    output.symlink_to(source)
                except OSError as exc:
                    self.skipTest(f"file symlinks are unavailable: {exc}")
            else:
                output.write_bytes(source.read_bytes())
        return active

    def test_real_copy_activation_passes_the_gate(self) -> None:
        self._activate(symlink=False)
        verified = self._verify(
            self.exported.receipt, install=self.install, mods_root=self.mods_root,
            allow_live_acceptance_candidate=True)
        self.assertTrue(verified.files, "verification must cover at least one file")
        for item in verified.files:
            self.assertEqual(item.installation, "copy")
        require_copy_activation(verified.files, stage="arming")  # must not raise

    def test_real_symlink_activation_is_refused(self) -> None:
        self._activate(symlink=True)
        verified = self._verify(
            self.exported.receipt, install=self.install, mods_root=self.mods_root,
            allow_live_acceptance_candidate=True)
        self.assertTrue(any(item.installation == "symlink" for item in verified.files))
        with self.assertRaises(ProtocolError) as caught:
            require_copy_activation(verified.files, stage="connection")
        self.assertEqual(caught.exception.code, "activation-route-refused")
    def test_second_holder_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            game = Path(state) / "game"
            with install_lock(state, game, owner="ui", timeout_s=5):
                with self.assertRaises(ValidationError):
                    with install_lock(state, game, owner="backend", timeout_s=0.1):
                        pass

    def test_lock_releases_on_exit(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            game = Path(state) / "game"
            with install_lock(state, game, owner="ui", timeout_s=5):
                pass
            with install_lock(state, game, owner="backend", timeout_s=5):
                pass


class RememberedSessionTests(unittest.TestCase):
    def test_server_edit_cannot_silently_change_seed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            remember_session(state, game_root="G", seed="seed-A", slot="Alaric",
                             server="archipelago.gg:1", play_id="play_x")
            remembered = load_remembered(state)
            assert remembered is not None
            self.assertEqual(remembered["server_for_seed"], "seed-A")
            self.assertEqual(remembered["server"], "archipelago.gg:1")


class SupervisorTests(unittest.TestCase):
    def _session(self) -> SupervisorSession:
        return SupervisorSession(
            session_id="session_abc", play_id="play_" + "1" * 32, arm_id="arm_" + "2" * 32,
            executable="C:\\games\\shadPS4.exe", executable_sha256=hashlib.sha256(b"e").hexdigest(),
            pid=4242, creation_time=987654, owner="supervisor", client_pid=4243,
            created_at=1.0,
        )

    def test_gui_qprocess_may_not_own_a_session(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            # The GUI-owned command backend must never own the client; only
            # the persistent supervisor may.
            session = SupervisorSession(
                session_id="s2", play_id="play_" + "3" * 32, arm_id="arm_" + "4" * 32,
                executable="e", executable_sha256=hashlib.sha256(b"e").hexdigest(),
                pid=1, creation_time=None, owner="gui-command", client_pid=None,
                created_at=0.0)
            with self.assertRaises(ValidationError):
                register_session(state, session)

    def test_reattach_validates_everything_not_pid_alone(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            register_session(state, self._session())
            good = dict(executable="C:\\games\\shadPS4.exe",
                        executable_sha256=hashlib.sha256(b"e").hexdigest(),
                        pid=4242, creation_time=987654, process_alive=True)
            reattach_session(state, "session_abc", **good)
            # Reused PID, different birth identity -> fail closed.
            bad = dict(good, creation_time=111111)
            with self.assertRaises(ProtocolError) as caught:
                reattach_session(state, "session_abc", **bad)
            self.assertEqual(caught.exception.code, "stale-session")
            # Dead process -> fail closed.
            with self.assertRaises(ProtocolError):
                reattach_session(state, "session_abc", **dict(good, process_alive=False))

    def test_duplicate_client_claim_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            register_session(state, self._session())
            with self.assertRaises(ProtocolError) as caught:
                claim_client(state, "session_abc", 9999)
            self.assertEqual(caught.exception.code, "duplicate-client")
            release_client(state, "session_abc")
            claim_client(state, "session_abc", 9999)  # now free

    def test_lookup_by_play(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            register_session(state, self._session())
            found = existing_session_for_play(state, "play_" + "1" * 32)
            self.assertIsNotNone(found)


if __name__ == "__main__":
    unittest.main()
