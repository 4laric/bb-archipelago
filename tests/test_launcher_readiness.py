from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bb_launcher.client_config import session_paths
from bb_launcher.core import SUPPRESSION_PATH, activate_build, sha256_file
from bb_launcher.readiness import (
    BRIDGE_STATE_NAME,
    format_readiness,
    gather_readiness,
    grants_watchdog_warning,
)
from tests.test_launcher_core import make_install
from tests.test_launcher_client_config import make_build


def write_ledger(path: Path, entries: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"slots": entries}), encoding="utf-8")


def ledger_entry(highest: int | None, acks: int, watermark: int | None = None) -> dict:
    return {
        "bound_save_identity": "mock-save",
        "highest_processed_index": highest,
        "acknowledged": {str(index): {} for index in range(acks)},
        "pending": None,
        "save_watermark": watermark,
    }


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.install = make_install(self.root / "game")

    def tearDown(self):
        self.temporary.cleanup()

    def activate(self, seed: str, content: bytes) -> dict:
        build = make_build(self.root / seed, seed, content)
        return activate_build(self.install, build, process_is_running=lambda: False)

    def test_readiness_reports_the_active_overlay_ledger_and_bridge(self):
        owner = self.activate("52100005", b"suppressed")
        state = self.root / "state"
        paths = session_paths(state, seed="52100005", slot="Hunter")
        write_ledger(
            paths.ledger,
            {"52100005\x1fHunter": ledger_entry(3, 4, watermark=3)},
        )
        paths.bridge_root.mkdir(parents=True)
        (paths.bridge_root / BRIDGE_STATE_NAME).write_text(
            "build=bb-0.1.0-r5\nprotocol=BBGRANT1\nharness=bb-native-grant-v5\n"
            "status=completed\npid=5040\ntag=received_17\ndetail=direct before=2 after=3\n",
            encoding="utf-8",
        )
        # The config file exists once a launch wrote it; fake the file only.
        paths.config.parent.mkdir(parents=True, exist_ok=True)
        paths.config.write_text("{}", encoding="utf-8")

        readiness = gather_readiness(self.install, state, seed="52100005", slot="Hunter")
        self.assertFalse(readiness.notes)
        overlay = readiness.overlay
        self.assertIsNotNone(overlay)
        assert overlay is not None
        self.assertEqual(overlay.cache_key, owner["cache_key"])
        self.assertEqual(overlay.seed, "52100005")
        self.assertEqual(overlay.slot, "Hunter")
        installed = self.install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        self.assertEqual(overlay.suppression_sha256, sha256_file(installed))
        self.assertFalse(overlay.enemizer_enabled)
        ledger = readiness.ledger
        self.assertIsNotNone(ledger)
        assert ledger is not None
        self.assertEqual(ledger.acknowledged, 4)
        self.assertEqual(ledger.highest_processed_index, 3)
        self.assertEqual(ledger.save_watermark, 3)
        self.assertFalse(ledger.pending)
        bridge = readiness.bridge
        self.assertIsNotNone(bridge)
        assert bridge is not None
        self.assertEqual(bridge.status, "completed")
        self.assertEqual(bridge.harness, "bb-native-grant-v5")
        self.assertEqual(bridge.pid, 5040)

        text = format_readiness(readiness)
        self.assertIn(owner["cache_key"][:12], text)
        self.assertIn("4 acknowledged, cursor 3, save watermark 3", text)
        self.assertIn("bb-native-grant-v5", text)
        self.assertIn("(written)", text)

    def test_readiness_is_fail_soft_for_a_fresh_session(self):
        readiness = gather_readiness(self.install, self.root / "state", seed="s", slot="Hunter")
        self.assertIsNone(readiness.overlay)
        self.assertIsNone(readiness.ledger)
        self.assertIsNone(readiness.bridge)
        self.assertFalse(readiness.notes)
        text = format_readiness(readiness)
        self.assertIn("Overlay: none active", text)
        self.assertIn("no deliveries recorded yet", text)
        self.assertIn("Bridge: no state yet", text)
        self.assertIn("written at launch", text)

    def test_readiness_surfaces_bad_state_as_notes_without_raising(self):
        # An unowned pre-existing mods directory is a conflict, not a crash.
        self.install.mods.mkdir()
        (self.install.mods / "user-mod.bin").write_bytes(b"mine")
        paths = session_paths(self.root / "state", seed="s", slot="Hunter")
        paths.ledger.parent.mkdir(parents=True)
        paths.ledger.write_bytes(b"{not json")
        paths.bridge_root.mkdir(parents=True)
        (paths.bridge_root / BRIDGE_STATE_NAME).write_text("build=bb\n", encoding="utf-8")

        readiness = gather_readiness(self.install, self.root / "state", seed="s", slot="Hunter")
        self.assertIsNone(readiness.overlay)
        self.assertIsNone(readiness.ledger)
        self.assertIsNone(readiness.bridge)
        joined = "\n".join(readiness.notes)
        self.assertIn("ownership", joined)
        self.assertIn("ledger is unreadable", joined)
        self.assertIn("no status line", joined)
        text = format_readiness(readiness)
        self.assertIn("Note:", text)

    def test_ledger_progress_is_scoped_to_the_matching_seed_and_slot(self):
        state = self.root / "state"
        entries = {"other\x1fHunter": ledger_entry(7, 8), "s\x1fOther": ledger_entry(2, 3)}
        ours = session_paths(state, seed="s", slot="Hunter")
        theirs = session_paths(state, seed="other", slot="Hunter")
        write_ledger(ours.ledger, entries)
        write_ledger(theirs.ledger, entries)
        readiness = gather_readiness(self.install, state, seed="s", slot="Hunter")
        # The file exists but holds only other sessions: this one is fresh.
        self.assertIsNone(readiness.ledger)
        self.assertFalse(readiness.notes)

        other = gather_readiness(self.install, state, seed="other", slot="Hunter")
        ledger = other.ledger
        self.assertIsNotNone(ledger)
        assert ledger is not None
        self.assertEqual(ledger.acknowledged, 8)
        self.assertEqual(ledger.highest_processed_index, 7)

    def test_grants_watchdog_warns_when_an_expected_bridge_never_reported(self):
        readiness = gather_readiness(self.install, self.root / "state", seed="s", slot="Hunter")
        self.assertIsNone(readiness.bridge)
        warning = grants_watchdog_warning(readiness, bridge_expected=True)
        self.assertIsNotNone(warning)
        assert warning is not None
        self.assertIn("NOT armed", warning)
        self.assertIn("Cheat Engine", warning)

    def test_grants_watchdog_is_quiet_once_the_bridge_reports(self):
        paths = session_paths(self.root / "state", seed="s", slot="Hunter")
        paths.bridge_root.mkdir(parents=True)
        (paths.bridge_root / BRIDGE_STATE_NAME).write_text(
            "build=bb-0.1.0-r5\nprotocol=BBGRANT1\nharness=bb-native-grant-v5\n"
            "status=executing\npid=5040\n",
            encoding="utf-8",
        )
        readiness = gather_readiness(self.install, self.root / "state", seed="s", slot="Hunter")
        self.assertIsNotNone(readiness.bridge)
        self.assertIsNone(grants_watchdog_warning(readiness, bridge_expected=True))

    def test_grants_watchdog_is_quiet_when_no_bridge_was_expected(self):
        readiness = gather_readiness(self.install, self.root / "state", seed="s", slot="Hunter")
        self.assertIsNone(readiness.bridge)
        self.assertIsNone(grants_watchdog_warning(readiness, bridge_expected=False))


if __name__ == "__main__":
    unittest.main()
