import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tools.bb_enemizer.boss_canary import ADAPTER, CHANGED_EVENTS, COMPLETION_EVENT
from tools.build_boss_shuffle import build, checked_native_plan, regenerate_draft
from tools.verify_boss_canary import AI, AI_REPORT, EVENT, EXPECTED_FILES, GAMEPARAM, PLAN, RECEIPT, SCALING, SOURCE_PLAN, digest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


def write_verified_writer_output(root: Path) -> None:
    """A writer-shaped result whose receipt can pass the independent verifier."""
    for name in EXPECTED_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode("utf-8"))
    canary = {"boss_adapter": ADAPTER, "required_event_overlay": EVENT, "swap_count": 1,
              "swaps": [{"logical_key": "m24_01_00_00:c5000_0000"}], "scaling": {"applied": True}}
    for name in (PLAN, SOURCE_PLAN):
        (root / name).write_text(json.dumps(canary), encoding="utf-8")
    scaling = {"applied": True, "source_plan_sha256": digest(root / SOURCE_PLAN),
               "output_plan_sha256": digest(root / PLAN), "output_gameparam_sha256": digest(root / GAMEPARAM),
               "source_gameparam_sha256": "a" * 64, "paramdef_sha256": "b" * 64}
    (root / SCALING).write_text(json.dumps(scaling), encoding="utf-8")
    ai = {"applied": True, "plan_sha256": digest(root / PLAN), "gameparam_sha256": "a" * 64,
          "paramdef_sha256": "b" * 64,
          "maps": [{"map": Path(AI).name, "missing_goals_after": 0, "output_sha256": digest(root / AI)}]}
    (root / AI_REPORT).write_text(json.dumps(ai), encoding="utf-8")
    receipt = {"format": "bb-boss-adapter-v1", "adapter": ADAPTER, "applied": True,
               "completion_event": COMPLETION_EVENT, "ap_location": "boss_cleric_beast",
               "changed_events": CHANGED_EVENTS, "output_event_sha256": digest(root / EVENT),
               "files": [{"path": name, "sha256": digest(root / name), "size": (root / name).stat().st_size}
                         for name in sorted(EXPECTED_FILES)]}
    (root / RECEIPT).write_text(json.dumps(receipt), encoding="utf-8")


class BossShuffleBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.draft, cls.native = regenerate_draft(BUNDLE, "draft-seed")

    def write_draft(self, directory: Path, value=None) -> Path:
        draft = directory / "draft.json"
        draft.write_text(json.dumps(self.draft if value is None else value), encoding="utf-8")
        return draft

    def test_tampered_or_non_native_drafts_are_refused_before_the_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tampered = json.loads(json.dumps(self.draft))
            tampered["swaps"][0]["swap"]["target"]["model_name"] = "c9999"
            with self.assertRaisesRegex(ValueError, "canonical bundle"):
                checked_native_plan(self.write_draft(root, tampered), BUNDLE)
            unsupported = json.loads(json.dumps(self.draft))
            unsupported["format"] = "bb-enemizer-plan-v2"
            with self.assertRaisesRegex(ValueError, "unsupported draft"):
                checked_native_plan(self.write_draft(root, unsupported), BUNDLE)

    def test_writer_command_is_native_and_verified_staging_is_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "inputs"
            inputs.mkdir()
            draft = self.write_draft(inputs)
            output = root / "published"
            args = Namespace(plan=draft, bundle=BUNDLE, writer=inputs / "writer.dll",
                             gameparam=inputs / "gameparam.parambnd.dcx", paramdef=inputs / "paramdef.paramdefbnd.dcx",
                             maps=inputs / "maps", scripts=inputs / "scripts", event=inputs / "event.emevd.dcx",
                             output=output, dotnet=Path("dotnet"))
            for path in (args.writer, args.gameparam, args.paramdef, args.event):
                path.write_bytes(b"input")
            args.maps.mkdir()
            args.scripts.mkdir()

            def fake_writer(command, check):
                self.assertTrue(check)
                self.assertIn("--boss-native", command)
                self.assertNotIn("--boss-scaled", command)
                self.assertEqual("--apply", command[-1])
                native = json.loads(Path(command[3]).read_text(encoding="utf-8"))
                self.assertEqual("draft-seed", native["seed"])
                self.assertEqual(ADAPTER, native["boss_adapter"])
                write_verified_writer_output(Path(command[-2]))

            with patch("tools.build_boss_shuffle.subprocess.run", side_effect=fake_writer) as run:
                result = build(args)
            self.assertEqual(10, result["files_verified"])
            self.assertTrue((output / RECEIPT).is_file())
            self.assertEqual(1, run.call_count)
            stages = [path for path in root.iterdir() if path.name.startswith(".bb-boss-shuffle-")]
            self.assertEqual(0, len(stages), "published builds must not leave an unverified staging directory")


if __name__ == "__main__":
    unittest.main()
