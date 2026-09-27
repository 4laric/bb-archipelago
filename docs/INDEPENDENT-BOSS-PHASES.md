# Independently randomized boss phases

Status: proposed design; not implemented. Current linked-health repairs remain the
release stopgap. This design does not claim parity with another randomizer.

## Player-facing behavior

Offer an opt-in **Independent boss phases** mode. A multi-phase destination has
ordered combat slots, each with an independent compatible boss-form roll. Ludwig's
room can contain human Gascoigne followed by Holy Blade Ludwig. Each slot has its
own health pool and health bar. Defeating the first slot starts the next; only the
last defeat completes the location, grants its reward/check, removes fog, enables
post-boss interactions and permits progression. Single-slot destinations stay single.

The initial conversion covers Ludwig, Orphan and Gascoigne. Their human/beast or
first/second forms become separately selectable donors, including in single-slot
arenas. Other donors remain whole encounters until explicitly converted. Do not
assign an unconverted multi-stage encounter into a phase slot: that would nest
transitions and unexpectedly multiply fight length.

The catalog will have more selectable forms and destination slots than the existing
22 arena identities. Publish counts from the actual catalog, not a hardcoded total.
Invisible HP proxies, support actors, summons and simultaneous group members are
not selectable phases. Wet Nurse's proxy is not a separate boss. Group encounters
require their own completion contract before admission.

## Model and ownership

Retain ArenaContract for geography, entrance, fog, host/co-op admission, music,
completion, rewards and world progression. Introduce:

- BossForm: stable ID (e.g. ludwig.accursed, ludwig.holy_blade, orphan.first,
  orphan.winged, gascoigne.human, gascoigne.beast), source pins, primary actor,
  necessary helpers, direct-start routine, local combat routines, death predicate,
  cleanup routine, effect/AI assets, and supported destination-slot capabilities.
- EncounterLayout: arena ID, ordered PhaseSlot records, one final completion signal,
  reset policy, allocation namespace and layout version.
- PhaseSlot: stable arena/ordinal key, placement, compatible forms, health/damage
  budget, camera/music policy and safe handoff placement. Ordinal is not an actor ID.
- Assignment: seed plus versioned options -> slot/form mapping and allocation plan.

Forms own combat only. They cannot award items, set destination completion flags,
open fog, invoke source cutscenes, warp the player, or activate the next slot.
The encounter controller alone owns sequencing and completion. Existing native
asset copying, source pins, effect-bank constraints and deterministic matching
remain in use. Extend compatibility to (arena, slot, form), rather than allowing
all forms merely because an actor model loads.

## Encounter lifecycle

States: dormant -> entering -> slot_active(n) -> handoff(n) -> slot_active(n+1)
-> completed. Host owns transitions; clients follow replicated encounter state.
Only initialize a slot after its primary/helpers have loaded and initialized HP.
A death predicate must observe a living active boss first, preventing unloaded
zero-HP actors from completing a slot. Accept a death signal once per attempt.

During handoff, retire old AI/projectiles/effects and hide its bar; stage the next
form at a reviewed ground placement; initialize and load it before activation;
then show its bar and enable combat. Keep fog and progression locked. Do not use
arbitrary sleeps as readiness proofs. Any deliberate transition delay is presentation
and must be bounded. No forced player warp unless the arena contract requires one.

On player death or encounter unload, reset to slot one with fresh HP and clear
attempt-local flags and actors. No mid-fight phase checkpoint in the initial version.
Permanent completion stays permanent. Distinguish attempt-local reset flags from
save-persisted destination progression. Late co-op joiners must observe the current
slot, not activate an earlier boss or create a second reward authority.

## Isolating each form

For Ludwig and Orphan, remove referred-damage pairing between phase bodies and
remove the native transform/HP-threshold controller. Each selectable form uses its
own primary HP and death predicate. A second-phase form starts with required
animations, AI state and combat effects initialized directly, without waiting for
messages from a missing first-phase body. Preserve required helpers (for example
Orphan's lightning support) and retire them on slot completion/reset.

For Gascoigne, define which human moveset is included initially; do not silently
count every weapon animation change as a new form. Beast Gascoigne starts directly
in beast combat without music-box/human transformation dependencies. Preserve only
form-relevant reactions. Source-pin every extraction and reject unknown variants.

A form may still need an internal HP proxy where the engine requires one. Such a
proxy must remain loaded and damage-capable; this design removes cross-phase health
coupling, not all multi-actor implementations.

## Assignment and balance

Use stable sorted slot/form identities and a versioned deterministic seed stream.
Never rely on worker completion order. Apply compatibility, asset budgets and
no-repeat/coverage policies across slots. Good-boss coverage must explicitly define
whether it guarantees forms or boss families; initial proposal: family coverage,
then deterministic form selection, with the selected form shown in diagnostics.

Split a destination's total health budget across its slots rather than granting
full encounter HP to every roll. Initial target: equal shares, with reviewed
per-form adjustments. Damage follows destination difficulty, not reduced HP share.
Avoid stacking native co-op multipliers and randomizer scaling. Publish effective
HP per slot and test multi-client scaling. Balance values require playtests.

## Migration and diagnostics

Keep existing whole-encounter mode available. Changing modes rebuilds the overlay
and cache identity; old generated packages cannot acquire this behavior through a
launcher-only update. AP seed/check IDs remain unchanged. Do not reset defeated
boss flags or rewrite saves. Explain that already completed encounters stay complete.

Record layout version, form IDs, placements, effective scaling, source hashes,
assigned actor/event IDs and assets in the manifest. Diagnostics distinguish
waiting-for-load, active slot, handoff and completed. Labels/spoilers show both
ordered rolls. Failure leaves the encounter incomplete rather than issuing rewards.

## Implementation gates

1. Catalog and schema: define forms/slots, ownership validation, deterministic
   assignment and cache identity; no changes to default gameplay.
2. Vertical slice: Ludwig arena with two simple single-body donors; verify separate
   HP, one final reward, death/retry, reload and no off-arena activation.
3. Extract Ludwig forms and independently validate direct-start Holy Blade combat.
4. Add Orphan and Gascoigne forms/layouts with their own helper and state contracts.
5. Expand compatible placements only after source checks and native build validation.
6. Opt-in release after gameplay matrix passes; retain whole-encounter fallback.

Required automated checks: form ownership forbids source progression; every slot
has one active HP owner; helpers have lifecycle owners; IDs do not collide; dead or
unloaded actors cannot advance an unstarted slot; exactly one final completion;
reset clears all attempt state; assignments are deterministic; all emitted binaries
compile and round-trip with preserved destination reward events.

Required live matrix: both slots and each direct-start form, dying in either slot,
dying during handoff, quit/reload, leaving/unloading, already-completed saves,
co-op host/client and join/disconnect during handoff. Observe damage/HP, phase AI,
projectile cleanup, health bars, music, fog, reward/check count and progression.
Native compilation alone is not acceptance evidence for these behaviors.
