import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_activation import ACTIVATION_POLICIES, guard_shuffled_activation
from tools.bb_enemizer.boss_entrances import ENTRANCE_POLICIES
from tools.bb_enemizer.encounter_recipes import reusable_recipes

BUNDLE = Path(__file__).resolve().parents[1] / "research/bb_inputs.db"


class BossActivationTests(unittest.TestCase):
    def test_every_destination_uses_its_own_pinned_music_bounds(self):
        self.assertEqual(set(ENTRANCE_POLICIES), set(ACTIVATION_POLICIES))
        for key, p in ACTIVATION_POLICIES.items():
            with self.subTest(arena=key):
                original = read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
                blocks = event_blocks(original)
                self.assertEqual(hashlib.sha256(blocks[p.music_event].encode()).hexdigest(),
                                 p.source_sha256)
                self.assertGreaterEqual(blocks[p.music_event].count(p.witnesses[0]), 1)
                # A changed label represents an imported actor, including arenas
                # which share a map with a second boss and its completion events.
                result = guard_shuffled_activation(SimpleNamespace(key=key), original, original)
                after = event_blocks(result)
                self.assertIn("WaitFor(" + p.predicate + ");", after[p.health_event])
                for eid in blocks:
                    if eid not in (0, p.health_event):
                        self.assertEqual(blocks[eid], after[eid])
                self.assertEqual(result, guard_shuffled_activation(SimpleNamespace(key=key), original, result))

    def test_real_gascoigne_phase_and_resume_paths_and_neighbor_stay_separate(self):
        recipe = reusable_recipes()[("blood-starved-beast", "father-gascoigne")]
        original = read_blob(BUNDLE, "event/" + recipe.arena.event_file).decode("utf-8-sig")
        donor = read_blob(BUNDLE, "event/" + recipe.donor.event_file).decode("utf-8-sig")
        patched = recipe.patch(original, donor)
        result = guard_shuffled_activation(recipe.arena, original, patched)
        blocks = event_blocks(result)
        gate = "WaitFor(PlayerInMap(23, 0) && InArea(10000, 2302801));"
        for eid in (12304802, 12414780):
            lines = blocks[eid].splitlines()
            for i, line in enumerate(lines):
                if "DisplayBossHealthBar(Enabled," in line:
                    self.assertEqual(gate if eid == 12304802 else "WaitFor(EventFlag(12304980) && PlayerInMap(23, 0));", lines[i - 1].strip())
        # Paarl's separate health/controller and BSB's reward logic are preserved.
        before = event_blocks(patched)
        for eid in (12304702, 12301800, 12301803):
            self.assertEqual(before[eid], blocks[eid])

    def test_entry_latches_are_new_live_bank_ids_and_require_start_and_room(self):
        import re
        from tools.bb_inputs import read_prefix
        corpus = "\n".join(v.decode("utf-8-sig") for v in read_prefix(BUNDLE, "event/").values())
        flags = [p.entry_event for p in ACTIVATION_POLICIES.values()]
        self.assertEqual(len(flags), len(set(flags)))
        for key, p in ACTIVATION_POLICIES.items():
            self.assertEqual(p.health_event // 1000, p.entry_event // 1000)
            self.assertNotRegex(corpus, rf"(?<!\w){p.entry_event}(?!\w)")
            original = read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
            result = event_blocks(guard_shuffled_activation(SimpleNamespace(key=key), original, original))
            self.assertIn(f"SetEventFlag({p.entry_event}, OFF);", result[0])
            self.assertIn(f"WaitFor(EventFlag({p.start_flag}) && ({p.predicate}));", result[p.entry_event])

    def test_ebrietas_logarius_phase_rejects_unloaded_zero_but_keeps_death_checks(self):
        r = reusable_recipes()[("martyr-logarius", "ebrietas")]
        source = lambda f: read_blob(BUNDLE, "event/" + f).decode("utf-8-sig")
        original = source(r.arena.event_file)
        patched = r.patch(original, source(r.donor.event_file))
        before = event_blocks(patched)
        after = event_blocks(guard_shuffled_activation(r.arena, original, patched))
        self.assertIn("EventFlag(12504980) && CharacterBackreadStatus(2500800) "
                      "&& HPRatio(2500800) > 0 && HPRatio(2500800) < 0.5", after[12504600])
        self.assertIn("HPRatio(2500800) <= 0", after[12504620])
        self.assertEqual(before[12501800], after[12501800])

    def test_shared_map_latches_compose_without_reordering_resets(self):
        from tools.bb_enemizer.boss_pool import compose_event_patches
        p = ACTIVATION_POLICIES["blood-starved-beast"]
        source = read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
        patches = [guard_shuffled_activation(SimpleNamespace(key=key), source, source)
                   for key in ("blood-starved-beast", "darkbeast-paarl")]
        result = event_blocks(compose_event_patches(source, patches, [12301800, 12301700]))
        for flag in (12304980, 12304981):
            self.assertIn(flag, result)
            self.assertLess(result[0].index(f"SetEventFlag({flag}, OFF)"),
                            result[0].index(f"$InitializeEvent(0, {flag})"))

    def test_changed_location_source_fails_closed(self):
        p = ACTIVATION_POLICIES["blood-starved-beast"]
        original = read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
        with self.assertRaisesRegex(ValueError, "source drift"):
            guard_shuffled_activation(SimpleNamespace(key="blood-starved-beast"),
                                      original.replace("2302801", "2302999"), original)


class EntranceMotionAuditTests(unittest.TestCase):
    def test_cleric_donor_choreography_does_not_keep_elevated_warp(self):
        from tools.bb_enemizer.boss_entrances import strip_destination_entrance_animations
        r = reusable_recipes()[("cleric-beast", "amygdala")]
        source = lambda f: read_blob(BUNDLE, "event/" + f).decode("utf-8-sig")
        original = source(r.arena.event_file)
        patched = r.patch(original, source(r.donor.event_file))
        before = event_blocks(patched)[12411702]
        self.assertIn("2412831", before)
        after = event_blocks(strip_destination_entrance_animations(
            "cleric-beast", original, patched))[12411702]
        self.assertNotIn("2412831", after)
        self.assertIn("ForceAnimationPlayback(2410800, 7006", after)
        self.assertIn("SetCharacterGravity(2410800, Enabled)", after)

    def test_cleric_grounded_and_chalice_forms_with_unchanged_physics(self):
        from tools.bb_enemizer.boss_entrances import strip_destination_entrance_animations
        from tools.bb_enemizer.chalice_recipes import chalice_recipes
        routes = {**reusable_recipes(), **chalice_recipes()}
        for donor in ("darkbeast-paarl", "keeper-of-old-lords",
                      "pthumerian-descendant", "pthumerian-elder"):
            with self.subTest(donor=donor):
                r = routes[("cleric-beast", donor)]
                source = lambda f: read_blob(BUNDLE, "event/" + f).decode("utf-8-sig")
                original = source(r.arena.event_file)
                patched = r.patch(original, source(r.donor.event_file))
                result = strip_destination_entrance_animations("cleric-beast", original, patched)
                body = event_blocks(result)[12411702]
                self.assertNotIn("2412831", body)
                self.assertIn("SetEventFlag(12414700, ON)", body)
                self.assertIn("ChangeCharacterEnableState(2410800, Enabled)", body)
                self.assertEqual(result, strip_destination_entrance_animations(
                    "cleric-beast", original, result))

    def test_original_model_motions_removed_but_ground_warps_and_rewards_kept(self):
        import re
        from tools.bb_enemizer.boss_entrances import strip_destination_entrance_animations
        for key, p in ACTIVATION_POLICIES.items():
            with self.subTest(arena=key):
                original = read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
                # Apply to originals to witness every entrance, even if a donor
                # adapter had already removed some of these model motions.
                patched = strip_destination_entrance_animations(key, original, original)
                before, after = event_blocks(original), event_blocks(patched)
                eid = ENTRANCE_POLICIES[key].event_id
                self.assertNotRegex(after[eid], rf"ForceAnimationPlayback\({p.actor},")
                for other in before:
                    if other != eid:
                        self.assertEqual(before[other], after[other])
                if key == "cleric-beast":
                    self.assertNotIn("2412831", after[eid])
                if key == "laurence":
                    self.assertIn("IssueShortWarpRequest(3400850, TargetEntityType.Area, 3402853", after[eid])
                    self.assertIn("SetCharacterGravity(3400850, Enabled)", after[eid])
                self.assertEqual(patched, strip_destination_entrance_animations(key, original, patched))
