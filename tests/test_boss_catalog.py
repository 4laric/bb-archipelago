"""Boss contracts must distinguish completion actors, proxies and game evidence."""
import json
import unittest
from pathlib import Path

from tools.bb_enemizer.bosses import build_boss_catalog, parse_events
from tools.bb_enemizer.model import Archetype, Slot
from tools.build_boss_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def slot(entity, suffix="00"):
    return Slot("m99_00_00_" + suffix, "m99_00_00_" + suffix, f"c1000_{entity}",
                entity, 0, "collision", False, 1, 2, 3, Archetype("c1000", 10, 20, 0))


class BossParsingTests(unittest.TestCase):
    def test_comments_strings_nested_calls_and_line_references(self):
        script = '''// $Event(9, Default, function() { HandleBossDefeat(9); });
$Event(123, Default, function() {
    var text = "HandleBossDefeat(999) }";
    /* HandleBossDefeat(888); } */
    WaitFor(CharacterDead(10) && (HPRatio(11) <= 0));
    HandleBossDefeat(12);
});'''
        events = parse_events(script)
        self.assertEqual([123], [event.event_id for event in events])
        calls = events[0].calls
        defeat = [call for call in calls if call.operation == "HandleBossDefeat"]
        self.assertEqual(1, len(defeat))
        self.assertEqual((12, 6), (defeat[0].integer(0), defeat[0].line))
        self.assertEqual([10], [c.integer(0) for c in calls if c.operation == "CharacterDead"])
        with self.assertRaisesRegex(ValueError, "unclosed"):
            parse_events("$Event(1, Default, function() { HandleBossDefeat(2);")

    def test_distinct_completion_proxy_and_healthbar_actors_and_alternates(self):
        script = '''$Event(123, Default, function() {
    if (ThisEvent()) { EndEvent(); }
    WaitFor(CharacterDead(10) && HPRatio(11) <= 0);
    HandleBossDefeat(12);
});
$Event(456, Default, function(animationId) {
    EndIf(EventFlag(123));
    DisplayBossHealthBar(Enabled, 11, 0, 999);
    ForceAnimationPlayback(11, animationId, false, false, false);
});
$Event(0, Default, function() {
    $InitializeEvent(0, 456, 7001);
    DisplayBossHealthBar(Enabled, 9999, 0, 999);
});'''
        result = build_boss_catalog({"m99_00_00_00.emevd.dcx.js": script},
                                    [slot(10), slot(10, "01"), slot(11)], {"boss_test": 123})
        record = result["encounters"][0]
        self.assertEqual([12], record["defeat_entities"])
        actors = {a["entity_id"]: a for a in record["actors"]}
        self.assertEqual({10, 11, 12}, set(actors))
        self.assertEqual(2, len(actors[10]["placements"]))
        self.assertIn("health_bar", actors[11]["roles"])
        self.assertEqual({10: 2, 11: 1, 12: 0}, {key: len(value["placements"]) for key, value in actors.items()})
        self.assertIn("actor has no fixed-map placement", record["gaps"])
        self.assertEqual({"animationId": "7001"}, record["actor_initializers"][0]["bindings"])
        self.assertFalse(record["approved_for_randomization"])
        self.assertFalse(result["policy_changed"])

    def test_unresolved_operands_and_duplicate_definitions_are_not_safety(self):
        script = '''$Event(123, Default, function(chr) { HandleBossDefeat(chr); });
$Event(123, Default, function() { HandleBossDefeat(10); });'''
        result = build_boss_catalog({"m99_00_00_00.emevd.dcx.js": script}, [slot(10)], {"boss_test": 123})
        self.assertEqual(1, len(result["unresolved_defeats"]))
        self.assertIn("ambiguous terminal event definition", result["encounters"][0]["gaps"])
        self.assertFalse(result["encounters"][0]["runtime_validated"])


class OriginalBossCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build(ROOT / "research/bb_inputs.db")
        cls.by_ap = {key: record for record in cls.catalog["encounters"] for key in record["ap_locations"]}

    def test_all_22_ap_bosses_have_nonempty_original_witnesses(self):
        self.assertEqual(22, len(self.catalog["encounters"]))
        self.assertEqual(22, len(self.by_ap))
        self.assertEqual((22, 0), (len(self.by_ap), len(self.catalog["unmatched_ap_bindings"])))
        for record in self.catalog["encounters"]:
            self.assertTrue(record["defeat_entities"])
            self.assertTrue(record["actor_references"])
            self.assertFalse(record["approved_for_randomization"])
        # The corpus does not use the same self-read shape for every boss.
        self.assertEqual({"boss_gehrman", "boss_moon_presence", "boss_ludwig"}, {
            key for key, record in self.by_ap.items() if not record["terminal_uses_this_event"]
        })
        self.assertEqual(12, self.catalog["summary"]["single_actor"])
        self.assertEqual(10, self.catalog["summary"]["multiple_actors"])

    def test_witches_shadows_and_mergo_do_not_collapse_into_one_actor(self):
        witch = self.by_ap["boss_witch_of_hemwick"]
        self.assertEqual([2200800], witch["defeat_entities"])
        self.assertEqual({2200800, 2200801}, {a["entity_id"] for a in witch["actors"]})
        shadows = self.by_ap["boss_shadows_of_yharnam"]
        self.assertEqual({2700800, 2700801, 2700802}, {a["entity_id"] for a in shadows["actors"]})
        mergo = self.by_ap["boss_mergos_wet_nurse"]
        self.assertEqual([2600803], mergo["defeat_entities"])
        actor = next(a for a in mergo["actors"] if a["entity_id"] == 2600802)
        self.assertIn("health_bar", actor["roles"])
        self.assertIn("completion_test", actor["roles"])

    def test_cleric_limb_event_has_bound_animation_arguments(self):
        cleric = self.by_ap["boss_cleric_beast"]
        calls = [i for i in cleric["actor_initializers"] if i["callee_event"] == 12414710]
        self.assertEqual(['8020', '8000', '8010', '8030', '8040'],
                         [call["bindings"]["animationId"] for call in calls])
        self.assertEqual(['local_parameter_binding'] * 5, [call["resolution"] for call in calls])

    def test_generated_catalog_is_reproducible(self):
        committed = json.loads((ROOT / "research/enemizer/boss_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, self.catalog)


if __name__ == "__main__":
    unittest.main()
