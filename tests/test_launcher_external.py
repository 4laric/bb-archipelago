from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from bb_launcher.core import (
    APP_VERSION,
    CATHEDRAL_EVENT_PATH,
    SEED_MANIFEST_NAME,
    SERIAL,
    SUPPRESSION_PATH,
    GameInstall,
    SeedCache,
    SeedIdentity,
    ValidationError,
    sha256_file,
)
from bb_launcher.external import (
    ACTIVE_MODS_DIR_NAME,
    ExternalPackageExists,
    BBLauncherBuildPin,
    EXTERNAL_RECEIPT_FORMAT,
    ExternalNamespace,
    LIVE_ACCEPTANCE_CANDIDATES,
    export_external_package,
    load_external_receipt,
    verify_external_activation,
)


CANDIDATE_COMMIT = next(iter(LIVE_ACCEPTANCE_CANDIDATES))
CANDIDATE_EXE = next(iter(LIVE_ACCEPTANCE_CANDIDATES[CANDIDATE_COMMIT]))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(seed: str, slot: str = "Hunter / One") -> SeedIdentity:
    return SeedIdentity(
        seed=seed,
        slot=slot,
        world_build="bloodborne-apworld-test",
        runtime_build="bloodborne-runtime-test",
        shad_build="shad-test",
        source_hashes={SUPPRESSION_PATH: digest(b"vanilla")},
        options={"enemy_randomizer": False},
        suppression_plan_sha256=digest(b"plan"),
        suppression_binder_sha256=digest(b"binder"),
    )


class ExternalArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        game = self.root / "game"
        base = game / SERIAL
        patch_dir = game / f"{SERIAL}-patch"
        mods = game / f"{SERIAL}-mods"
        for directory in (base, patch_dir, mods):
            directory.mkdir(parents=True)
        self.install = GameInstall(game, base, patch_dir, mods)
        self.mods_root = self.root / "bblauncher" / "Mods"
        self.mods_root.mkdir(parents=True)
        self.state_root = self.root / "state"
        self.pin = BBLauncherBuildPin(
            "local acceptance build", CANDIDATE_COMMIT, CANDIDATE_EXE,
            live_acceptance_candidate=True,
        )
        inputs = self.root / "inputs"
        inputs.mkdir()
        binder = inputs / "gameparam.parambnd.dcx"
        binder.write_bytes(b"generated-binder")
        event = inputs / "m24.emevd.dcx"
        event.write_bytes(b"generated-event")
        self.built_identity = identity("cache-origin")
        self.build = SeedCache(self.root / "cache").build(
            self.built_identity, binder, cathedral_event=event
        )
        # The cache deliberately excludes seed and slot.  This selected
        # identity must be the authority stored in the external receipt.
        self.selected_identity = identity("selected-seed")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def export(self):
        return export_external_package(
            self.build,
            self.selected_identity,
            mods_root=self.mods_root,
            state_root=self.state_root,
            install=self.install,
            bblauncher=self.pin,
            client_version="client-test",
            namespace=ExternalNamespace.for_identity(self.selected_identity),
            created_at=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
            allow_live_acceptance_candidate=True,
        )

    def activate_copy(self, exported):
        active_root = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME)
        active_root.mkdir()
        active = active_root / exported.receipt.package_name
        wrapper = exported.package_path / "dvdroot_ps4"
        wrapper.rename(active)
        exported.package_path.rmdir()
        for record in exported.receipt.files:
            stripped = record.path[len("dvdroot_ps4/"):]
            source = active.joinpath(*PurePosixPath(stripped).parts)
            output = self.install.mods.joinpath(*PurePosixPath(record.path).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(source.read_bytes())
        return active

    def activate_symlink(self, exported):
        active = self.activate_copy(exported)
        for record in exported.receipt.files:
            installed = self.install.mods.joinpath(*PurePosixPath(record.path).parts)
            installed.unlink()
            source = active.joinpath(*PurePosixPath(record.path[len("dvdroot_ps4/"):]).parts)
            try:
                installed.symlink_to(source)
            except OSError as exc:
                self.skipTest(f"file symlinks are unavailable: {exc}")
        return active

    def test_export_is_data_only_atomic_and_receipt_uses_selected_identity(self):
        before = self.snapshot_game()
        exported = self.export()
        self.assertEqual(
            sorted(path.relative_to(exported.package_path).as_posix()
                   for path in exported.package_path.rglob("*") if path.is_file()),
            sorted(record.path for record in exported.receipt.files),
        )
        self.assertFalse((exported.package_path / SEED_MANIFEST_NAME).exists())
        self.assertEqual(exported.receipt.identity.seed, "selected-seed")
        self.assertEqual(exported.receipt.cache_key, self.built_identity.cache_key)
        self.assertEqual(exported.receipt.namespace.ledger_key,
                         ExternalNamespace.for_identity(self.selected_identity).ledger_key)
        self.assertEqual(self.snapshot_game(), before)
        self.assertEqual(list(self.mods_root.iterdir()), [exported.package_path])
        loaded = load_external_receipt(
            exported.receipt_path, allow_live_acceptance_candidate=True
        )
        self.assertEqual(loaded, exported.receipt)
        raw = json.loads(exported.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["format"], EXTERNAL_RECEIPT_FORMAT)
        self.assertEqual(raw["source_hashes"], dict(self.selected_identity.source_hashes))
        self.assertEqual(raw["suppression"]["plan_sha256"],
                         self.selected_identity.suppression_plan_sha256)
        self.assertEqual(raw["enemizer_identity"], None)

    def snapshot_game(self):
        return {
            path.relative_to(self.install.root).as_posix(): sha256_file(path)
            for path in self.install.root.rglob("*") if path.is_file()
        }

    def test_build_policy_fails_closed_and_candidate_requires_two_explicit_marks(self):
        unmarked = BBLauncherBuildPin("local", CANDIDATE_COMMIT, CANDIDATE_EXE)
        with self.assertRaisesRegex(ValidationError, "not supported"):
            export_external_package(
                self.build, self.selected_identity, mods_root=self.mods_root,
                state_root=self.state_root, install=self.install, bblauncher=unmarked,
                client_version="client", allow_live_acceptance_candidate=True,
            )
        with self.assertRaisesRegex(ValidationError, "not supported"):
            export_external_package(
                self.build, self.selected_identity, mods_root=self.mods_root,
                state_root=self.state_root, install=self.install, bblauncher=self.pin,
                client_version="client",
            )

    def test_export_refuses_existing_target_and_does_not_mutate_it(self):
        exported = self.export()
        before = self.tree_bytes(exported.package_path)
        with self.assertRaisesRegex(ValidationError, "already exists"):
            self.export()
        self.assertEqual(self.tree_bytes(exported.package_path), before)

    def test_export_collision_is_typed_so_the_ui_can_offer_replacement(self):
        exported = self.export()
        with self.assertRaises(ExternalPackageExists) as caught:
            self.export()
        self.assertEqual(caught.exception.path, exported.package_path)
        self.assertIn("already exists", str(caught.exception))

    def test_replace_existing_swaps_the_inactive_package_and_writes_a_new_receipt(self):
        first = self.export()
        (first.package_path / "stale-marker").write_bytes(b"old")
        replaced = export_external_package(
            self.build, self.selected_identity, mods_root=self.mods_root,
            state_root=self.state_root, install=self.install, bblauncher=self.pin,
            client_version="client-test",
            namespace=ExternalNamespace.for_identity(self.selected_identity),
            created_at=datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc),
            allow_live_acceptance_candidate=True, replace_existing=True,
        )
        self.assertEqual(replaced.package_path, first.package_path)
        self.assertFalse((replaced.package_path / "stale-marker").exists())
        self.assertNotEqual(replaced.receipt_path, first.receipt_path)
        self.assertTrue(first.receipt_path.is_file(), "the earlier receipt is immutable history")
        self.assertEqual(
            self.tree_bytes(replaced.package_path),
            {path: digest for path, digest in self.tree_bytes(first.package_path).items()},
        )

    def test_replace_existing_never_touches_an_activated_or_foreign_entry(self):
        package_name = f"Archipelago-Hunter-One-{self.build.cache_key[:12]}"
        active_root = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME)
        active_root.mkdir()
        activated = active_root / package_name
        activated.mkdir()
        (activated / "keep").write_bytes(b"live")
        with self.assertRaisesRegex(ValidationError, "active Mods directory"):
            export_external_package(
                self.build, self.selected_identity, mods_root=self.mods_root,
                state_root=self.state_root, install=self.install, bblauncher=self.pin,
                client_version="client-test", allow_live_acceptance_candidate=True,
                replace_existing=True,
            )
        self.assertEqual((activated / "keep").read_bytes(), b"live")
        shutil.rmtree(active_root)
        # A plain file squatting on the name is not a companion package.
        squatter = self.mods_root / package_name
        squatter.write_bytes(b"not a package")
        with self.assertRaisesRegex(ValidationError, "not a replaceable companion package"):
            export_external_package(
                self.build, self.selected_identity, mods_root=self.mods_root,
                state_root=self.state_root, install=self.install, bblauncher=self.pin,
                client_version="client-test", allow_live_acceptance_candidate=True,
                replace_existing=True,
            )
        self.assertEqual(squatter.read_bytes(), b"not a package")

    def test_export_refuses_case_variant_inactive_and_active_targets(self):
        package_name = f"Archipelago-Hunter-One-{self.build.cache_key[:12]}"
        variant = self.mods_root / package_name.upper()
        variant.mkdir()
        with self.assertRaisesRegex(ValidationError, "already exists"):
            self.export()
        variant.rmdir()
        active_root = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME)
        active_root.mkdir()
        (active_root / package_name.upper()).mkdir()
        with self.assertRaisesRegex(ValidationError, "active Mods directory"):
            self.export()

    def test_active_package_directory_cannot_be_selected_as_export_root(self):
        active_root = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME)
        active_root.mkdir()
        nested = active_root / "Some-Package" / "nested-mods"
        nested.mkdir(parents=True)
        for selected in (active_root, nested):
            with self.subTest(selected=selected):
                before = self.tree_entries(active_root)
                with self.assertRaisesRegex(ValidationError, "active package directory"):
                    export_external_package(
                        self.build, self.selected_identity, mods_root=selected,
                        state_root=self.state_root, install=self.install, bblauncher=self.pin,
                        client_version="client", allow_live_acceptance_candidate=True,
                    )
                self.assertEqual(self.tree_entries(active_root), before)

    def test_export_refuses_state_or_cache_inside_bblauncher_managed_root(self):
        managed_root = self.mods_root.parent
        active_root = managed_root / ACTIVE_MODS_DIR_NAME
        active_root.mkdir()
        for state in (active_root, active_root / "package-state"):
            with self.subTest(state=state):
                before = self.tree_entries(managed_root)
                with self.assertRaisesRegex(ValidationError, "BBLauncher managed root"):
                    export_external_package(
                        self.build, self.selected_identity, mods_root=self.mods_root,
                        state_root=state, install=self.install, bblauncher=self.pin,
                        client_version="client", allow_live_acceptance_candidate=True,
                    )
                self.assertEqual(self.tree_entries(managed_root), before)

        cached = active_root / "cache" / self.build.cache_key
        shutil.copytree(self.build.path, cached)
        active_build = SeedCache(active_root / "cache").verify(
            cached, expected_key=self.build.cache_key
        )
        before = self.tree_entries(managed_root)
        with self.assertRaisesRegex(ValidationError, "verified seed cache"):
            export_external_package(
                active_build, self.selected_identity, mods_root=self.mods_root,
                state_root=self.state_root, install=self.install, bblauncher=self.pin,
                client_version="client", allow_live_acceptance_candidate=True,
            )
        self.assertEqual(self.tree_entries(managed_root), before)

    def tree_bytes(self, root: Path):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()
        }

    def tree_entries(self, root: Path):
        return tuple(sorted(
            (path.relative_to(root).as_posix(), "directory" if path.is_dir()
             else digest(path.read_bytes()))
            for path in root.rglob("*")
        ))

    def test_export_refuses_write_root_overlap_with_game_or_state(self):
        for mods, state in (
            (self.install.root, self.state_root),
            (self.mods_root, self.mods_root / "state"),
            (self.mods_root, self.build.path),
        ):
            with self.subTest(mods=mods, state=state):
                with self.assertRaisesRegex(ValidationError, "overlaps"):
                    export_external_package(
                        self.build, self.selected_identity, mods_root=mods,
                        state_root=state, install=self.install, bblauncher=self.pin,
                        client_version="client", allow_live_acceptance_candidate=True,
                    )

    def test_export_refuses_reparse_alias_for_protected_game_overlay(self):
        from bb_launcher import external
        original = external._is_reparse

        def mark_overlay(path):
            return Path(path) == self.install.mods or original(path)

        with patch("bb_launcher.external._is_reparse", side_effect=mark_overlay):
            with self.assertRaisesRegex(ValidationError, "active game overlay crosses"):
                self.export()

    def test_default_state_layout_allows_cache_as_a_state_root_sibling(self):
        default_state = self.root / "default-state"
        cache = SeedCache(default_state / "seeds")
        binder = self.root / "default-binder.dcx"
        binder.write_bytes(b"default-layout")
        built = cache.build(identity("built-default"), binder)
        selected = identity("selected-default")
        exported = export_external_package(
            built, selected, mods_root=self.mods_root, state_root=default_state,
            install=self.install, bblauncher=self.pin, client_version="client",
            allow_live_acceptance_candidate=True,
        )
        self.assertTrue(exported.receipt_path.is_file())
        self.assertTrue(built.path.is_dir())

    def test_interrupted_copy_cleans_staging_and_publishes_nothing(self):
        existing = self.mods_root / "Existing-Cosmetic-Mod"
        existing.mkdir()
        original = __import__("bb_launcher.external", fromlist=["shutil"]).shutil.copyfile
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected copy failure")
            return original(source, destination)

        with patch("bb_launcher.external.shutil.copyfile", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected"):
                self.export()
        self.assertEqual(list(self.mods_root.iterdir()), [existing])
        self.assertFalse((self.state_root / "external").exists())

    def test_receipt_write_failure_never_publishes_package(self):
        existing = self.mods_root / "Existing-Cosmetic-Mod"
        existing.mkdir()
        with patch("bb_launcher.external._write_immutable_json",
                   side_effect=OSError("injected receipt failure")):
            with self.assertRaisesRegex(OSError, "receipt failure"):
                self.export()
        self.assertEqual(list(self.mods_root.iterdir()), [existing])

    def test_copy_activation_verifies_all_files_and_exposes_effective_binder(self):
        exported = self.export()
        active = self.activate_copy(exported)
        unrelated = active.parent / "Blue-Hat"
        (unrelated / "sfx").mkdir(parents=True)
        (unrelated / "sfx" / "hat.bin").write_bytes(b"hat")
        verified = verify_external_activation(
            exported.receipt_path, install=self.install, mods_root=self.mods_root,
            observed_at=datetime(2026, 9, 22, 12, 1, tzinfo=timezone.utc),
            allow_live_acceptance_candidate=True,
        )
        self.assertEqual({item.installation for item in verified.files}, {"copy"})
        self.assertEqual(verified.installed_gameparam.read_bytes(), b"generated-binder")
        self.assertEqual(verified.active_package, active)
        self.assertEqual(len(verified.activation_fingerprint), 64)

    def test_fingerprint_captures_activation_generation_metadata(self):
        exported = self.export()
        active = self.activate_copy(exported)
        first = verify_external_activation(
            exported.receipt, install=self.install, mods_root=self.mods_root,
            allow_live_acceptance_candidate=True,
        )
        current = active.stat().st_mtime_ns
        os.utime(active, ns=(current + 1_000_000_000, current + 1_000_000_000))
        second = verify_external_activation(
            exported.receipt, install=self.install, mods_root=self.mods_root,
            allow_live_acceptance_candidate=True,
        )
        self.assertNotEqual(first.activation_fingerprint, second.activation_fingerprint)

    def test_standalone_owner_manifest_is_never_adopted(self):
        exported = self.export()
        self.activate_copy(exported)
        (self.install.mods / ".bb-ap-owner.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "standalone"):
            verify_external_activation(
                exported.receipt, install=self.install, mods_root=self.mods_root,
                allow_live_acceptance_candidate=True,
            )

    def test_symlink_activation_requires_exact_per_file_active_source(self):
        exported = self.export()
        active = self.activate_symlink(exported)
        verified = verify_external_activation(
            exported.receipt, install=self.install, mods_root=self.mods_root,
            allow_live_acceptance_candidate=True,
        )
        self.assertEqual({item.installation for item in verified.files}, {"symlink"})
        self.assertEqual(len(verified.files), len(exported.receipt.files))
        for item in verified.files:
            with self.subTest(path=item.path):
                self.assertTrue(item.active_source.is_relative_to(active))

    def test_wrong_dangling_and_cyclic_links_are_rejected(self):
        for mode in ("escaping", "dangling", "cyclic"):
            with self.subTest(mode=mode):
                self.reset_activation()
                exported = self.export()
                active = self.activate_symlink(exported)
                record = exported.receipt.files[0]
                installed = self.install.mods.joinpath(*PurePosixPath(record.path).parts)
                installed.unlink()
                if mode == "escaping":
                    outside = self.root / "outside.bin"
                    outside.write_bytes(active.joinpath(*PurePosixPath(
                        record.path[len("dvdroot_ps4/"):]).parts).read_bytes())
                    installed.symlink_to(outside)
                    pattern = "escapes"
                elif mode == "dangling":
                    installed.symlink_to(self.root / "absent.bin")
                    pattern = "dangling or cyclic"
                else:
                    installed.symlink_to(installed)
                    pattern = "dangling or cyclic"
                with self.assertRaisesRegex(ValidationError, pattern):
                    verify_external_activation(
                        exported.receipt, install=self.install, mods_root=self.mods_root,
                        allow_live_acceptance_candidate=True,
                    )

    def reset_activation(self):
        import shutil
        for path in (self.install.mods, self.mods_root,
                     self.mods_root.with_name(ACTIVE_MODS_DIR_NAME), self.state_root):
            if path.exists():
                shutil.rmtree(path)
        self.install.mods.mkdir(parents=True)
        self.mods_root.mkdir(parents=True)

    def test_case_variant_duplicate_is_rejected(self):
        exported = self.export()
        self.activate_copy(exported)
        binder = self.install.mods.joinpath(*PurePosixPath(SUPPRESSION_PATH).parts)
        duplicate = binder.with_name(binder.name.upper())
        if duplicate == binder:
            self.skipTest("fixture filesystem does not permit a distinct case variant")
        duplicate.write_bytes(binder.read_bytes())
        with self.assertRaisesRegex(ValidationError, "exactly one case-insensitive"):
            verify_external_activation(
                exported.receipt, install=self.install, mods_root=self.mods_root,
                allow_live_acceptance_candidate=True,
            )

    def test_missing_partial_and_changed_non_binder_file_are_rejected(self):
        for mutation, pattern in (("missing", "exactly one"), ("event", "hash changed")):
            with self.subTest(mutation=mutation):
                self.reset_activation()
                exported = self.export()
                self.activate_copy(exported)
                if mutation == "missing":
                    target = self.install.mods.joinpath(*PurePosixPath(SUPPRESSION_PATH).parts)
                    target.unlink()
                else:
                    # The binder remains valid: every generated file, including
                    # EMEVD, must be checked independently.
                    target = self.install.mods.joinpath(*PurePosixPath(CATHEDRAL_EVENT_PATH).parts)
                    target.write_bytes(b"changed-event")
                with self.assertRaisesRegex(ValidationError, pattern):
                    verify_external_activation(
                        exported.receipt, install=self.install, mods_root=self.mods_root,
                        allow_live_acceptance_candidate=True,
                    )

    def test_collision_in_any_active_package_is_rejected_even_for_same_bytes(self):
        exported = self.export()
        self.activate_copy(exported)
        other = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME) / "Cosmetic"
        collision = other.joinpath(*PurePosixPath(
            CATHEDRAL_EVENT_PATH[len("dvdroot_ps4/"):]).parts)
        collision.parent.mkdir(parents=True)
        installed = self.install.mods.joinpath(*PurePosixPath(CATHEDRAL_EVENT_PATH).parts)
        collision.write_bytes(installed.read_bytes())
        with self.assertRaisesRegex(ValidationError, "collides"):
            verify_external_activation(
                exported.receipt, install=self.install, mods_root=self.mods_root,
                allow_live_acceptance_candidate=True,
            )

    def test_two_active_archipelago_packages_are_rejected(self):
        exported = self.export()
        self.activate_copy(exported)
        second = self.mods_root.with_name(ACTIVE_MODS_DIR_NAME) / "Archipelago-Other-deadbeef"
        (second / "sfx").mkdir(parents=True)
        (second / "sfx" / "unrelated.bin").write_bytes(b"other")
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            verify_external_activation(
                exported.receipt, install=self.install, mods_root=self.mods_root,
                allow_live_acceptance_candidate=True,
            )

    def test_directory_reparse_in_active_package_is_rejected(self):
        exported = self.export()
        active = self.activate_copy(exported)
        outside = self.root / "outside-dir"
        outside.mkdir()
        link = active / "linked-dir"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks are unavailable: {exc}")
        with self.assertRaisesRegex(ValidationError, "reparse"):
            verify_external_activation(
                exported.receipt, install=self.install, mods_root=self.mods_root,
                allow_live_acceptance_candidate=True,
            )

    def test_receipt_tamper_is_detected_before_activation(self):
        exported = self.export()
        raw = json.loads(exported.receipt_path.read_text(encoding="utf-8"))
        raw["identity"]["seed"] = "other-seed"
        exported.receipt_path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "inconsistent|identity digest"):
            load_external_receipt(
                exported.receipt_path, allow_live_acceptance_candidate=True
            )


if __name__ == "__main__":
    unittest.main()
