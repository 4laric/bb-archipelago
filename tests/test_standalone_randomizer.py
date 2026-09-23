from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tools.bb_standalone import StandaloneOptions, generate_plan, verify_plan
from tools.bb_standalone.catalog import (
    build_catalog,
    catalog_sha256,
    derive_catalog,
    load_catalog_document,
)
from tools.bb_standalone.generate import _world
from tools.bb_standalone.schema import GAMEPARAM_PATH, PARAMDEF_PATH, PLAN_FORMAT

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASHES = {GAMEPARAM_PATH: "a" * 64, PARAMDEF_PATH: "b" * 64}


class StandaloneRandomizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = generate_plan("standalone-test", SOURCE_HASHES)

    def test_default_plan_is_deterministic_complete_and_has_no_ap_effect_rewards(self):
        again = generate_plan("standalone-test", SOURCE_HASHES)
        self.assertEqual(self.plan, again)
        self.assertEqual(PLAN_FORMAT, self.plan["format"])
        self.assertEqual(
            {
                "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx",
                "dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx",
            },
            set(self.plan["source_hashes"]),
        )
        self.assertEqual(503, len(self.plan["placements"]))
        self.assertEqual(0, len(self.plan["unsupported"]))
        self.assertEqual(
            {"fixed_progression", "completion_only"},
            {row["status"] for row in self.plan["fixed_progression"]},
        )
        self.assertEqual(
            {"interaction_laurences_skull", "boss_moon_presence"},
            {row["location_key"] for row in self.plan["fixed_progression"]},
        )
        self.assertNotIn(
            "forbidden_woods_password",
            {row["item_key"] for row in self.plan["placements"]},
        )
        categories = Counter(
            row["reward"]["item_category"] for row in self.plan["placements"]
        )
        self.assertGreater(categories[0], 0)
        self.assertGreater(categories[4], 0)
        self.assertGreater(categories[8], 0)
        self.assertNotIn(255, categories)

    def test_original_indirect_routes_distinguish_alternatives_and_retired_awards(self):
        rows = {row["location_key"]: row for row in load_catalog_document()["entries"]}
        paarl = rows["boss_darkbeast_paarl"]["targets"]
        self.assertEqual(
            [(50_800_000, "delivery"), (50_800_005, "alternative")],
            [(row["item_lot_id"], row["role"]) for row in paarl],
        )
        rom = rows["boss_rom"]["targets"]
        self.assertEqual(
            [(51_001_900, "delivery"), (3_200_800, "retire")],
            [(row["item_lot_id"], row["role"]) for row in rom],
        )
        crow = rows["award_crow_hunter_badge"]["targets"]
        self.assertEqual(3, len(crow))
        self.assertEqual(1, sum(row["role"] == "delivery" for row in crow))
        self.assertEqual(2, sum(row["role"] == "alternative" for row in crow))

    def test_every_default_and_dlc_location_has_an_explicit_catalog_disposition(self):
        witnessed = 0
        for options in (StandaloneOptions(), StandaloneOptions(include_dlc=True)):
            _world_module, locations, *_rest = _world(options)
            catalog = build_catalog(locations)
            self.assertEqual(len(locations), len(catalog))
            self.assertFalse([row for row in catalog if row.status == "unsupported"])
            witnessed += sum(row.status == "placeable" for row in catalog)
        self.assertGreater(witnessed, 1_000)

    def test_tracked_catalog_matches_original_source_derivation(self):
        import worlds.bloodborne as world

        document = load_catalog_document()
        self.assertEqual(
            "8cf1c60fbebc734dfcccd02d2d2fb98b8b5c386cc3a0d4722b9b9e9fc22486be",
            catalog_sha256(),
        )
        derived = [
            entry.as_dict() for entry in derive_catalog(world.ALL_NETWORK_LOCATIONS)
        ]
        # Conditions are catalog selection metadata; source target derivation
        # is compared separately so neither side can bless the other.
        tracked = []
        for row in document["entries"]:
            row = dict(row)
            row.pop("when", None)
            tracked.append(row)
        self.assertEqual(658, len(derived))
        self.assertEqual(derived, tracked)
        self.assertGreater(len(document["items"]), 100)

    def test_opt_in_one_time_enemy_without_an_award_route_is_refused_precisely(self):
        with self.assertRaisesRegex(
            ValueError,
            "active standalone locations lack native award targets: hunter_yurie",
        ):
            generate_plan(
                "unsupported-one-time",
                SOURCE_HASHES,
                StandaloneOptions(one_time_enemy_checks=True),
            )

    def test_sphere_replay_reaches_every_placement_and_all_three_goals(self):
        counts = []
        for goal in ("submit_to_gehrman", "refuse_gehrman", "moon_presence"):
            plan = generate_plan(
                f"goal-{goal}", SOURCE_HASHES, StandaloneOptions(goal=goal)
            )
            counts.append(plan["verification"]["reachable_placements"])
            self.assertEqual(len(plan["placements"]), counts[-1])
            self.assertEqual(
                {
                    "submit_to_gehrman": "boss_mergos_wet_nurse",
                    "refuse_gehrman": "boss_gehrman",
                    "moon_presence": "boss_moon_presence",
                }[goal],
                plan["verification"]["goal_location"],
            )
        self.assertEqual([503, 503, 503], counts)

    def test_plan_validation_rejects_unsupported_rows_duplicate_targets_and_bad_hashes(
        self,
    ):
        unsupported = copy.deepcopy(self.plan)
        unsupported["unsupported"] = [{"location_key": "x", "reason": "test"}]
        with self.assertRaisesRegex(ValueError, "unsupported active locations"):
            verify_plan(unsupported)

        duplicate = copy.deepcopy(self.plan)
        duplicate["placements"][1]["award_targets"][0] = copy.deepcopy(
            duplicate["placements"][0]["award_targets"][0]
        )
        with self.assertRaisesRegex(
            ValueError, "award targets do not match the catalog"
        ):
            verify_plan(duplicate)

        changed_reward = copy.deepcopy(self.plan)
        changed_reward["placements"][0]["reward"]["quantity"] += 1
        with self.assertRaisesRegex(ValueError, "reward does not match catalog item"):
            verify_plan(changed_reward)

        missing_location = copy.deepcopy(self.plan)
        missing_location["placements"].pop()
        with self.assertRaisesRegex(ValueError, "placement location set differs"):
            verify_plan(missing_location)

        with self.assertRaisesRegex(ValueError, "source_hashes must pin"):
            generate_plan("missing-source", {})

    def test_cli_runs_without_archipelago_and_emits_the_same_valid_plan(self):
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            hashes = temp / "hashes.json"
            output = temp / "plan.json"
            hashes.write_text(json.dumps(SOURCE_HASHES), encoding="utf-8")
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-m",
                    "tools.bb_standalone",
                    "--seed",
                    "standalone-test",
                    "--source-hashes",
                    str(hashes),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            emitted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(self.plan, emitted)
            self.assertNotIn("BaseClasses", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
