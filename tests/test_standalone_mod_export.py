from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.export_standalone_mod import (
    ACTIVE_MODS_DIR_NAME,
    BUILD_IDENTITY_FORMAT,
    BUILD_IDENTITY_NAME,
    BUILD_RECEIPT_FORMAT,
    BUILD_RECEIPT_NAME,
    GAMEPARAM_PATH,
    WAKEUP_EVENT_PATH,
    export_directory,
    export_zip,
    load_export_receipt,
    package_name,
    validate_overlay,
    verify_export,
)


ROOT = Path(__file__).resolve().parents[1]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_record(root: Path, relative: str) -> dict[str, object]:
    path = root.joinpath(*relative.split("/"))
    return {
        "path": relative,
        "sha256": digest(path.read_bytes()),
        "size": path.stat().st_size,
    }


def make_overlay(root: Path, *, seed: str = "Night of Hunters / 01", enemies: bool = True) -> Path:
    overlay = root / f"overlay-{len(list(root.glob('overlay-*')))}"
    gameparam = overlay.joinpath(*GAMEPARAM_PATH.split("/"))
    gameparam.parent.mkdir(parents=True)
    gameparam.write_bytes(b"composed-gameparam")
    item_plan = {"format": "bb-standalone-item-plan-v1", "seed": seed}
    write_json(overlay / "standalone-item-plan.json", item_plan)
    write_json(
        overlay / "item-writer-receipt.json",
        {"format": "bb-standalone-item-receipt-v1", "applied": True},
    )
    enemy_plan_sha = None
    if enemies:
        map_path = overlay / "dvdroot_ps4/map/MapStudio/m21_00_00_00.msb.dcx"
        map_path.parent.mkdir(parents=True)
        map_path.write_bytes(b"randomized-map")
        script_path = overlay / "dvdroot_ps4/script/m21_00_00_00.luabnd.dcx"
        script_path.parent.mkdir(parents=True)
        script_path.write_bytes(b"randomized-ai")
        write_json(
            overlay / "standalone-enemy-plan.json",
            {"format": "bb-enemizer-plan-v2", "seed": seed},
        )
        enemy_plan_sha = digest((overlay / "standalone-enemy-plan.json").read_bytes())
    identity = {
        "format": BUILD_IDENTITY_FORMAT,
        "seed": seed,
        "generator_build": "test-generator",
        "options": {
            "items": {"goal": "moon_presence", "include_dlc": False},
            "enemies": {"enabled": enemies, "preserve_locomotion": True},
        },
        "source_hashes": {
            "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx": "a" * 64,
            "dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx": "b" * 64,
        },
        "tool_hashes": {"item_writer": "c" * 64},
        "item_plan_sha256": digest((overlay / "standalone-item-plan.json").read_bytes()),
        "enemy_plan_sha256": enemy_plan_sha,
    }
    write_json(overlay / BUILD_IDENTITY_NAME, identity)
    relative_files = [
        path.relative_to(overlay).as_posix()
        for path in overlay.rglob("*")
        if path.is_file()
    ]
    records = [file_record(overlay, relative) for relative in sorted(relative_files)]
    receipt = {
        "format": BUILD_RECEIPT_FORMAT,
        "applied": True,
        "identity_sha256": digest((overlay / BUILD_IDENTITY_NAME).read_bytes()),
        "source_hashes": identity["source_hashes"],
        "composed_gameparam_sha256": digest(gameparam.read_bytes()),
        "item_writer": {"format": "bb-standalone-item-receipt-v1"},
        "enemy_writer": {"format": "test-enemy-receipt"} if enemies else None,
        "files": records,
    }
    write_json(overlay / BUILD_RECEIPT_NAME, receipt)
    return overlay


class StandaloneModExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.overlay = make_overlay(self.root)
        self.manager = self.root / "BBLauncher"
        self.mods = self.manager / "Mods"
        self.mods.mkdir(parents=True)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _wakeup_overlay(self):
        overlay = make_overlay(self.root, seed="expanded")
        event = overlay / WAKEUP_EVENT_PATH
        event.parent.mkdir(parents=True)
        event.write_bytes(b"native-wakeup-event")
        plan_path = overlay / "standalone-enemy-plan.json"
        plan = json.loads(plan_path.read_text())
        plan["wakeup_fallbacks"] = [{"logical_key": "test", "entity_id": 2410001,
                                    "map": "m24_01_00_00", "event_id": 12410510}]
        write_json(plan_path, plan)
        identity = json.loads((overlay / BUILD_IDENTITY_NAME).read_text())
        identity["enemy_plan_sha256"] = digest(plan_path.read_bytes())
        identity["source_hashes"][WAKEUP_EVENT_PATH] = "d" * 64
        write_json(overlay / BUILD_IDENTITY_NAME, identity)
        report = {"format": "bb-enemizer-wakeup-fallback-v1", "applied": True,
                  "plan_sha256": identity["enemy_plan_sha256"],
                  "wakeup_fallbacks": plan["wakeup_fallbacks"],
                  "source_event_sha256": "d" * 64,
                  "output_event_sha256": digest(event.read_bytes())}
        write_json(overlay / "wakeup-fallback-report.json", report)
        receipt = json.loads((overlay / BUILD_RECEIPT_NAME).read_text())
        receipt.update(identity_sha256=digest((overlay / BUILD_IDENTITY_NAME).read_bytes()),
                       source_hashes=identity["source_hashes"], wakeup_writer=report)
        receipt["files"] = [file_record(overlay, p.relative_to(overlay).as_posix())
                            for p in overlay.rglob("*")
                            if p.is_file() and p.name != BUILD_RECEIPT_NAME]
        write_json(overlay / BUILD_RECEIPT_NAME, receipt)
        return overlay

    def test_expanded_wakeup_event_exports_and_tampering_is_refused(self):
        overlay = self._wakeup_overlay()
        result = export_directory(overlay, mods_root=self.mods, receipt_root=self.receipts)
        self.assertTrue((result.package_path / WAKEUP_EVENT_PATH).is_file())
        self.assertFalse((result.package_path / "wakeup-fallback-report.json").exists())
        verify_export(result.package_path, result.receipt_path, overlay_root=overlay)
        (result.package_path / WAKEUP_EVENT_PATH).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            verify_export(result.package_path, result.receipt_path, overlay_root=overlay)

    def test_wakeup_writer_provenance_and_other_event_paths_are_refused(self):
        for mutation in ("source", "plan", "output", "unexpected-event"):
            with self.subTest(mutation=mutation):
                overlay = self._wakeup_overlay()
                receipt_path = overlay / BUILD_RECEIPT_NAME
                receipt = json.loads(receipt_path.read_text())
                if mutation == "unexpected-event":
                    extra = "dvdroot_ps4/event/m99_00_00_00.emevd.dcx"
                    (overlay / extra).write_bytes(b"unowned-event")
                    receipt["files"].append(file_record(overlay, extra))
                else:
                    field = {"source": "source_event_sha256", "plan": "plan_sha256",
                             "output": "output_event_sha256"}[mutation]
                    receipt["wakeup_writer"][field] = "e" * 64
                    write_json(overlay / "wakeup-fallback-report.json", receipt["wakeup_writer"])
                    receipt["files"] = [file_record(overlay, r["path"]) for r in receipt["files"]]
                write_json(receipt_path, receipt)
                with self.assertRaises(ValueError):
                    validate_overlay(overlay)

    def test_directory_export_is_data_only_and_verifies_exact_native_paths(self):
        result = export_directory(
            self.overlay, mods_root=self.mods, receipt_root=self.receipts
        )
        exported = {
            path.relative_to(result.package_path).as_posix()
            for path in result.package_path.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            {
                GAMEPARAM_PATH,
                "dvdroot_ps4/map/MapStudio/m21_00_00_00.msb.dcx",
                "dvdroot_ps4/script/m21_00_00_00.luabnd.dcx",
            },
            exported,
        )
        for relative in exported:
            self.assertNotIn("standalone-", relative)
        receipt = verify_export(
            result.package_path, result.receipt_path, overlay_root=self.overlay
        )
        self.assertEqual("directory", receipt["package_kind"])
        self.assertEqual("Night of Hunters / 01", receipt["seed"])
        self.assertEqual("moon_presence", receipt["options"]["items"]["goal"])
        self.assertFalse(receipt["validation"]["gameplay_tested"])
        serialized = json.dumps(receipt).lower()
        for forbidden in ("archipelago", "server", "slot", "client", "suppression"):
            self.assertNotIn(forbidden, serialized)

    def test_zip_is_deterministic_safe_and_extracts_as_one_bblauncher_package(self):
        first_root = self.root / "zip-one"
        second_root = self.root / "zip-two"
        first_root.mkdir()
        second_root.mkdir()
        first = export_zip(
            self.overlay, zip_root=first_root, receipt_root=first_root
        )
        second = export_zip(
            self.overlay, zip_root=second_root, receipt_root=second_root
        )
        self.assertEqual(first.package_path.name, second.package_path.name)
        self.assertEqual(first.package_path.read_bytes(), second.package_path.read_bytes())
        self.assertNotIn("/", first.package_path.name)
        self.assertNotIn(" ", first.package_path.name)
        with zipfile.ZipFile(first.package_path) as archive:
            names = archive.namelist()
        expected_prefix = first.receipt["package_name"] + "/dvdroot_ps4/"
        self.assertTrue(names)
        for name in names:
            self.assertEqual(expected_prefix, name[: len(expected_prefix)])
        verify_export(first.package_path, first.receipt_path, overlay_root=self.overlay)

    def test_overlay_validation_rejects_corruption_missing_files_and_extras(self):
        mutations = ("corrupt", "missing", "extra")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                overlay = make_overlay(self.root, seed=f"drift-{mutation}")
                target = overlay.joinpath(*GAMEPARAM_PATH.split("/"))
                if mutation == "corrupt":
                    target.write_bytes(b"changed")
                    pattern = "drifted"
                elif mutation == "missing":
                    target.unlink()
                    pattern = "file set differs"
                else:
                    (overlay / "unexpected.bin").write_bytes(b"extra")
                    pattern = "file set differs"
                with self.assertRaisesRegex(ValueError, pattern):
                    validate_overlay(overlay)

    def test_build_receipt_rejects_path_escape_and_identity_provenance_drift(self):
        escape = make_overlay(self.root, seed="escape")
        receipt_path = escape / BUILD_RECEIPT_NAME
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["files"].append(
            {"path": "../outside.bin", "size": 1, "sha256": "d" * 64}
        )
        write_json(receipt_path, receipt)
        with self.assertRaisesRegex(ValueError, "unsafe relative path"):
            validate_overlay(escape)

        provenance = make_overlay(self.root, seed="provenance")
        receipt_path = provenance / BUILD_RECEIPT_NAME
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["identity_sha256"] = "e" * 64
        write_json(receipt_path, receipt)
        with self.assertRaisesRegex(ValueError, "authenticate its identity"):
            validate_overlay(provenance)

    def test_native_ai_writer_receipt_inside_game_root_is_refused(self):
        overlay = make_overlay(self.root, seed="misplaced-native-receipt")
        misplaced = overlay / "dvdroot_ps4/script.json"
        write_json(misplaced, {"format": "bb-enemizer-ai-receipt-v1"})
        receipt_path = overlay / BUILD_RECEIPT_NAME
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["files"].append(file_record(overlay, "dvdroot_ps4/script.json"))
        write_json(receipt_path, receipt)
        with self.assertRaisesRegex(
            ValueError, "unexpected game-data payload path.*dvdroot_ps4/script.json"
        ):
            validate_overlay(overlay)

    def test_existing_destination_is_preserved(self):
        overlay = validate_overlay(self.overlay)
        target = self.mods / package_name(overlay)
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_bytes(b"do-not-replace")
        with self.assertRaisesRegex(ValueError, "overwrite existing"):
            export_directory(
                self.overlay, mods_root=self.mods, receipt_root=self.receipts
            )
        self.assertEqual(b"do-not-replace", marker.read_bytes())
        self.assertIsNone(next(self.receipts.iterdir(), None))

    def test_export_verification_rejects_changed_missing_and_extra_package_files(self):
        for mutation in ("changed", "missing", "extra"):
            with self.subTest(mutation=mutation):
                overlay = make_overlay(self.root, seed=f"package-{mutation}")
                result = export_directory(
                    overlay, mods_root=self.mods, receipt_root=self.receipts
                )
                gameparam = result.package_path.joinpath(*GAMEPARAM_PATH.split("/"))
                if mutation == "changed":
                    gameparam.write_bytes(b"corrupt")
                    pattern = "drifted"
                elif mutation == "missing":
                    gameparam.unlink()
                    pattern = "file set differs"
                else:
                    (result.package_path / "dvdroot_ps4/extra.bin").write_bytes(b"extra")
                    pattern = "file set differs"
                with self.assertRaisesRegex(ValueError, pattern):
                    verify_export(result.package_path, result.receipt_path)

    def test_export_receipt_tamper_and_wrong_overlay_provenance_are_rejected(self):
        result = export_directory(
            self.overlay, mods_root=self.mods, receipt_root=self.receipts
        )
        other = make_overlay(self.root, seed="different-seed")
        with self.assertRaisesRegex(ValueError, "provenance"):
            verify_export(result.package_path, result.receipt_path, overlay_root=other)

        raw = json.loads(result.receipt_path.read_text(encoding="utf-8"))
        raw["seed"] = "tampered"
        write_json(result.receipt_path, raw)
        with self.assertRaisesRegex(ValueError, "package name|identity digest"):
            load_export_receipt(result.receipt_path)

    def test_active_mods_and_receipts_inside_manager_are_never_written(self):
        active = self.manager / ACTIVE_MODS_DIR_NAME
        active.mkdir()
        before = tuple(active.iterdir())
        with self.assertRaisesRegex(ValueError, "active Mods"):
            export_directory(
                self.overlay, mods_root=active, receipt_root=self.receipts
            )
        self.assertEqual(before, tuple(active.iterdir()))

        manager_receipts = self.manager / "receipts"
        manager_receipts.mkdir()
        with self.assertRaisesRegex(ValueError, "outside BBLauncher"):
            export_directory(
                self.overlay, mods_root=self.mods, receipt_root=manager_receipts
            )
        self.assertIsNone(next(self.mods.iterdir(), None))

    def test_cli_exports_and_verifies_without_archipelago_imports(self):
        zip_root = self.root / "cli-zip"
        zip_root.mkdir()
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT)
        exported = subprocess.run(
            [
                sys.executable,
                "-S",
                str(ROOT / "tools/export_standalone_mod.py"),
                "export",
                "--overlay",
                str(self.overlay),
                "--zip-root",
                str(zip_root),
                "--receipt-root",
                str(zip_root),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, exported.returncode, exported.stderr)
        archive = next(zip_root.glob("*.zip"))
        receipt = next(zip_root.glob("*.export-receipt.json"))
        verified = subprocess.run(
            [
                sys.executable,
                "-S",
                str(ROOT / "tools/export_standalone_mod.py"),
                "verify",
                "--package",
                str(archive),
                "--receipt",
                str(receipt),
                "--overlay",
                str(self.overlay),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, verified.returncode, verified.stderr)
        command_output = (
            exported.stdout + exported.stderr + verified.stdout + verified.stderr
        )
        self.assertNotIn("Archipelago", command_output)


if __name__ == "__main__":
    unittest.main()
