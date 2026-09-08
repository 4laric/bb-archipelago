from __future__ import annotations

import hashlib
import json
import tempfile
import types
import unittest
from pathlib import Path

from bb_launcher.core import (
    SUPPRESSION_PATH, GameInstall, SeedCache, SeedIdentity, ValidationError, activate_build,
)
from bb_launcher.workflow import LauncherWorkflow, RunningProcess, _shad_game_argument

from tests.test_launcher_doctor import DoctorFixture, PLAN_HASH, RUNTIME, SUPPRESSED


class ConnectToRunningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = DoctorFixture(self.root)
        self.install = GameInstall.from_root(self.root / "game")
        identity = SeedIdentity(
            seed="AP_test", slot="Hunter", world_build="bloodborne-apworld-0.1.0",
            runtime_build=RUNTIME, shad_build="0.18.0",
            source_hashes={SUPPRESSION_PATH: hashlib.sha256(b"source").hexdigest()},
            options={
                "enemy_randomizer": False,
                "starting_weapons": None,
                "weapon_requirement_families": None,
                "shop_gate_permutation": None,
                "enemy_drop_assignments": None,
                "category8_awards": [],
            },
            suppression_plan_sha256=PLAN_HASH,
            suppression_binder_sha256=hashlib.sha256(SUPPRESSED).hexdigest(),
        )
        self.build = SeedCache(self.root / "cache").build(identity, self.fixture.binder)
        activate_build(self.install, self.build.path, process_is_running=lambda: False)
        self.launched = []

    def tearDown(self):
        self.temporary.cleanup()

    def process(self, *, executable=None, game=None, pid=41):
        executable = executable or self.fixture.shad_exe
        game = game or self.install.base
        return RunningProcess(pid, executable.resolve(), (str(executable), "--game", str(game)))

    def workflow(self, running, shads=None):
        def launch(specs):
            self.launched.extend(specs)
            return [types.SimpleNamespace(pid=731)]

        return LauncherWorkflow(
            self.root, process_launcher=launch, process_running=running,
            process_watcher=lambda *_args: None,
            shad_processes=(shads or (lambda: (self.process(),))),
        )

    def snapshot_overlay(self):
        return {
            path.relative_to(self.install.mods).as_posix(): path.read_bytes()
            for path in self.install.mods.rglob("*") if path.is_file()
        }

    def test_starts_only_the_client_for_the_verified_active_seed(self):
        workflow = self.workflow(
            lambda name: name.casefold() == self.fixture.shad_exe.name.casefold()
        )
        before = self.snapshot_overlay()
        result = workflow.connect_to_running(
            self.fixture.settings(), player_name="Hunter", research_captures=True
        )
        self.assertEqual([spec.name for spec in self.launched], ["AP client"])
        self.assertEqual(result.process_ids, (731,))
        self.assertEqual(result.cache_key, self.build.cache_key)
        self.assertTrue(result.reused)
        self.assertFalse(result.grants_bridge)
        self.assertEqual(before, self.snapshot_overlay())
        config = json.loads(result.client_config.read_text(encoding="utf-8"))
        self.assertTrue(config["pickup_notification_probe"])

    def assert_refused_without_mutation(self, running, message):
        before = self.snapshot_overlay()
        state = self.root / "state"
        self.launched.append("sentinel")
        with self.assertRaisesRegex(ValidationError, message):
            self.workflow(running).connect_to_running(
                self.fixture.settings(), player_name="Hunter"
            )
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")
        self.assertEqual(before, self.snapshot_overlay())
        self.assertFalse(state.exists())

    def test_refuses_when_no_launcher_owned_overlay_is_active(self):
        owner = self.install.mods / ".bb-ap-owner.json"
        owner.unlink()
        self.launched.append("sentinel")
        with self.assertRaisesRegex(Exception, "ownership manifest"):
            self.workflow(lambda name: name.casefold() == "shadps4.exe").connect_to_running(
                self.fixture.settings(), player_name="Hunter"
            )
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")
        self.assertFalse((self.root / "state").exists())

    def test_a_tampered_active_overlay_is_refused_with_the_rebuild_hint(self):
        """bb-archipelago#408: launch time guards, it never heals.

        ``activate_build`` rebuilds this directory and so may repair it.  This
        check runs against the overlay shadPS4 has *already loaded*, so it
        stays strict -- and names the one action that fixes it.
        """
        decoy = self.install.root / "CUSA03173-mods.bb-ap-foreign-00000000-000000"
        decoy.mkdir(parents=True)
        tampered = self.install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        tampered.write_bytes(b"A MOD OVERWROTE THIS")
        self.launched.append("sentinel")
        with self.assertRaises(Exception) as caught:
            self.workflow(
                lambda name: name.casefold() == self.fixture.shad_exe.name.casefold()
            ).connect_to_running(self.fixture.settings(), player_name="Hunter")
        message = str(caught.exception)
        self.assertIn("owned overlay file size changed", message)
        self.assertIn("Run Randomize & Launch again to rebuild the overlay.", message)
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")
        # Refusing means refusing: nothing was moved aside here.
        self.assertEqual(tampered.read_bytes(), b"A MOD OVERWROTE THIS")
        self.assertEqual(list(self.install.root.glob("*bb-ap-foreign-*")), [decoy])

    def test_refuses_when_shadps4_is_not_running(self):
        before = self.snapshot_overlay()
        self.launched.append("sentinel")
        with self.assertRaisesRegex(ValidationError, "already be running"):
            self.workflow(lambda _name: False, lambda: ()).connect_to_running(
                self.fixture.settings(), player_name="Hunter"
            )
        self.assertEqual(before, self.snapshot_overlay())
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")

    def test_refuses_a_duplicate_client(self):
        self.assert_refused_without_mutation(
            lambda name: name.casefold() in {"shadps4.exe", "bb-ap-client.exe"},
            "AP client is already running",
        )

    def test_refuses_a_different_shadps4_executable(self):
        other = self.root / "other" / "shadPS4.exe"
        other.parent.mkdir()
        other.write_bytes(b"shad")
        self.launched.append("sentinel")
        with self.assertRaisesRegex(ValidationError, "running shadPS4 executable"):
            self.workflow(
                lambda name: False,
                lambda: (self.process(executable=other),),
            ).connect_to_running(self.fixture.settings(), player_name="Hunter")
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")

    def test_refuses_a_shadps4_running_the_wrong_game(self):
        wrong = self.root / "other-game" / "CUSA03173"
        self.launched.append("sentinel")
        with self.assertRaisesRegex(ValidationError, "running shadPS4 game"):
            self.workflow(
                lambda name: False,
                lambda: (self.process(game=wrong),),
            ).connect_to_running(self.fixture.settings(), player_name="Hunter")
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")

    def test_refuses_multiple_shadps4_processes(self):
        self.launched.append("sentinel")
        with self.assertRaisesRegex(ValidationError, "2 shadPS4 processes"):
            self.workflow(
                lambda name: False,
                lambda: (self.process(pid=1), self.process(pid=2)),
            ).connect_to_running(self.fixture.settings(), player_name="Hunter")
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")

    def test_refuses_when_verified_process_disappears_before_spawn(self):
        calls = iter(((self.process(),), ()))
        self.launched.append("sentinel")
        with self.assertRaisesRegex(ValidationError, "stopped before"):
            self.workflow(lambda _name: False, lambda: next(calls)).connect_to_running(
                self.fixture.settings(), player_name="Hunter"
            )
        self.assertEqual(["sentinel"], self.launched, "witness: no launch spec was appended")

    def test_game_argument_normalizes_eboot_and_ignores_later_option_values(self):
        eboot = self.install.base / "eboot.bin"
        self.assertEqual(
            _shad_game_argument((str(self.fixture.shad_exe), "-g", str(eboot))),
            self.install.base,
        )
        self.assertEqual(
            _shad_game_argument(
                (str(self.fixture.shad_exe), str(eboot), "-f", "false")
            ),
            self.install.base,
        )

    def test_category8_only_legacy_request_reconnects_with_canonical_manifest(self):
        from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

        award = CATEGORY8_AWARDS[1]
        canonical = {
            name: getattr(award, name)
            for name in (
                "item_key", "token_goods_id", "item_lot_id", "gemgen_id",
                "ack_flag", "source_lot_id",
            )
        }
        request = json.loads(self.fixture.request_path.read_text(encoding="utf-8"))
        request["category8_awards"] = {
            "12250001": {**canonical, "item_lot_id": 98_000_001}
        }
        self.fixture.request_path.write_text(json.dumps(request), encoding="utf-8")
        identity = SeedIdentity(
            seed="AP_test", slot="Hunter", world_build="bloodborne-apworld-0.1.0",
            runtime_build=RUNTIME, shad_build="0.18.0",
            source_hashes={SUPPRESSION_PATH: hashlib.sha256(b"source-category8").hexdigest()},
            options={
                "enemy_randomizer": False, "starting_weapons": None,
                "weapon_requirement_families": None, "shop_gate_permutation": None,
                "enemy_drop_assignments": None, "category8_awards": [canonical],
            },
            suppression_plan_sha256=PLAN_HASH,
            suppression_binder_sha256=hashlib.sha256(SUPPRESSED).hexdigest(),
        )
        build = SeedCache(self.root / "cache").build(identity, self.fixture.binder)
        activate_build(self.install, build.path, process_is_running=lambda: False)
        seed_manifest = self.root / "state" / "seed-manifests" / f"{build.cache_key}.json"
        seed_manifest.parent.mkdir(parents=True)
        seed_manifest.write_text(self.fixture.manifest_path.read_text(encoding="utf-8"), encoding="utf-8")

        result = self.workflow(lambda _name: False).connect_to_running(
            self.fixture.settings(), player_name="Hunter"
        )
        config = json.loads(result.client_config.read_text(encoding="utf-8"))
        self.assertEqual(config["suppression_manifest"], str(seed_manifest.resolve()))
        self.assertEqual([spec.name for spec in self.launched], ["AP client"])

    def test_refuses_when_selected_seed_does_not_match_active_overlay(self):
        request = json.loads(self.fixture.request_path.read_text(encoding="utf-8"))
        request["seed_name"] = "another-seed"
        self.fixture.request_path.write_text(json.dumps(request), encoding="utf-8")
        self.assert_refused_without_mutation(
            lambda name: name.casefold() == "shadps4.exe", "selected seed/options/runtime"
        )


if __name__ == "__main__":
    unittest.main()
