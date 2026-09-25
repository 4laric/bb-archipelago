from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher import core
from bb_launcher.integrated.migration import migrate_legacy_overlay


def _sfo(path: Path, values: dict[str, str]) -> None:
    keys = bytearray()
    data = bytearray()
    entries = []
    for key, value in values.items():
        key_at = len(keys)
        keys.extend(key.encode() + b"\0")
        encoded = value.encode() + b"\0"
        data_at = len(data)
        data.extend(encoded)
        entries.append(struct.pack("<HHIII", key_at, 0x0204, len(encoded), len(encoded), data_at))
    key_table = 20 + 16 * len(entries)
    data_table = key_table + len(keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<4s4I", b"\0PSF", 0x00000101, key_table,
                                 data_table, len(entries)) + b"".join(entries) + keys + data)


def _file(root: Path, relative: str, payload: bytes) -> dict[str, object]:
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"path": relative, "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "game"
        _sfo(self.root / core.SERIAL / "sce_sys" / "param.sfo",
             {"TITLE_ID": core.SERIAL, "APP_VER": core.APP_VERSION})
        self.install = core.GameInstall.from_root(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def owner(self, *, merged: bool = False) -> tuple[dict, str | None]:
        ap = _file(self.install.mods, core.SUPPRESSION_PATH, b"ap binder")
        user_path = "dvdroot_ps4/msg/engus/player.msgbnd.dcx" if merged else None
        user = [_file(self.install.mods, user_path, b"player mod")] if user_path else []
        owner = {"format": core.OWNER_FORMAT, "launcher": "bloodborne-archipelago",
                 "cache_key": "a" * 64, "files": [ap],
                 "user_merge": {"format": core.USER_MERGE_FORMAT, "files": user}}
        (self.install.mods / core.OWNER_NAME).write_text(json.dumps(owner), encoding="utf-8")
        return owner, user_path

    def migrate(self) -> dict:
        return migrate_legacy_overlay(self.root, process_is_running=lambda: False,
                                      state_root=Path(self.temp.name) / "state")

    def test_verified_overlay_moves_aside_and_repeat_is_idempotent(self) -> None:
        self.owner()
        result = self.migrate()
        self.assertEqual(result["status"], "migrated")
        self.assertFalse(self.install.mods.exists())
        self.assertEqual(core._load_owner(Path(result["disabled_overlay"]))["cache_key"], "a" * 64)
        self.assertEqual(self.migrate()["status"], "already_migrated")

    def test_new_companion_overlay_after_prior_migration_is_migrated_again(self) -> None:
        self.owner()
        first = self.migrate()
        self.owner()
        second = self.migrate()
        self.assertEqual(second["status"], "migrated")
        self.assertNotEqual(first["disabled_overlay"], second["disabled_overlay"])
        self.assertTrue(Path(first["disabled_overlay"]).exists())
        self.assertTrue(Path(second["disabled_overlay"]).exists())

    def test_merged_player_bytes_remain_in_plain_overlay(self) -> None:
        _, user_path = self.owner(merged=True)
        result = self.migrate()
        self.assertEqual(result["merged_files"], 1)
        self.assertEqual(self.install.mods.joinpath(*user_path.split("/")).read_bytes(), b"player mod")
        self.assertFalse((self.install.mods / core.OWNER_NAME).exists())
        self.assertTrue(Path(result["disabled_overlay"]).joinpath(*user_path.split("/")).exists())

    def test_interrupted_after_deactivation_resumes_from_preserved_tree(self) -> None:
        self.owner(merged=True)
        with patch("bb_launcher.integrated.migration._copy_merged_files", side_effect=OSError("stop")):
            with self.assertRaisesRegex(OSError, "stop"):
                self.migrate()
        self.assertFalse(self.install.mods.exists())
        resumed = self.migrate()
        self.assertEqual(resumed["status"], "migrated")
        self.assertEqual(resumed["merged_files"], 1)

    def test_unowned_and_modified_trees_are_not_moved(self) -> None:
        self.install.mods.mkdir()
        (self.install.mods / "unowned.txt").write_text("mine")
        self.assertEqual(self.migrate()["status"], "no_legacy")
        self.assertTrue((self.install.mods / "unowned.txt").exists())
        (self.install.mods / "unowned.txt").unlink()
        self.owner()
        self.install.mods.joinpath(*core.SUPPRESSION_PATH.split("/")).write_bytes(b"changed")
        with self.assertRaises(core.OverlayIntegrityError):
            self.migrate()
        self.assertTrue((self.install.mods / core.OWNER_NAME).exists())

    def test_game_running_refuses_before_any_mutation(self) -> None:
        self.owner()
        with self.assertRaisesRegex(core.ConflictError, "shadPS4 is running"):
            migrate_legacy_overlay(self.root, process_is_running=lambda: True)
        self.assertTrue((self.install.mods / core.OWNER_NAME).exists())


if __name__ == "__main__":
    unittest.main()
