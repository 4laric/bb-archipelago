# Bloodborne enemizer

The first implementation boundary is deliberately a **deterministic dry-run
planner**. It consumes the physical-provenance enemy inventory already mined
from Bloodborne's MSBB files and writes a complete swap manifest. It does not
modify a game dump.

This follows the architecture proven by `4laric/nightreign-enemy-rando`:

1. inventory extraction;
2. roster and compatibility metadata;
3. protected-slot classification;
4. deterministic target planning;
5. rejection and spoiler output;
6. game-specific binary writing.

## Current safety policy

The bootstrap policy excludes dummy/script-spawn Parts, talk-bound characters,
CharaInit-bound NPCs and hunters, non-character models, and incomplete
NPC/Think pairs. Alternate map-state copies are one logical placement: if one
copy is protected, all copies are protected; if randomized, all copies receive
the same target.

`tools/build_enemizer_catalog.py` adds param- and event-derived evidence. Only
hostile team-23/npcType-0 archetypes with valid collider dimensions enter the
roster. Collider radius and height determine asymmetric size classes; HP,
currency, respawn, and collider signals form conservative common/elite/boss
tiers. A slot is protected when its entity ID occurs in its area's EMEVD. Areas
whose fixed-map EMEVD was not extracted fail closed: every slot stays vanilla.

### EMEVD usage census

The phrase "entity ID referenced by area EMEVD" describes the current lexical
test, not a proven game-semantic category. `tools/build_emevd_entity_usage.py`
reproduces that test for all 2,399 protected physical slots and commits a
policy-neutral derived table at `research/enemizer/emevd_entity_usage.tsv`.
It separates direct operations, event-initializer arguments, resolved callee
parameter uses, comments, and collisions with item-lot and acquisition-flag
namespaces. The companion summary records that no protection policy changed.
It reads `research/bb_inputs.db` by default, so regenerating the census needs no
game dump; `--inventory` plus `--events` remains available for dump comparison.

The census finds actual character-operation use for 2,254 slots. The remaining
145 have only event arguments or other operation families and need review; this
is not evidence that they are safe. Although 308 protected physical slots share
a number with an ItemLotParam row, only two occurrences are `AwardItemLot`
operands, and only 20 of those collisions lack a separate character operation.
This disproves the stronger "all numeric collisions are item-lot uses" premise
without converting the opposite heuristic into policy. Any relaxation remains
blocked on an in-game map-load and playtest pass. `docs/ENEMIZER-COVERAGE.md`
sharpens this decomposition, proposes the character-operation predicate, and
measures the coverage delta it would earn (308 → 336 swaps, +28, all
non-boss). That wider mode is available behind the off-by-default
`build_enemizer_catalog.py --relax-non-character-emevd` flag; the conservative
default swap set is unchanged.

Target selection follows the Nightreign engine's two-stage model. It chooses a
character model family uniformly, preventing enemies with many authored
NpcParam variants from dominating the pool, then chooses that family's variant
whose native Bloodborne scaling SpEffect is closest to the destination's. The
source model family is excluded, so every planned swap is visually meaningful.

The remaining placements are only *candidate* common-enemy slots. Their plans
carry `size compatibility unknown` until the Bloodborne NPC/character catalog
has real size, tier, and locomotion annotations. A manifest is therefore an
audit artifact, not yet an installable mod.

## Generate a manifest

```powershell
python -m tools.bb_enemizer.cli --seed 12345 --output work/enemizer/12345.json
```

Optional JSON inputs:

- `--tags`: keyed by archetype key (`model:npc:think:chara_init`), with
  `size_class`, `tier`, `locomotion`, `target`, and `notes` fields.
- `--slot-policy`: keyed by physical (`map:part`) or logical slot, with
  `randomize`, `reason`, compatibility fields, and per-slot `bans`.

## MSBB writer

The writer consumes `bb-enemizer-plan-v2` and changes only the destination
Part's archetype tuple:

- `ModelName`
- `NPCParamID`
- `ThinkParamID`
- `CharaInitID`

It must preserve the destination's name, entity ID, transform, collision,
patrol regions, talk ID, event references, draw/display groups, and map-state
identity. It must register missing character models in the MSBB model table,
round-trips every modified file through SoulsFormatsNEXT, validates that no
protected Part field changed in memory, and reopens every output to verify the
new tuple. It refuses an in-place output root, source-data drift, missing Parts,
the wrong manifest format, or a command without an explicit `--apply` token.
The manifest retains a separate expected source tuple for every physical
alternate-state copy, even though those copies share one randomized target.
The writer preflights all maps and source tuples before creating any output.

```powershell
dotnet run --project tools/bb_enemizer_writer -c Release `
  -p:SoulsFormatsNextRoot=C:\path\to\SoulsFormatsNEXT -- `
  work/enemizer/12345.json C:\path\to\map\MapStudio work/enemizer/12345-map --apply
```

The output is still experimental until the roster annotations and in-game
playtest gates are complete.

## Scaling

Elden Ring Archipelago's useful contribution is the policy shape—normalize the
source's native strength, then apply the destination/progression tier—not its
numeric SpEffect IDs. The catalog now derives Bloodborne's native HP ladder
from persistent category-0 `SpEffectParam` rows in the 7000 block. Planning
uses it to select the closest authored NpcParam variant of the chosen enemy
family. This avoids regulation edits for the conservative first release while
preserving area strength substantially better than a raw NPCParam swap.

A later, wider mode can clone NpcParam rows and synthesize exact source-to-
destination SpEffects in `gameparam.parambnd`; that remains separate from
placement selection so it can be tested and disabled independently.

## Offline release gate

`python tools/audit_enemizer.py --seeds 25` regenerates plans across many seeds,
repeats each plan with reversed inventory order to prove determinism, rejects
same-model or unapproved targets, reports large-enemy concentration per map,
and verifies every approved model has a character binder and either its own
animation binder or Bloodborne's explicit `cXXX1 -> cXXX0` shared binder.

The MSBB writer also retains a complete pre-edit state for every enemy Part.
After serialization it reopens each map and proves the Part set, every protected
field, every unchanged archetype tuple, every requested target tuple, and every
original model entry survived the persisted round trip.

`tools/build_enemizer_first_boot.ps1` is the fail-closed packaging entrypoint.
It regenerates the catalogs, runs the 25-seed release gate, creates one
manifest, runs the guarded writer, and emits a package-shaped
`dvdroot_ps4/map/MapStudio` tree plus its manifest, audit, and metadata. Any
failed stage prevents a successful package result.

## Scaling

Enemy scaling — transplant normalization and later depth scaling — is designed
in `docs/ENEMIZER-SCALING.md` (static overlay scaling built on the NG+
`GameClearSpEffectID` area ladder). Design only; nothing is implemented.
