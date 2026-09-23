"""Script-contract classification for enemizer release tranches.

A reference to an entity ID in area EMEVD is a dependency to support, not an
automatic refusal. The map writer preserves the destination's entity ID,
event bindings, flags, transform, talk ID and part name; only the archetype
tuple (ModelName, NPCParam, ThinkParam, CharaInitID) changes, and donor AI
is transplanted alongside. An operation is therefore *supported* when it
addresses the entity through preserved identity or donor-agnostic data, and
*hard* when it assumes the original model/skeleton/AI/boss wiring.

Evidence anchors (static, corpus-wide, committed inputs only):
- 0 of 1,222 ForceAnimationPlayback calls occur inside WaitFor regions
  (balanced-paren parse over all area + common events): there is no
  wait-on-animation hang mechanism in the corpus. This does NOT prove a
  donor missing the animation is harmless: downstream animation state,
  TAE-driven effects/flags, and model-specific blends remain unvalidated
  and playtest is owed. The residual is bounded to non-hang behavior, not
  proven absent.
- NpcParam animIdOffset is 0 on all 639 used rows: animation literals live
  in one global namespace, not per-model offsets (a uniformity observation,
  not per-model coverage proof).
- Set-then-wait-same-effect hang pairs: 8 corpus-wide, 1 entity affected
  (already parts-gated): SpEffect writes are non-blocking.
- Enemy drops v2 rewrites per-NpcParam tables (never AP locations) and fixed
  treasure/objacts are untouched by the writer: drops need no per-placement
  handling.

Any operation not listed in either table classifies as ``unreviewed`` and
fails closed (blocked + reported). The tables must stay total over the
observed 77-operation vocabulary (see tests).
"""
from __future__ import annotations

# op -> one-line compatibility argument. The writer preserves entity ID and
# event bindings; donor AI (ThinkParam + Lua) is transplanted with the model.
SUPPORTED_OPS: dict[str, str] = {
    # Reads / predicates: observe state through preserved identity.
    "CharacterDead": "death predicate on preserved entity ID; donor is killable",
    "HPRatio": "HP read on preserved entity ID",
    "CharacterHPValue": "HP read on preserved entity ID",
    "HasDamageType": "damage predicate; read-only",
    "CharacterHasSpEffect": "effect read; read-only",
    "CharacterHasEventMessage": "message-flag read; read-only",
    "CharacterBackreadStatus": "LOD-status read; read-only",
    "CharacterAIState": "AI-state read; donor AI is transplanted",
    "CharacterTargetedBy": "targeting read; read-only",
    "CharacterDamagedBy": "damage-source read; read-only",
    # Generic AI interface: operates on the transplanted donor AI.
    "RequestCharacterAIReplan": "generic replan request to present AI",
    "SetCharacterAIState": "generic AI enable/disable; symmetric pairing preserved",
    "ChangeCharacterEnableState": "generic enable/disable toggle",
    "ClearCharactersAITarget": "generic target clear",
    "ChangeCharacterPatrolBehavior": "patrol directive to transplanted AI",
    # LOD / perf plumbing: identity-independent.
    "SetCharacterBackreadState": "LOD state write; model-independent",
    "SetCharacterDefaultBackreadState": "LOD default write; model-independent",
    # Absolute data writes: value is data, not model behavior.
    "SetCharacterTeamType": "absolute team assignment; donor is hostile-23",
    "SetCharacterImmortality": "generic flag write",
    "SetCharacterInvincibility": "generic flag write",
    "SetCharacterHPBarDisplay": "HUD flag write",
    # Transform / physics: positions and collision are preserved.
    "SetCharacterGravity": "physics flag; preserved transform",
    "SetCharacterGravityMaphitStateExcludingOwnWorld": "collision flag; preserved transform",
    "SetCharacterMaphits": "collision flags; preserved transform",
    "RotateCharacter": "transform write; preserved transform",
    "WarpCharacterAndSetFloor": "transform write; preserved transform",
    "WarpCharacterAndCopyFloor": "transform write; preserved transform",
    "IssueShortWarpRequest": "transform request; preserved transform",
    "SetCharacterHome": "home-point write; preserved transform",
    "CharacterWarpRequest": "warp request; preserved transform",
    # Event plumbing: IDs and bindings preserved by the writer.
    "SetCharacterEventTarget": "event-target binding; preserved bindings",
    "SetEventPoint": "event point write; preserved bindings",
    # Death / treasure mechanics: donor-agnostic engine behavior.
    "ForceCharacterDeath": "death forcing on preserved entity ID",
    "ForceCharacterTreasure": "treasure forcing; drop tables are per-NpcParam rewritten",
    # Network / multiplayer plumbing: entity-addressed, model-independent.
    "SetNetworkUpdateRate": "netcode tuning; model-independent",
    "SetNetworkUpdateAuthority": "netcode authority; model-independent",
    "SummonNPC": "co-op plumbing on preserved entity ID",
    "SendNPCSummonHome": "co-op plumbing on preserved entity ID",
    # Animation: fire-and-forget only (0 of 1222 in WaitFor corpus-wide) in
    # one global ID namespace (animIdOffset 0 everywhere). Proven: no
    # wait-hang mechanism. NOT proven: downstream animation-state/TAE/flag
    # effects on donors missing the animation. Residual is bounded
    # non-hang behavior; playtest owed per tranche.
    "ForceAnimationPlayback": "fire-and-forget statement; non-hang residual, playtest owed",
    "SetCharacterAnimationState": "animation-state write; non-hang residual, playtest owed",
    "RequestCharacterAnimationReset": "animation reset; non-hang residual, playtest owed",
    # SpEffect writes: ID-addressed game data, proven non-blocking (no live
    # set-then-wait-same-effect pair outside parts-gated placements).
    # Residual: wrong-skeleton effect behavior; playtest owed.
    "SetSpEffect": "ID-addressed effect write; proven non-blocking",
    "ClearSpEffect": "ID-addressed effect clear; proven non-blocking",
    # Spatial / object / presentation / item-lot families: regions, objacts,
    # treasures, SFX and lots are preserved or donor-agnostic.
    "InArea": "spatial check on preserved transform",
    "EntityInRadiusOfEntity": "spatial check on preserved transforms",
    "ActionButtonInArea": "spatial trigger; preserved transform",
    "SetObjactState": "objact write; objacts preserved",
    "ActivateMapPart": "part activation; parts preserved",
    "DeactivateObject": "object deactivation; objects preserved",
    "RequestObjactActivation": "objact request; objacts preserved",
    "SetObjectTreasureState": "treasure write; treasures preserved",
    "WarpObjectToCharacter": "object warp to preserved transform",
    "CreateBulletOwner": "bullet ownership; donor AI transplanted",
    "ShootBullet": "bullet spawn; donor AI transplanted",
    "CreateDamagingObject": "damage volume; positional data",
    "CreateReferredDamagePair": "damage pairing; positional data",
    "PlaySE": "sound cue; positional",
    "SpawnOneshotSFX": "one-shot SFX; positional",
    "AwardItemLot": "lot award on preserved entity ID",
    "SetDistanceLimitForConversationStateProcessing": "dialogue-range tuning",
    "EzstateInstructionRequest": "ezstate instruction; engine-level",
    "StartTimeMeasurement": "diagnostic timer",
    "EndTimeMeasurement": "diagnostic timer",
}

# op -> blocker reason + what an adapter would need. These stay protected.
HARD_OPS: dict[str, str] = {
    "DisplayBossHealthBar": "boss wiring: health-bar bound to arena actor; needs encounter template",
    "HandleBossDefeat": "boss wiring: completion bound to arena actor; needs encounter template",
    "HandleMinibossDefeat": "miniboss wiring: completion binding; needs encounter template",
    "CreateNPCPart": "model-specific limb construction; needs per-model part adapter",
    "SetNPCPartHP": "model-specific limb HP; needs per-model part adapter",
    "NPCPartHP": "model-specific limb read; needs per-model part adapter",
    "SetNPCPartSEAndSFX": "model-specific limb SFX; needs per-model part adapter",
    "AdaptHpchangingSpEffectToNPCPartOfTarget": "model-specific limb/effect coupling; needs per-model adapter",
    "ChangeCharacterHitmask": "model-specific hitmask; needs per-model adapter",
    "ChangeCharactersCloth": "model-specific cloth; needs per-model adapter",
    "ChangeCharacterDispmask": "model-specific display mask; needs per-model adapter",
    "SetCharacterAIId": "AI identity write; donor AI mapping unproven; needs AI-ID adapter",
    "RequestCharacterAICommand": "AI-command IDs are AI-specific; per-command review owed",
    "RequestAnimationPlayback": "async playback request; blocking semantics unproven (1 site)",
    "SetSpEffectAndUnknown200455": "unknown operation semantics; research owed",
}


def classify_ops(operations: set[str]) -> tuple[str, set[str], set[str]]:
    """Classify one placement's operation set.

    Returns (contract_class, hard_ops, unreviewed_ops) where contract_class
    is 'supported' only when every op is in SUPPORTED_OPS.
    """
    hard = {op for op in operations if op in HARD_OPS}
    unreviewed = {op for op in operations if op not in SUPPORTED_OPS and op not in HARD_OPS}
    if hard or unreviewed:
        return "needs_adapter", hard, unreviewed
    return "supported", set(), set()


def placement_operations(census_operations: str) -> set[str]:
    """Fold one census 'operations' cell to base operation names."""
    init_markers = {
        "$InitializeEvent:argument", "$InitializeEvent:event_id",
        "$Event:argument", "$Event:event_id",
    }
    ops = set()
    for entry in census_operations.split(";"):
        if not entry:
            continue
        name = entry.rsplit(":", 1)[0]
        if name in init_markers:
            continue
        ops.add(name.removeprefix("resolved/"))
    return ops
