# Boss shuffle implementation

The target is a seed-driven shuffle of all 22 AP boss encounters, including
multi-actor fights. This branch is under development. A successful offline
build is not evidence that entrance, combat, arena fit or AP completion works
in a running game. The experimental reviewed-pool option is separate from the
original single-encounter canary. The full 22-encounter goal remains unfinished.

## Ownership of encounter behavior

`tools/bb_enemizer/boss_contracts.py` separates an `ArenaContract` from a
`CombatPackage`. The arena retains its AP completion event, rewards, fog,
entry conditions and progression. The combat package supplies the actor,
health-bar label, phase routines and body-part initializers. Each source event
is hash-pinned; actor, local flag and event mappings are explicit. The BSB to
Cleric adapter still reproduces the original canary source exactly.

Paarl adds a second combat package with five body-part initializers and their
parameterized routine, phase changes, activation animation/invincibility and
client entry synchronization. Copying just its NPC parameters or its HP phase
event would omit these dependencies. Boss-specific GameClear effects
7420–7429 carry explicit tier numbers in the original SpEffectParam names.
The planner and native verifier use those names' tier mapping, alongside the
existing ordinary and DLC mappings. This is inferred area-tier normalization
using the standard 7401–7413 ladder; it does not invert the distinct individual
boss NG+ multipliers and remains unvalidated for gameplay balance.

`tools/bb_enemizer/boss_actor_rosters.py` records the combat bodies, proxies and
helpers needed by the ten multi-actor encounters, with source and placement
evidence. These rosters are inputs to construction, not an approval list.
See [the multi-actor dossier](ENEMIZER-BOSS-MULTI-ACTOR.md) for the distinct
completion, generator, proxy and phase-transition requirements. Mergo's
terminal entity 2600803 remains unresolved and is not silently turned into a
placeable actor.

## Native construction

`tools/build_boss_encounters.py` decompiles the player's originals with pinned
DarkScript 3.6.3, applies the reviewed contract, compiles it, and records native
fingerprints for the exact replacement events. `BBEnemizerWriter
--boss-encounters` checks the original binary hash and the declared replacements,
then merges only those events into the original file. Compiler normalization
of unrelated events is discarded. Original event order, link/string data and
all protected completion events are checked again after serialization.

Multi-actor donors can declare `terminal_predicates`: one exact MAIN
`CharacterDead(original_actor)` instruction becomes an `EventFlag(bridge)`
wait. The bridge implements the donor's combat completion condition. The
native writer rejects any other difference in the protected terminal,
including rewards, flags, branch offsets and parameters. Gascoigne's standalone
Cleric adapter uses this route for its human-or-beast death condition and
cleans up the beast after victory/reload; donor-owned Insight and progression
flags are excluded from its transplanted phase routine.

The native path composes map, parameter, AI and event output in staging and
emits `boss-encounters-report.json` with the complete file set and hashes.
The developer builder verifies that receipt before publishing a new output
directory. It does not activate a mod, launch the emulator, or touch saves.
Direct map/scaling commands reject boss-marked plans, so an event-dependent
build cannot accidentally be presented as a complete map-only build.

The experimental `--pool bsb-paarl` mode constructs the reciprocal BSB/Paarl
assignment. Both edits originate from the same pristine map script; disjoint
constructor changes are composed before compilation, and overlapping edits
are refused. It uses each donor exactly once. This two-member pool has only
one derangement, so changing the seed cannot yet change its assignment. The
matching implementation supports larger explicit compatibility graphs and
refuses an incomplete matching instead of dropping encounters.

`--pool reviewed` currently includes Cleric, BSB, Paarl, Amelia, Amygdala,
Ebrietas, Maria and Laurence, plus the reciprocal Gehrman/Moon Presence pair. The regular
eight-boss graph has two complete assignments selected by seed; the final pair
is fixed. All donors are used once and no boss stays in its own arena. Cleric and
Amelia attach explicitly allocated, pinned combat routines rather than relying
on a destination having the same number of native phase events. Constructor
composition also accepts disjoint appended initializer calls and rejects
conflicting event/slot bindings.

`--pool gascoigne-cleric` builds the reciprocal transformation test. The
Gascoigne arena retains its original OR-death terminal and cutscene while its
unused beast is disabled without being killed before victory. Both directions
compose in the same m24 script, with source-pinned Talk IDs in all three states.

The native writer also supports explicit additional actor placements and
additional event IDs. Actor placement preserves the destination anchor's
collision, groups and move points, rotates the donor's
relative position into that frame, and imports its declared character tuple.
An optional exact source pin imports donor initialization fields. Dummy actor
materialization requires explicit intent and a source pin. Typed MSBB generator
additions require source fingerprints and complete spawn-Part/region mappings;
they do not infer EMEVD generator behavior. `--boss-actor-pins` reads this
provenance from the owner's effective original maps. The existence of an actor
roster still does not enable a combat package automatically.

`boss_actor_initializations` imports the four pinned donor fields on a primary
actor after its combat tuple has been transplanted. Gascoigne uses this to
retain the human form's TalkID 241330 in the same map, where its source ESD
already exists. This is not evidence for moving talk-bound actors across maps.

Ebrietas's bullet-owner identity is a real MSB actor. Its native-pinned helper
is materialized in every recipient map state. Maria's 3500801 event target is
different: it is absent from all original MSB entity tables. The experimental
adapter preserves that exact literal, verifies original and final destination
absence, and verifies the source/final `SetCharacterEventTarget` instruction.
Its receipt explicitly records inferred evidence and unobserved runtime behavior.

`--ordinary-plan` combines ordinary-enemy and boss swaps before a single native
map/AI/scaling pass. NPC clone IDs are allocated once across both sets. The
launcher cache retains the complete native receipt and auxiliary plans, and
verifies every generated map, event, AI binder and parameter file.

The packaged builder uses a pinned upstream DarkScript3 download cached locally
on first use. Both the release archive and extracted resources are checked;
the package does not redistribute the upstream compiler. The frozen builder
needs no separately installed Python interpreter.

Example, using original effective maps/scripts/events and the built AP binder:

```powershell
python tools/build_boss_encounters.py --arena cleric-beast --donor darkbeast-paarl `
  --seed boss-test --darkscript <DarkScript3.exe> `
  --writer <BBEnemizerWriter.dll> --dotnet <dotnet.exe> `
  --gameparam <built-gameparam.parambnd.dcx> --paramdef <paramdef.paramdefbnd.dcx> `
  --maps <effective-MapStudio> --scripts <effective-script> `
  --events <original-events> --output <new-output-directory> --apply
```

The event inputs include the donor and destination binaries plus their original
`common.emevd.dcx` link. Output must be outside every input directory. Source
maps must combine base and update per-file, with update precedence; an update
directory alone can omit most of the game.

`--event-overrides <directory>` composes pre-existing AP event patches on
affected boss maps. Both variants are compared against the same original;
overlapping non-constructor changes fail. Source override hashes are retained
in the plan. Native no-payload initializer calls are lifted only if the same
file declares a matching zero-argument event, allowing the pinned compiler to
encode the required unused argument padding.

The earlier `--boss-shuffle` CLI is a registry planning report. It reports
planned destination coverage, never treats a donor's untouched home encounter
as randomized, and exits nonzero if a registered template cannot be planned.
`tools/build_boss_shuffle.py` provides a checked bridge from that report to the
original native canary. It is not the full-roster product entry point.

## Evidence recorded during development

On 2026-09-22, original CUSA03173 01.09 inputs built both BSB and Paarl into
Cleric Beast's arena through the generalized compiler/native path. Each output
verified ten retained files, all three map states and complete imported AI
goals. BSB used one normalization clone; Paarl recorded unscaled output. The
Cleric and Gascoigne completion events were protected during both builds.
These are offline construction results, not live observations.

The reciprocal BSB/Paarl pool also compiled and built from the original game
inputs: two map states, four physical placements, one normalization clone,
one explicit scaling skip, complete AI goals, and nine verified output files.
Both original Old Yharnam completion events were preserved. This validates
same-map composition structurally, not the encounters in gameplay.

Both four-boss pool assignments also built from those inputs: seven map files,
nine physical primary placements, three event files and complete AI goals,
with eighteen verified output files per build. The standalone Gascoigne source
compiled and passed the constrained terminal check on the original Cleric
binary, with source-pinned primary initialization and three phase-actor
placements. It retained ten verified files. No gameplay behavior is claimed.

The Cleric-at-Amelia build also composed an existing AP Cathedral patch. The
native output preserved the patched fingerprints of 12400760, 12401803,
12405710 and 12409990 exactly, alongside the boss replacement.

The five-boss pool including Amygdala built eight map files, ten primary
placements, four event files and four complete AI binders, with twenty-one
verified files overall. The subsequent nine-encounter pool built both seeded
assignments with 31 verified files each. The reciprocal Maria/Cleric build
verified 13 files, including source-pinned actor initialization and the opaque
event-target witness. Ebrietas-to-Paarl built its real c9010 helper in both states.

A combined build of 308 ordinary swaps and nine boss encounters verified 50
files: 23 maps, 560 primary placements, 15 complete AI binders, and one scaling
pass producing 239 NPC clones. A second build composed the existing AP Cathedral
events into the same output. The frozen Windows builder also completed an
original-data reciprocal BSB/Paarl build with nine verified files.

Standalone Ludwig and Laurence donors each built ten verified files in Cleric's
arena. Ludwig is the two-actor 3400800/3400801 encounter, distinct from Laurence
3400850. Its adapter selects the normal three-limb configuration, replaces the
source cutscene/warp with a destination actor-relative phase transition, and
preserves destination progression through an explicit terminal bridge. These
Ludwig donor remains outside the closed pool; Laurence now joins it through
the BSB-to-Laurence and BSB-to-Maria cross-links. Their runtime phase
behavior and arena fit remain unobserved. Ludwig's second form and Gascoigne's
beast now receive distinct NPC clones with the parent's inferred normalization
effect. Physical map states share one helper clone per logical fight. Native
verification binds each helper to its original actor fingerprint, initialization,
parent-owned destination anchor, source tier, output parameter row and receipt.
Noncombat additions such as Ebrietas's projectile owner remain separate. The
reciprocal Gascoigne/Cleric native build verified ten files and both destination
completion events, including all six primary actor initialization records.

Cleric-at-Laurence also builds through the encounter builder (eight verified
files). It preserves both original m34 completion events and all Ludwig phase
routines, retaining Laurence's entry item/cutscene while substituting Cleric's
entry animation, combat attachments and camera. Its new phase events use
collision-scanned project IDs rather than Ludwig's existing event IDs.

Boss-only normalization now also covers the previously missing m24_02 arena
at tier 11, witnessed by original Ebrietas NPC251000's named 7423 effect.
The ordinary enemy tier oracle and its pinned fixture remain unchanged.
The updated original-data reviewed build verifies 31 files and nine normalized
boss placements. The combined ordinary/AP build verifies 50 files, 317 logical
placements, 244 primary NPC clones and 67 normalization effects. Ludwig and
reciprocal Gascoigne/Cleric builds each verify ten files with explicit helper
clone receipts; all three Gascoigne map states share one helper clone.

## Remaining work before full support

Complete the arena and donor contracts across the roster; construct auxiliary
actors, generators and phase/proxy graphs; assign each donor exactly once with
deterministic compatibility-aware seed matching; compose all selected
encounters with collision-free identifiers and scaling; integrate the
launcher/cache/package path; and run the whole-roster structural and native
build matrix.

Live acceptance then covers the shapes separately: single actor, transformation,
multiple simultaneous actors, shared HP, helpers/generators and special proxy.
For each constructed encounter check first entry, death/re-entry, phase and
helper behavior, damage/health bar, arena containment, defeat/rewards/exit,
exactly one destination AP check, no donor progression change, and save/reload.
Follow [the live-probe contract](CONTRIBUTING-LIVE-PROBES.md). Do not promote
the branch from experimental based on planner or serialization tests alone.

## Full-roster coverage ledger

This ledger describes at least one constructed directed adapter in each role,
not arbitrary compatibility with every other boss. All gameplay validation is
still outstanding. The full target remains all 22 encounters in complete
seed-dependent assignments.

| Encounter | Donor adapter | Destination adapter | Reviewed pool |
|---|---|---|---|
| Cleric Beast | Constructed | Constructed | Yes |
| Father Gascoigne | Constructed | Constructed | Pending cross-links |
| Blood-starved Beast | Constructed | Constructed | Yes |
| Darkbeast Paarl | Constructed | Constructed | Yes |
| Vicar Amelia | Constructed | Constructed | Yes |
| Witch of Hemwick | Pending | Pending | Pending |
| Shadows of Yharnam | Pending | Pending | Pending |
| Rom | Pending | Pending | Pending |
| The One Reborn | Pending | Pending | Pending |
| Amygdala | Constructed | Constructed | Yes |
| Martyr Logarius | In progress | Pending | Pending |
| Celestial Emissary | Pending | Pending | Pending |
| Ebrietas | Constructed | Constructed | Yes |
| Micolash | Pending | Pending | Pending |
| Mergo's Wet Nurse | Pending | Pending | Pending |
| Gehrman | Constructed | Constructed | Yes, fixed reciprocal pair |
| Moon Presence | Constructed | Constructed | Yes, fixed reciprocal pair |
| Ludwig | Constructed | Constructed | Pending cross-links |
| Laurence | Constructed | Constructed | Yes |
| Living Failures | Pending | Pending | Pending |
| Lady Maria | Constructed | Constructed | Yes |
| Orphan of Kos | Constructed | In progress | Pending |

Latest standalone construction evidence: reciprocal Ludwig/Cleric and
Laurence/Cleric each verify 13 output files. Orphan-at-Cleric verifies ten,
including separate normalized phase/support NPC clones shared across three
map states, source-pinned player-effect and camera routines, an independent
combat-ready flag and a destination-owned terminal bridge. Installed Orphan
Event 0 and health variants are accepted by exact reviewed hashes; the
installed health damage trigger and update frequency remain intact.
