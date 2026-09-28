import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.cli import main

ROOT = Path(__file__).resolve().parents[1]


class NoWinterLanternTests(unittest.TestCase):
    def test_normal_spawns_replaced_and_all_variants_excluded_deterministically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.tsv"
            inventory.write_bytes(read_blob(ROOT / "research/bb_inputs.db", "mined/msb_enemies.tsv"))
            plans = []
            for i in range(2):
                output = root / f"plan-{i}.json"
                with contextlib.redirect_stdout(io.StringIO()):
                    result = main(["--seed", "lantern-regression", "--inventory", str(inventory),
                                   "--output", str(output), "--no-winter-lanterns",
                                   "--tags", str(ROOT / "research/enemizer/enemy_tags.json"),
                                   "--slot-policy", str(ROOT / "research/enemizer/slot_policy.json"),
                                   "--facts", str(ROOT / "research/enemizer/archetype_facts.json")])
                self.assertEqual(0, result)
                plans.append(json.loads(output.read_text()))
            self.assertEqual(plans[0], plans[1])
            swaps = plans[0]["swaps"]
            lanterns = [s for s in swaps if s["source"]["model_name"] == "c2560"]
            self.assertEqual(9, len(lanterns))
            self.assertEqual({"m26_00_00_00", "m33_00_00_00", "m36_00_00_00"},
                             {s["logical_key"].split(":")[0] for s in lanterns})
            targets = {s["target"]["model_name"] for s in swaps}
            self.assertGreater(len(targets), 1)
            self.assertNotIn("c2560", targets)
            self.assertNotIn("m26_00_00_00:c2560_0004", {s["logical_key"] for s in swaps})

    def test_helper_patch_preserves_other_events_and_rejects_changed_callee(self):
        from tools.bb_enemizer.boss_canary import event_blocks
        from tools.bb_enemizer.winter_lanterns import CALLEES, INITIALIZERS, HELPERS, patch_winter_lanterns
        for map_name in CALLEES:
            source = read_blob(ROOT / "research/bb_inputs.db", f"event/{map_name}.emevd.dcx.js").decode("utf-8-sig")
            before = event_blocks(source)
            after = event_blocks(patch_winter_lanterns(map_name, source))
            self.assertEqual({k: v for k, v in before.items() if k != 0},
                             {k: v for k, v in after.items() if k != 0})
            for line in INITIALIZERS[map_name]:
                self.assertIn(line, before[0])
                self.assertNotIn(line, after[0])
            for helper in HELPERS[map_name]:
                self.assertIn(f"ChangeCharacterEnableState({helper}, Disabled);", after[0])
            event_id = next(iter(CALLEES[map_name]))
            changed = source.replace("\r\n", "\n").replace(before[event_id], before[event_id].replace("{", "{\n    NoOperation();", 1))
            with self.assertRaisesRegex(ValueError, "unsupported Winter Lantern helper"):
                patch_winter_lanterns(map_name, changed)

    def test_helper_patch_composes_with_boss_constructor_edits(self):
        from tools.bb_enemizer.boss_pool import compose_event_patches
        from tools.bb_enemizer.winter_lanterns import CALLEES, HELPERS, patch_winter_lanterns
        for map_name in CALLEES:
            source = read_blob(ROOT / "research/bb_inputs.db", f"event/{map_name}.emevd.dcx.js").decode("utf-8-sig").replace("\r\n", "\n")
            boss = source.replace("$Event(0, Default, function() {", "$Event(0, Default, function() {\n    SetEventFlag(99000000, OFF);", 1)
            self.assertNotEqual(source, boss)
            lanterns = patch_winter_lanterns(map_name, source)
            merged = compose_event_patches(source, [boss, lanterns], [])
            self.assertEqual(merged, compose_event_patches(source, [lanterns, boss], []))
            self.assertIn("SetEventFlag(99000000, OFF);", merged)
            for helper in HELPERS[map_name]:
                self.assertIn(f"SetCharacterBackreadState({helper}, true);", merged)
