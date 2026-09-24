import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.bb_enemizer.chalice_recipes import chalice_recipes, source_manifest, validate_original_source
from tools.bb_enemizer.chalice_character_ffx import character_ffx_plan
from tools.build_boss_encounters import CHALICE_PACKAGES, reviewed_compatibility


class ChaliceIntegrationTests(unittest.TestCase):
    def test_nine_explicit_variants_do_not_expand_reviewed_pool(self):
        routes = chalice_recipes()
        self.assertEqual(len(routes), 9)
        self.assertEqual({arena for arena, donor in routes}, {'cleric-beast'})
        self.assertEqual({donor for arena, donor in routes}, set(CHALICE_PACKAGES))
        reviewed = reviewed_compatibility()
        self.assertEqual(len(reviewed), 22)
        self.assertFalse(set(CHALICE_PACKAGES) & set(reviewed))
        self.assertTrue(all(not set(donors) & set(CHALICE_PACKAGES)
                            for donors in reviewed.values()))

    def test_original_constructor_is_required_and_hash_checked(self):
        manifest = source_manifest('pthumerian-elder')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'constructor provenance drift'):
                validate_original_source(root, 'pthumerian-elder')
            source = root / manifest['event_file']
            source.parent.mkdir(parents=True)
            source.write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError, 'constructor provenance drift'):
                validate_original_source(root, 'pthumerian-elder')

    def test_character_roots_bind_both_banks_and_all_cleric_states(self):
        for suffix in ('00', '01', '02'):
            actor = {
                'source_map': 'm29_01_11_00', 'source_part': 'c5010_0000',
                'source_entity_id': 2900100,
                'source_archetype': {'model_name': 'c5010'},
                'destination_map': 'm24_01_00_' + suffix,
                'destination_part': 'c3010_0000', 'destination_entity_id': 2410800,
            }
            plan = character_ffx_plan(actor, 'cleric-beast')
            banks = plan['boss_character_ffx_bank_requirements']
            self.assertEqual(len(banks), 2)
            self.assertEqual({row['source_ffx_file'] for row in banks}, {
                'frpg_sfxbnd_m29a.ffxbnd.dcx', 'frpg_sfxbnd_m29c.ffxbnd.dcx'})
            self.assertTrue(all(row['destination_map'] == actor['destination_map'] for row in banks))
            declared = [root['witness']['effect_id'] for bank in banks for root in bank['roots']]
            self.assertEqual(len(declared), len(set(declared)))
            self.assertEqual(plan['chalice_character_effect_limits']['runtime_bank_precedence'],
                             'not-validated')
            with self.assertRaisesRegex(ValueError, 'pinned to Cleric'):
                character_ffx_plan(actor, 'lady-maria')

    def test_character_proof_cannot_be_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / 'proof.json'
            altered.write_text(json.dumps({}), encoding='utf-8')
            with patch('tools.bb_enemizer.chalice_character_ffx.PROOF_FILE', altered):
                with self.assertRaisesRegex(ValueError, 'proof resource changed'):
                    character_ffx_plan({'destination_map': 'm24_01_00_00'}, 'cleric-beast')


if __name__ == '__main__':
    unittest.main()
