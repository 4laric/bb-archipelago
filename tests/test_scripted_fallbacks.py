"""Boss-pool scripted-AI initializer fallbacks (tools/bb_enemizer/scripted_fallbacks.py)."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.bb_enemizer import scripted_fallbacks as fallbacks
from tools.bb_enemizer.boss_pool import compose_event_patches
from tools.bb_enemizer.cli import load_release_files
from tools.bb_enemizer.inventory import (
    apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
)
from tools.bb_enemizer.planner import EnemizerConfig, plan_swaps
from tools.build_emevd_entity_usage import materialize_bundle

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "research/enemizer"
CATHEDRAL = "m24_00_00_00"
CENTRAL = "m24_01_00_00"


class ScriptedFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.inventory, cls.events = materialize_bundle(ROOT / "research/bb_inputs.db", Path(cls._tmp.name))
        cls.texts = {name: (cls.events / f"{name}.emevd.dcx.js").read_text(encoding="utf-8-sig")
                     for name in (CATHEDRAL, CENTRAL)}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_committed_record_is_rebuilt_from_the_bundle(self):
        committed = json.loads((RELEASE / "release_scripted.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, fallbacks.build_release(self.events))
        self.assertEqual(21, len(committed["releases"]))

    def test_every_pinned_line_names_its_entity(self):
        self.assertEqual(set(fallbacks.LINES), set(fallbacks.ENTITY_IDS))
        for key, lines in fallbacks.LINES.items():
            for line in lines:
                self.assertIn(str(fallbacks.ENTITY_IDS[key]), line, key)
        self.assertEqual(51, sum(len(fallbacks.LINES[key]) for key in fallbacks.LINES
                                 if key.startswith(CATHEDRAL)))

    def test_patch_removes_exactly_the_swapped_placements_lines(self):
        keys = ["m24_00_00_00:c2730_0009", "m24_00_00_00:c2700_0000"]
        patched = fallbacks.patch_initializers(CATHEDRAL, self.texts[CATHEDRAL], keys)
        removed = set(self.texts[CATHEDRAL].splitlines()) - set(patched.splitlines())
        self.assertEqual({line.strip() for line in removed},
                         {line for key in keys for line in fallbacks.LINES[key]})
        # The staircase giant keeps its patrol and wake-on-proximity events.
        self.assertIn("$InitializeEvent(0, 12405670, 2400203, 2404332, 2404301, 5, 0);", patched)
        # Another giant's pinned lines stay.
        self.assertIn(fallbacks.LINES["m24_00_00_00:c2730_0003"][0], patched)

    def test_patch_refuses_changed_or_unknown_sources(self):
        with self.assertRaises(ValueError):
            fallbacks.patch_initializers(CATHEDRAL, self.texts[CATHEDRAL], ["m24_00_00_00:c2700_0001"])
        body_changed = self.texts[CATHEDRAL].replace(
            "ChangeCharacterDispmask(chrEntityId, 3, OFF);", "ChangeCharacterDispmask(chrEntityId, 2, OFF);", 1)
        with self.assertRaises(ValueError):
            fallbacks.patch_initializers(CATHEDRAL, body_changed, ["m24_00_00_00:c2700_0000"])
        line = fallbacks.LINES["m24_00_00_00:c2700_0000"][0]
        duplicated = self.texts[CATHEDRAL].replace(line, line + "\n    " + line, 1)
        with self.assertRaises(ValueError):
            fallbacks.patch_initializers(CATHEDRAL, duplicated, ["m24_00_00_00:c2700_0000"])

    def test_patch_composes_with_another_constructor_variant(self):
        original = self.texts[CATHEDRAL]
        ours = fallbacks.patch_initializers(CATHEDRAL, original, ["m24_00_00_00:c2730_0005"])
        other_line = "$InitializeEvent(0, 12405670, 2400203, 2404332, 2404301, 5, 0);"
        other = original.replace(other_line, other_line + "\n    $InitializeEvent(0, 12409999);", 1)
        combined = compose_event_patches(original, [ours, other], [])
        self.assertIn("$InitializeEvent(0, 12409999);", combined)
        for line in fallbacks.LINES["m24_00_00_00:c2730_0005"]:
            self.assertNotIn(line, combined)

    def test_plan_rows_must_be_pinned_and_swapped(self):
        row = {"logical_key": "m24_00_00_00:c2730_0009", "entity_id": 2400203, "map": CATHEDRAL}
        wake = {"logical_key": "m24_01_00_00:c1120_0009", "entity_id": 2410148, "map": CENTRAL,
                "event_id": 12415130}
        plan = {"swaps": [{"logical_key": row["logical_key"]}, {"logical_key": wake["logical_key"]}],
                "scripted_fallbacks": [row], "wakeup_fallbacks": [wake]}
        self.assertEqual({f"{CATHEDRAL}.emevd.dcx.js": [row["logical_key"]],
                          f"{CENTRAL}.emevd.dcx.js": [wake["logical_key"]]},
                         fallbacks.scripted_fallback_keys(plan))
        for broken in ({**plan, "swaps": []},
                       {**plan, "scripted_fallbacks": [{**row, "entity_id": 1}]},
                       {**plan, "scripted_fallbacks": [{**row, "logical_key": "m24_00_00_00:c2700_0001"}]}):
            with self.assertRaises(ValueError):
                fallbacks.scripted_fallback_keys(broken)

    def test_boss_builder_adds_one_variant_per_map_and_retires_rows(self):
        from tools.build_boss_encounters import add_scripted_variants, retire_applied_fallbacks

        texts = {f"{name}.emevd.dcx.js": text for name, text in self.texts.items()}
        variants = {f"{CENTRAL}.emevd.dcx.js": ["boss adapter"]}
        scripted = {f"{CATHEDRAL}.emevd.dcx.js": ["m24_00_00_00:c2700_0000"],
                    f"{CENTRAL}.emevd.dcx.js": ["m24_01_00_00:c1100_0000"]}
        add_scripted_variants(variants, texts, scripted)
        self.assertEqual(1, len(variants[f"{CATHEDRAL}.emevd.dcx.js"]))
        self.assertEqual(["boss adapter", fallbacks.patch_initializers(
            CENTRAL, self.texts[CENTRAL], ["m24_01_00_00:c1100_0000"])], variants[f"{CENTRAL}.emevd.dcx.js"])
        wake = {"logical_key": "m24_01_00_00:c1120_0009"}
        row = {"logical_key": "m24_00_00_00:c2700_0000"}
        plan = retire_applied_fallbacks({"wakeup_fallbacks": [wake], "scripted_fallbacks": [row]})
        self.assertEqual({"wakeup_fallbacks": [], "boss_scripted_fallbacks": [row, wake]}, plan)
        self.assertEqual({"wakeup_fallbacks": []}, retire_applied_fallbacks({"wakeup_fallbacks": []}))

    def test_planner_swaps_and_reports_the_released_placements(self):
        slots = load_slots(self.inventory)
        tags = load_tags(RELEASE / "enemy_tags.json")
        overrides = load_slot_overrides(RELEASE / "slot_policy.json")
        release = load_release_files([str(RELEASE / f"release_{name}.json")
                                      for name in ("contracts", "spawns", "chara", "wakeup", "scripted")])
        policies = {slot.key: apply_archetype_tag(classify_slot(slot, overrides, release),
                                                  tags.get(slot.archetype.key)) for slot in slots}
        swaps, _ = plan_swaps(slots, policies, tags, EnemizerConfig("12345"))
        swapped = {swap.logical_key for swap in swaps}
        self.assertLessEqual(fallbacks.RELEASED_KEYS, swapped)
        rows = fallbacks.fallback_rows(swaps, slots, release)
        self.assertEqual(sorted(fallbacks.RELEASED_KEYS), [row["logical_key"] for row in rows])
        # Without the tranche nothing is released or reported.
        release.pop("m24_00_00_00:c2730_0009")
        policies = {slot.key: apply_archetype_tag(classify_slot(slot, overrides, release),
                                                  tags.get(slot.archetype.key)) for slot in slots}
        swaps, _ = plan_swaps(slots, policies, tags, EnemizerConfig("12345"))
        self.assertNotIn("m24_00_00_00:c2730_0009", {swap.logical_key for swap in swaps})


if __name__ == "__main__":
    unittest.main()
