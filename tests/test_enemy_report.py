"""bb-archipelago#321: a player names a bad enemy swap without knowing an entity id."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bb_launcher.core import ENEMIZER_PLAN_NAME, SEED_MANIFEST_NAME, ValidationError, activate_build
from bb_launcher.enemy_report import (
    MAP_AREAS,
    ReportContext,
    area_key,
    area_name,
    areas_in_plan,
    format_report,
    load_context,
    rank_by_echoes,
    swap_rows,
    write_report,
)
from bb_launcher.workflow import LauncherSettings

from tests.test_launcher_core import make_build, make_install, sample_plan


def two_area_plan() -> dict:
    plan = sample_plan("seed:enemizer")
    first = plan["swaps"][0]
    second = json.loads(json.dumps(first))
    second["logical_key"] = "m22_00_00_00:c1170_0006"
    second["destination_keys"] = ["m22_00_00_00:c1170_0006", "m22_00_00_01:c1170_0006"]
    second["destinations"] = {
        "m22_00_00_00:c1170_0006": {"map_name": "m22_00_00_00", "entity_id": 2200610,
                                    "x": 5.0, "y": 6.0, "z": 7.0},
        "m22_00_00_01:c1170_0006": {"map_name": "m22_00_00_01", "entity_id": 2200610,
                                    "x": 5.0, "y": 6.0, "z": 7.0},
    }
    second["target"] = {"model_name": "c1240", "npc_param_id": 124412,
                        "think_param_id": 124400, "chara_init_id": 0}
    second["target_facts"] = {"name": "rabid dog", "echoes": 834, "hp": 80}
    second["target_tag"] = {"size_class": "M", "tier": "common",
                            "locomotion": "move_type_4", "scaling_hp": 2.1}
    second["warnings"] = []
    plan["swaps"].append(second)
    return plan


def context(plan: dict, **overrides) -> ReportContext:
    values = dict(
        cache_key="c" * 64,
        build_path=Path("build"),
        manifest={"enemizer": {"enabled": True, "seed": plan["seed"], "file_count": 2,
                               "plan": {"name": ENEMIZER_PLAN_NAME, "sha256": "d" * 64,
                                        "swap_count": len(plan["swaps"]),
                                        "options": plan["options"], "stress": plan["stress"]}}},
        plan=plan,
        seed="AP-seed-1",
        slot="Hunter",
        request_path="C:/seeds/Hunter.bbseed.json",
    )
    values.update(overrides)
    return ReportContext(**values)


class EnemyReportShapeTests(unittest.TestCase):
    def test_area_names_cover_every_fixed_map_the_planner_reads(self):
        self.assertEqual("m24_01", area_key("m24_01_00_11"))
        self.assertEqual("Central Yharnam", area_name("m24_01_00_11"))
        self.assertEqual("Fishing Hamlet", area_name("m36_00_00_00"))
        self.assertIn("unknown area m99_00", area_name("m99_00_00_00"))
        self.assertNotIn("m29_00", MAP_AREAS)  # chalice dungeons never enter the inventory

    def test_rows_fold_alternate_map_states_and_rank_by_echoes(self):
        rows = swap_rows(two_area_plan())
        self.assertEqual(2, len(rows))
        self.assertEqual(["m22_00_00_00", "m24_01_00_00"], [r.map_name for r in rows])
        self.assertEqual(("m22_00_00_00", "m22_00_00_01"), rows[0].map_states)
        self.assertEqual("c4060 / NpcParam 406000 (fishman large)", rows[1].now)
        self.assertEqual([("m22_00", "Hemwick Charnel Lane", 1), ("m24_01", "Central Yharnam", 1)],
                         areas_in_plan(two_area_plan()))
        ranked = rank_by_echoes(rows, 4700)
        self.assertEqual(406000, ranked[0].target_npc)

    def test_report_leads_with_the_reproduction_facts_and_the_echo_ranking(self):
        text = format_report(
            context(two_area_plan()), area="m24_01", echoes=4700, note="kept dying near the lamp",
            version="1.2.3", now=datetime(2026, 9, 4, 12, 0),
        )
        head = text.split("## ", 1)[0]
        for needle in (
            "- Launcher: 1.2.3",
            "- AP seed / slot: AP-seed-1 / Hunter",
            "- Enemy seed: seed:enemizer",
            "- Enemy options: tier mixing off, locomotion preserved off",
            "- Cache key: " + "c" * 64,
            "- Plan sha256: " + "d" * 64,
            "- Reported area: Central Yharnam",
            "- Echoes observed: 4700",
            "- Player note: kept dying near the lamp",
        ):
            self.assertIn(needle, head)
        self.assertIn("## Closest matches to 4700 echoes", text)
        ranking = text.split("## Closest matches to 4700 echoes")[1].split("## Swaps")[0]
        self.assertIn("| 1 | Central Yharnam | 2410100 | c4060 / NpcParam 406000 (fishman large) | 4514 |", ranking)
        self.assertIn("## Swaps in Central Yharnam (1 placements)", text)
        self.assertIn("- Swaps in this build: 2 placements (3 map-state copies)", text)
        self.assertNotIn("Hemwick", text.split("## Swaps in Central Yharnam")[1])
        self.assertIn("size-up at limit: +1", text)

    def test_report_without_an_area_lists_every_area_and_names_vanilla_ones(self):
        text = format_report(context(two_area_plan()), now=datetime(2026, 9, 4))
        self.assertIn("## Hemwick Charnel Lane (m22_00, 1 placements)", text)
        self.assertIn("| 2200610 | c1170_0006 | m22_00_00_00 +1 state |", text)
        self.assertIn("## Central Yharnam (m24_01, 1 placements)", text)
        self.assertIn("- Echoes observed: not given", text)
        vanilla = format_report(context(two_area_plan()), area="m27_00", now=datetime(2026, 9, 4))
        self.assertIn("No enemy in this area was randomized in this build", vanilla)

    def test_stress_profile_is_named_with_its_match_count(self):
        plan = two_area_plan()
        plan["stress"] = {"kind": "family", "argument": "c4060", "focus": "m24_01",
                          "description": "x", "matched": 1}
        text = format_report(context(plan), now=datetime(2026, 9, 4))
        self.assertIn("- Stress profile: family=c4060 in m24_01 (1 of 2 swaps embody it)", text)

    def test_write_report_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = write_report(tmp, "one\n", now=datetime(2026, 9, 4, 1, 2, 3))
            second = write_report(tmp, "two\n", now=datetime(2026, 9, 4, 1, 2, 3))
            self.assertEqual("enemy-reports", first.parent.name)
            self.assertNotEqual(first, second)
            self.assertEqual("one\n", first.read_text(encoding="utf-8"))

    def test_ai_evidence_uses_recorded_goals_and_filters_area(self):
        ctx = context(two_area_plan())
        ctx.manifest["enemizer"]["ai"] = {
            "applied": True, "plan_sha256": "d" * 64,
            "gameparam_sha256": "a" * 64, "paramdef_sha256": "b" * 64,
            "think_parameters": [{"think_param_id": 124400,
                                  "goals": [{"id": 900000, "logic": False}, {"id": 10000, "logic": True}]}],
            "maps": [
                {"map": "m22_00_00_00.luabnd.dcx", "missing_goals_before": 2,
                 "missing_goals_after": 0, "scripts_added": [{"file": "900000_battle.lua"}], "output_sha256": "e" * 64},
                {"map": "m24_01_00_00.luabnd.dcx", "output_sha256": "f" * 64},
            ],
        }
        ctx.manifest["files"] = [{"path": "dvdroot_ps4/script/m22_00_00_00.luabnd.dcx", "sha256": "e" * 64}]
        text = format_report(ctx, area="m22_00")
        self.assertIn("battle 900000, logic 10000", text)
        self.assertNotIn("battle 124400", text)
        self.assertIn("2 -> 0 | 1 | " + "e" * 64 + " | yes", text)
        self.assertNotIn("m24_01_00_00.luabnd.dcx", text)
        self.assertIn("not observed detection", text)
        ctx.manifest["enemizer"]["ai"]["plan_sha256"] = "0" * 64
        self.assertIn("does not match the retained plan", format_report(ctx))
        self.assertNotIn("battle 900000", format_report(ctx))

    def test_scaling_report_distinguishes_planned_from_written(self):
        plan = two_area_plan()
        plan["scaling"] = {"enabled": True, "changes": [{
            "logical_key": plan["swaps"][0]["logical_key"], "source_npc_param_id": 406000,
            "cloned_npc_param_id": 6000000, "minted_sp_effect_id": 60013,
            "hp_multiplier": 0.5, "attack_multiplier": 0.75, "defense_multiplier": 0.75,
        }]}
        self.assertIn("planned only; application not established", format_report(context(plan)))
        plan["scaling"]["applied"] = True
        text = format_report(context(plan), area="m24_01")
        self.assertIn("applied to build files (runtime unvalidated)", text)
        self.assertIn("406000 -> 6000000", text)
        self.assertIn("0.5 / 0.75 / 0.75", text)
        self.assertNotIn("406000 -> 6000000", format_report(context(plan), area="m22_00"))

    def test_echo_search_does_not_blame_other_maps_when_focus_has_no_swaps(self):
        text = format_report(context(two_area_plan()), area="m27_00", echoes=4700)
        self.assertNotIn("fishman large", text)
        self.assertIn("No enemy in this area was randomized", text)


class EnemyReportContextTests(unittest.TestCase):
    """The report reads the active overlay's retained plan and nothing else."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.install = make_install(self.root / "game")

    def tearDown(self):
        self.temporary.cleanup()

    def settings(self) -> LauncherSettings:
        return LauncherSettings(
            game_root=self.install.root,
            cache_root=self.root / "cache",
            ap_request=self.root / "missing-seed.bbseed.json",
            suppression_binder=self.root / "binder.dcx",
            suppression_manifest=self.root / "manifest.json",
            process_plan=self.root / "plan.json",
            state_root=self.root / "state",
        )

    def test_reads_the_active_builds_plan_and_falls_back_to_owner_identity(self):
        cache, build_path = make_build(self.root, "seed", b"content", with_maps=True)
        activate_build(self.install, build_path, process_is_running=lambda: False)
        loaded = load_context(self.settings())
        self.assertEqual(build_path, loaded.build_path)
        self.assertEqual(1, len(loaded.plan["swaps"]))
        self.assertEqual("seed", loaded.seed)
        text = format_report(loaded, area="m24_01", echoes=4514)
        self.assertIn("fishman large", text)
        self.assertIn("- Enemy seed: seed:enemizer", text)

    def test_names_the_remedy_when_no_overlay_or_no_enemizer_or_no_plan(self):
        with self.assertRaisesRegex(ValidationError, "Randomize & Launch first"):
            load_context(self.settings())
        cache, build_path = make_build(self.root, "plain", b"content")
        activate_build(self.install, build_path, process_is_running=lambda: False)
        with self.assertRaisesRegex(ValidationError, "enemy randomization off"):
            load_context(self.settings())
        cache, build_path = make_build(self.root, "old", b"content", with_maps=True)
        manifest_path = build_path / SEED_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["enemizer"]["plan"] = None
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (build_path / ENEMIZER_PLAN_NAME).unlink()
        activate_build(self.install, build_path, process_is_running=lambda: False)
        with self.assertRaisesRegex(ValidationError, "press Rebuild once"):
            load_context(self.settings())

    def test_changed_settings_request_cannot_relabel_the_active_seed(self):
        _cache, build_path = make_build(self.root, "active-seed", b"content", with_maps=True)
        activate_build(self.install, build_path, process_is_running=lambda: False)
        with patch("bb_launcher.enemy_report._request_identity", return_value={
            "seed": "another-seed", "slot": "Another Hunter", "path": "other.json",
        }):
            loaded = load_context(self.settings())
        self.assertEqual("active-seed", loaded.seed)
        self.assertEqual("Hunter", loaded.slot)
        self.assertEqual("not matched to the active overlay", loaded.request_path)


if __name__ == "__main__":
    unittest.main()
