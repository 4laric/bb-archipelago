import csv
import io
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from worlds.bloodborne.data import LOCATIONS, ONE_TIME_ENEMY_LOCATION_KEYS
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class OneTimeEnemyEvidenceTests(unittest.TestCase):
    def test_initial_tranche_contains_only_yurie(self):
        self.assertEqual({"hunter_yurie"}, set(ONE_TIME_ENEMY_LOCATION_KEYS))
        location = next(row for row in LOCATIONS if row.key == "hunter_yurie")
        self.assertEqual("Byrgenwerth", location.region)
        self.assertEqual(13200500, LOCATION_BINDINGS[location.key].event_flag)

    def test_yurie_has_a_dedicated_death_event(self):
        event = read_blob(
            BUNDLE, "event/m32_00_00_00.emevd.dcx.js"
        ).decode("utf-8")
        self.assertIn("$InitializeEvent(0, 13200500, 3200110);", event)
        start = event.index("$Event(13200500")
        body = event[start:event.index("});", start) + 3]
        self.assertIn("if (ThisEventSlot())", body)
        self.assertIn("WaitFor(CharacterDead(chrEntityId));", body)

    def test_yurie_is_a_unique_non_respawning_msb_placement(self):
        msb_rows = csv.DictReader(io.StringIO(read_blob(
            BUNDLE, "mined/msb_enemies.tsv"
        ).decode("utf-8")), delimiter="\t")
        placements = [row for row in msb_rows if row["part_entity_id"] == "3200110"]
        # The same logical placement exists in the two vanilla map variants.
        self.assertEqual({"m32_00_00_00", "m32_00_00_01"},
                         {row["map_name"] for row in placements})
        self.assertEqual({"c0000_0002"}, {row["part_name"] for row in placements})
        self.assertEqual({"6450"}, {row["npc_param_id"] for row in placements})

        npc_rows = csv.DictReader(io.StringIO(read_blob(
            BUNDLE, "params/NpcParam.csv"
        ).decode("utf-8")))
        yurie = next(row for row in npc_rows if row["ID"] == "6450")
        self.assertEqual("1", yurie["disableRespawn"])
        self.assertIn("聖歌隊NPC", yurie["Name"])


try:
    from worlds.bloodborne import BloodborneOptions, BloodborneWorld
except ImportError:
    BloodborneOptions = BloodborneWorld = None


@unittest.skipIf(BloodborneWorld is None, "requires Archipelago core")
class OneTimeEnemyOptionTests(unittest.TestCase):
    class _Options:
        include_dlc = 1
        alternate_hypogean_gaol_routes = 0

        def __init__(self, enabled):
            self.one_time_enemy_checks = enabled

    def _keys(self, enabled):
        world = BloodborneWorld.__new__(BloodborneWorld)
        world.options = self._Options(enabled)
        return {row.key for row in world._active_locations()}

    def test_option_defaults_off(self):
        option = BloodborneOptions.type_hints["one_time_enemy_checks"]
        self.assertEqual(0, option.default)
        self.assertIn("One-Time", option.display_name)

    def test_option_off_preserves_parity_and_on_adds_exact_tranche(self):
        off = self._keys(0)
        on = self._keys(1)
        self.assertFalse(off & ONE_TIME_ENEMY_LOCATION_KEYS)
        self.assertEqual(set(ONE_TIME_ENEMY_LOCATION_KEYS), on - off)


if __name__ == "__main__":
    unittest.main()
