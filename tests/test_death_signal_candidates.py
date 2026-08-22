"""Witnesses for the death-signal candidate narrowing (issue #78).

The load-bearing claim is a negative one: no EMEVD event flag is written on
every player death, so the DeathLink send signal has to be a live state read.
A negative claim needs exact witnesses, not vibes — if the corpus grows a
fourth `CharacterDead(10000)` site or an unconditional death flag, these tests
break loudly instead of letting the runbook go stale.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.death_signal_candidates import (
    ABSENT_INSTRUCTIONS, RESPAWN_WARP, code_occurrences, death_speffects,
    load_scripts, player_death_sites,
)


BUNDLE = Path(__file__).resolve().parents[1] / "research" / "bb_inputs.db"


class DeathSignalCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts = load_scripts(BUNDLE)
        cls.sites = player_death_sites(cls.scripts)
        cls.player_speffects, cls.set_aside_speffects = death_speffects(BUNDLE)

    def site(self, event_id: int):
        matches = [site for site in self.sites if site.event_id == event_id]
        self.assertEqual(1, len(matches))
        return matches[0]

    def test_exactly_three_player_death_sites_and_all_in_common(self):
        self.assertEqual(3, len(self.sites))
        self.assertEqual({9400, 9404, 9782}, {site.event_id for site in self.sites})
        self.assertEqual({"event/common.emevd.dcx.js"}, {site.path for site in self.sites})

    def test_no_event_writes_a_flag_unconditionally_on_death(self):
        self.assertEqual(0, len(self.site(9400).flags_after))
        self.assertEqual(0, len(self.site(9404).flags_after))
        spider_man = self.site(9782)
        self.assertEqual(((1438, "ON"), (1439, "OFF")), spider_man.flags_after)
        # ... and that write is quest-gated, not a general death flag: the wait
        # also requires carrying Goods 4310 or flag 1431 already set.
        self.assertEqual(
            ("CharacterDead", "EventFlag", "PlayerHasItem", "PlayerInMap"),
            spider_man.conditions,
        )

    def test_first_death_flag_is_set_before_the_death_wait(self):
        first_death = self.site(9400)
        self.assertEqual(((9402, "ON"),), first_death.flags_before)
        self.assertEqual(("CharacterDead",), first_death.conditions)

    def test_insight_death_wait_carries_no_flag_write_at_all(self):
        insight_death = self.site(9404)
        self.assertEqual(("CharacterDead", "EventFlag", "PlayerInsightAmount"),
                         insight_death.conditions)
        self.assertEqual(0, len(insight_death.flags_before))
        self.assertEqual(0, len(insight_death.flags_after))

    def test_death_respawn_points(self):
        self.assertEqual((2102962,), self.site(9400).respawn_points)
        self.assertEqual((2102961,), self.site(9404).respawn_points)
        self.assertEqual(0, len(self.site(9782).respawn_points))

    def test_player_death_speffect_candidates(self):
        self.assertEqual({
            560: "死んだとき復活",
            5904: "仮死亡遷移",
            5905: "仮死亡状態維持",
            5912: "仮死亡遷移_ダンジョン用",
            5913: "仮死亡状態維持_ダンジョン用",
            5914: "仮死亡状態維持（イベント用）",
            5915: "檻中専用死亡遷移",
        }, self.player_speffects)

    def test_death_judgment_rows_are_set_aside(self):
        self.assertEqual({4611, 4672, 5626, 6170, 6171, 6172},
                         set(self.set_aside_speffects))

    def test_bloodstain_is_engine_side_and_respawn_is_scripted(self):
        for token in ABSENT_INSTRUCTIONS:
            self.assertEqual(0, code_occurrences(self.scripts, token))
        self.assertEqual(22, code_occurrences(self.scripts, RESPAWN_WARP))


if __name__ == "__main__":
    unittest.main()
