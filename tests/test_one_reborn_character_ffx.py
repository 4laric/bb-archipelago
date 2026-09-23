import copy
import unittest
from unittest.mock import patch

from tools.bb_enemizer.one_reborn_character_ffx import character_ffx_plan


def actors():
    result = []
    for state, source_state in (("00", "00"), ("01", "01"), ("11", "00")):
        for index, model in enumerate(("c5070", "c5071", "c5072", *(["c1050"] * 7))):
            result.append({
                "source_map": "m28_00_00_" + source_state,
                "source_part": f"{model}_{index:04}",
                "source_entity_id": 2800800 + index,
                "source_archetype": {"model_name": model},
                "destination_map": "m24_01_00_" + state,
                "destination_part": f"replacement_{index}",
                "destination_entity_id": 984100 + index,
            })
    return result


class OneRebornCharacterFfxTests(unittest.TestCase):
    def test_all_twenty_original_bank_roots_have_typed_actor_bound_delivery(self):
        plan = character_ffx_plan(actors(), "cleric-beast")
        self.assertEqual(18, len(plan["boss_character_ffx_requirements"]))
        self.assertEqual(27, len(plan["boss_character_ffx_bank_requirements"]))
        merge, = plan["boss_ffx_merges"]
        self.assertEqual("frpg_sfxbnd_m28.ffxbnd.dcx", merge["source_file"])
        self.assertEqual("frpg_sfxbnd_m24_01.ffxbnd.dcx", merge["destination_file"])
        self.assertEqual([610500, 610502, 610505, 610506, 610507, 610510, 610550,
                          650702, 650705, 650710, 650715, 650718, 650719,
                          650740, 650741, 650742, 650751, 650790, 1507401, 1507601],
                         merge["required_effect_ids"])
        proofs = {(r["source_map"], r["source_part"], r["source_entity_id"]): r
                  for r in plan["boss_character_ffx_requirements"]}
        for delivery in plan["boss_character_ffx_bank_requirements"]:
            proof = proofs[(delivery["source_map"], delivery["source_part"], delivery["source_entity_id"])]
            for root in delivery["roots"]:
                self.assertEqual(proof["source_tae_entry_id"], root["source_tae_entry_id"])
                self.assertIn(root["witness"], proof["typed_event_witnesses"])

    def test_partial_or_duplicate_actor_delivery_is_refused(self):
        incomplete = actors()[:-1]
        with self.assertRaisesRegex(ValueError, "complete multipart roster"):
            character_ffx_plan(incomplete, "cleric-beast")
        duplicate = actors()
        duplicate[-1] = copy.deepcopy(duplicate[-2])
        with self.assertRaisesRegex(ValueError, "duplicate.*destination"):
            character_ffx_plan(duplicate, "cleric-beast")

    def test_proof_byte_drift_is_refused(self):
        with patch("pathlib.Path.read_bytes", return_value=b"{}"):
            with self.assertRaisesRegex(ValueError, "proof resource changed"):
                character_ffx_plan(actors(), "cleric-beast")

    def test_calls_do_not_share_mutable_witnesses(self):
        first = character_ffx_plan(actors(), "cleric-beast")
        first["boss_character_ffx_bank_requirements"][0]["roots"][0]["witness"]["effect_id"] = -1
        second = character_ffx_plan(actors(), "cleric-beast")
        self.assertEqual(650702, second["boss_character_ffx_bank_requirements"][0]["roots"][0]["witness"]["effect_id"])


if __name__ == "__main__":
    unittest.main()
