from pathlib import Path
import unittest

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.chalice_rom import recipes, CLEANUP, RETIRED


class ChaliceRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = Path(__file__).resolve().parents[1] / 'research/bb_inputs.db'
        cls.destination = read_blob(bundle, 'event/m32_00_00_00.emevd.dcx.js').decode('utf-8-sig')
        cls.source = read_blob(bundle, 'event/m29.emevd.dcx.js').decode('utf-8-sig')

    def test_all_three_donors_keep_progression_and_retire_spiders(self):
        original = event_blocks(self.destination)
        for recipe in recipes():
            with self.subTest(donor=recipe.donor.key):
                patched = event_blocks(recipe.patch(self.destination, self.source))
                for event in (13201800, 13201801, 13201802, 13201803, 13201804,
                              13204805, 13204820, 13204821, 13204830, 13204831,
                              13204832, 13204833, 13204834):
                    self.assertEqual(patched[event], original[event])
                for event in RETIRED:
                    self.assertIn('EndEvent();', patched[event])
                    self.assertLess(len(patched[event]), len(original[event]))
                self.assertEqual(patched[CLEANUP].count('ChangeCharacterEnableState('), 30)
                self.assertEqual(patched[CLEANUP].count('ForceCharacterDeath('), 30)
                self.assertLess(patched[CLEANUP].index('WaitFor(EventFlag(13201800))'),
                                patched[CLEANUP].index('ForceCharacterDeath('))
                self.assertIn(f', 0, {recipe.donor.health_name_id});', patched[13204802])
                self.assertIn('CharacterHasEventMessage(3200800, 500)', patched[13204803])
                self.assertEqual('7001' in patched[13204802], recipe.donor.key != 'keeper-of-old-lords')

    def test_destination_drift_refused(self):
        with self.assertRaisesRegex(ValueError, 'unsupported original Rom arena'):
            recipes()[0].patch(self.destination.replace('3200800', '3200809'), self.source)


if __name__ == '__main__':
    unittest.main()
