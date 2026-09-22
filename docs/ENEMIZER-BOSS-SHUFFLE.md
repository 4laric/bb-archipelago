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

Reviewed donor regions carry exact geometry fingerprints and fingerprints for
both original placement anchors. The native writer clones their shapes and
transforms their positions with the same anchor-relative yaw as actors. MSBB
angles are degrees; only the matrix calculation converts to radians. It
preserves original regions and order, rejects bound-ID/name collisions, and
verifies the additions again after generators have been written. Generators
may reference added regions only after those regions exist in the staged map.


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
Ebrietas, Maria, Laurence, Ludwig, Orphan, Logarius, Gascoigne, Rom, Living Failures,
Wet Nurse and Witch of Hemwick, plus the reciprocal Gehrman/Moon Presence pair. The eighteen-boss
graph has two complete assignments selected by seed; the final pair is fixed. All donors are used once and no boss stays in its own arena. Cleric and
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
preserves destination progression through an explicit terminal bridge.
Ludwig now joins the closed pool through a Laurence-to-Ludwig adapter that
copies Laurence's combat routines to project-owned events, preserving both
encounters in the shared map. Their runtime phase
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
| Father Gascoigne | Constructed | Constructed | Yes |
| Blood-starved Beast | Constructed | Constructed | Yes |
| Darkbeast Paarl | Constructed | Constructed | Yes |
| Vicar Amelia | Constructed | Constructed | Yes |
| Witch of Hemwick | Constructed | Constructed (Amelia) | Yes |
| Shadows of Yharnam | Pending | Pending | Pending |
| Rom | Constructed | Constructed | Yes |
| The One Reborn | Pending | Pending | Pending |
| Amygdala | Constructed | Constructed | Yes |
| Martyr Logarius | Constructed | Constructed | Yes |
| Celestial Emissary | Pending | Constructed | Pending |
| Ebrietas | Constructed | Constructed | Yes |
| Micolash | Pending | Constructed (Gehrman) | Pending |
| Mergo's Wet Nurse | Constructed | Constructed | Yes |
| Gehrman | Constructed | Constructed | Yes, fixed reciprocal pair |
| Moon Presence | Constructed | Constructed | Yes, fixed reciprocal pair |
| Ludwig | Constructed | Constructed | Yes |
| Laurence | Constructed | Constructed | Yes |
| Living Failures | Constructed | Constructed | Yes |
| Lady Maria | Constructed | Constructed | Yes |
| Orphan of Kos | Constructed | Constructed | Yes |

Latest standalone construction evidence: reciprocal Ludwig/Cleric and
Laurence/Cleric each verify 13 output files. Orphan-at-Cleric verifies ten,
including separate normalized phase/support NPC clones shared across three
map states, source-pinned player-effect and camera routines, an independent
combat-ready flag and a destination-owned terminal bridge. Installed Orphan
Event 0 and health variants are accepted by exact reviewed hashes; the
installed health damage trigger and update frequency remain intact.

The eleven-boss pool verifies 34 files for each of two distinct seed assignments
(`seed-0` and `seed-2`). Both compose the Laurence and Ludwig destinations in
m34 while preserving both original completion events. Direct BSB-at-Orphan
verifies eight files; its inactive phase/support actors stay alive but hidden
until the original OR-death terminal completes, and the shadow/post-fight
events remain unchanged. The imported camera is explicitly initialized and
the original destination multiplayer battle-state flag remains set on entry.

Helper normalization also permits distinct original actors that share an NPC
row, as required by Logarius's core and c9010 projectile owner. Source actor
and anchor fingerprints remain separate, and aliasing the original primary
actor as its own helper is rejected by both planner and native verification.
Logarius-at-BSB verifies nine output files, with separate sword and c9010
actors in both destination map states. Each helper shares its normalized clone
across states, and the original BSB completion event remains unchanged.
The reciprocal `--pool logarius-bsb` build verifies twelve files. Cainhurst
retains its cutscene, reward, fog and completion while BSB supplies combat.
The retired sword and projectile owner stay hidden and alive until completion;
their recorded original native actor pins are checked before construction.
Imported BSB cameras at Cainhurst, Orphan, Laurence and Maria now exit on
destination completion, preventing camera reactivation if an entry flag is
retained on reload. This is a static lifecycle guard, not a runtime observation.

The twelve-encounter pool verifies 37 files in each of two complete assignments
(seeds `0` and `1`). Ludwig-at-Orphan uses the destination's two existing
primary actors with original Ludwig source initialization; both normalize from
tier 11 to tier 13. It preserves Orphan's original two-actor OR terminal and
post-fight shadow, and maps both active/clear camera operations to m36.
The full pool therefore has thirteen logical actor swaps for twelve encounters;
those counts must not be conflated. The standalone direction verifies eight
files. All of these observations are native construction evidence only.

[Live acceptance preparation](ENEMIZER-BOSS-LIVE-ACCEPTANCE.md) records the
session identity, positive control, predictions, labels, retry/reload checks,
and shape/placement coverage required before runtime support is claimed.

Paarl-at-Logarius brings the reviewed pool to thirteen encounters. Its five
source limb bindings, phase controller and co-op activation accompany Paarl's
health, music and camera, while Cainhurst retains entry cutscene, fog and
progression. Two complete assignments (`seed-0`, `seed-2`) each verify forty
files. The retained Logarius sword and projectile owner are pinned and kept
inert until destination completion.

Standalone BSB-at-Wet-Nurse verifies eight files. BSB keeps direct health and
its own HP phase thresholds; its death then kills the original offstage health
proxy. Original terminal `12601800` and camera `12604804` remain byte-identical,
including opaque `2600803`. The adapter preserves original retry flag
`12604732` and host authority for the retained proxy/support actors. Original
combat controllers that could reactivate the support are ended. This does
not establish the engine meaning of `2600803` or runtime validity of the bridge.
The original map (`af32f7e1038cfd52dbf3b9f073ac1f25f47422230a4cfad3d35d62517d825919`)
has no such ID in a pinned SoulsFormats scan of loaded MSBB tables; the source
EMEVD contains only its terminal and camera uses. No fourth actor is invented.

Orphan-at-Gascoigne brings the pool to fourteen encounters. The original human
and beast parts become Orphan's two combat bodies across all three map states;
only the c4543 support is added. Its independent ready flag is not aliased to
the health event's completion flag. The original Gascoigne cutscene and OR-death
terminal remain unchanged. Both complete assignments verify forty files,
sixteen logical primary swaps, twenty-one source initialization records,
twelve auxiliary actor placements, twenty total NPC clones and thirteen
normalization effects. These counts include other encounters in the pool and
are not evidence of live phase behavior or arena fit.

Region construction and corrected degree-based actor transforms pass the native
suite, including 32 actor and 13 region assertions. Both fourteen-encounter
assignments were rebuilt with corrected transforms and each verifies forty
files (`work/boss-fourteen-degrees-seed-0` and `seed-2`). Earlier receipt success
alone did not detect the degrees/radians geometry defect.

Standalone BSB-at-Living-Failures verifies eight files. It places BSB on visible
body 3500851, preserves the offstage aggregate proxy 3500850, and forces that
proxy's death only after BSB dies. The original terminal 13501850 and all Maria
progression remain unchanged. Original wave/generator/support controllers are
retired; five retained helpers have native provenance checks, and the camera
cannot reactivate after completion. Seven focused tests cover this adapter;
31 focused contract/composition/build/test-quality tests pass. Gameplay remains
unobserved. Living Failures donor construction is described below.

Standalone Rom-at-Ebrietas verifies nine files against original native inputs.
The package includes the core and all thirty spiders in both map states,
four physical warp-region additions, all ninety spider controller bindings,
and shared helper normalization. Destination completion, co-op/fog and music
cleanup remain unchanged; the original Ebrietas owner stays inert until cleanup.
The installed original's richer spider activation event is separately pinned
and retained. Two foreign source replan calls are explicitly removed because
their absent m32 entity would otherwise become the active Ebrietas core.
Rom now joins the reviewed pool through the reciprocal Ebrietas-at-Rom adapter.

Native Object additions now preserve pinned source model/model-point data,
all persisted Object fields and original destination records/order, while
adopting destination loading groups and relative placement. This supports
Wet Nurse's moving duplicate-position marker; it is capability construction,
not yet a completed Wet Nurse donor. Thirteen native Object assertions pass.
Actor requirement binding also rejects a declared hash or initialization that
differs from the installed original, rather than replacing authored evidence.
The fourteen-boss native build passes this stricter binding check.


Ebrietas-at-Rom preserves Rom's completion, post-fight Blood Moon sequence,
co-op/fog and fall handling. It carries Ebrietas body-part controllers and a
separately normalized bullet owner into both original map states, while retiring
Rom spider controllers and cleaning their retained bodies after completion.
The standalone native build verifies nine files. The fifteen-encounter pool
verifies 44 files for each of two distinct assignments (seeds `0` and
`seed-0`), with all required AI goals present. Gameplay is
still unobserved.

MapSFX additions now carry source and anchor pins, explicit Part/Region
bindings, collision checks and full record-order readback. Effect-bank
composition verifies original BND4 hashes and unions the complete donor bank,
retaining destination entries and rejecting differing bytes at an existing
asset name. It verifies the FXR/FLVER/TPF output and requires exact agreement
between declared effect IDs and added MapSFX records. Same-map encounters may
reuse a bank only with identical source/destination pins; no imported entries
are needed. The launcher resolves banks with per-file update precedence,
includes their hashes in seed identity, and stages receipt-listed map banks as
active game files. Tests cover activation and removal on switching modes.


Standalone Living-Failures-at-Laurence now verifies nine native output files.
It retains Laurence progression, adds the proxy/three other bodies/support,
four generators, five regions and five MapSFX records, and preserves the source
9000-to-9060 entry sequence. A separate completed-load cleanup disables/kills
the proxy and additional bodies; Laurence's unchanged terminal owns the
primary. The m35-to-m34 effect-bank union retains 642 destination entries and
imports 360 donor entries, with two identical shared entries reused. A native
generator regression preserves null references during clone construction
without changing the original fingerprint schema. Living Failures now joins the seeded pool through its additional Maria
destination, preserving two distinct complete assignments.


BSB-at-Celestial-Emissary verifies eight native files. BSB occupies the visible
small emissary; a death bridge kills the retained giant only after BSB dies,
leaving the giant-based destination terminal unchanged. Wave generators and
phase controllers are retired, retained bodies are pinned and cleaned after
completion, and shared-map Ebrietas progression remains unchanged. This is a
standalone destination adapter; Celestial donor construction is still pending.


The reviewed pool now covers seventeen encounters. Seeds `0` and `seed-0`
each verify 48 native files and assign every admitted donor exactly once.
Living Failures occupies either Maria or Laurence, while BSB occupies its
original Research Hall encounter. The Maria route clones the same complete
helper/generator/region/SFX graph around Maria's original anchor and uses the
source-witnessed `h000060` collision. Its effect bank stays within m35 and
imports zero new entries while preserving the pinned original bank.

Wet Nurse occupies BSB's arena and Logarius occupies Wet Nurse's arena.
Wet Nurse's support and offstage health proxy are normalized in both BSB map
states. Six authored warp regions and the moving Object marker preserve the
original model-point warp controllers. Entry and co-op use Wet Nurse visibility
semantics, destination completion follows proxy HP reaching zero, player effect
5630 is cleared, and completed-load helper cleanup always runs. Destination
music and environmental audio remain destination-owned: original environmental
loop 12604815 references `a260000003`, witnessed only in `sprj_m26.fev`, and is
explicitly excluded from the donor's combat controller set. The plan records
that source event hash and policy rather than emitting an unloaded sound call.

Logarius-at-Wet-Nurse retains the destination's original proxy terminal and
opaque 2600803 handling, carries both sword and bullet-owner helpers, and
preserves destination sound slots with Logarius's phase trigger. Standalone
native construction verifies eight files. Amygdala-at-Celestial-Emissary also
verifies eight files, including complete body-part/phase controllers and the
original giant-based destination terminal; Celestial donor construction is
still in progress.

Standalone Amelia at Witch of Hemwick also verifies eight native files. The
full Amelia phase, cloth, limb, mask and healing routines are attached; Witch
revival, warps, minions and generators are retired. The retained second Witch
is disabled until the donor death bridge satisfies the original two-actor
terminal. Amelia's original entry animations run independently of Insight.
The original terminal, rewards and AP progression remain unchanged.

Primary actor initialization can explicitly retire a donor's map-local TalkID
with `destination_talk_id_override: 0`. Other override values are rejected;
the exact original source initialization and fingerprint still must match.
This supports replacement combat without importing unrelated dialogue, while
requiring each adapter to provide any terminal handshake its destination needs.

Standalone Gehrman at Micolash verifies eight native files. Gehrman's event
owner, health, camera and combat phases accompany the replacement, while the
original Micolash entry, fog, terminal and post-boss progression remain intact.
Chase controllers wait without completing their event flags; this preserves
the original post-boss controller's branches. A death bridge sets 72600301 only
after the replacement dies, replacing the retired dialogue handshake.
The owner's original m26 talk binder is pinned by SHA-256
`4734174288b8572bac33e9ad4ad7102e7b724427763d8f34c154dbe6d63b0816`;
ESDLang v0.5.1 shows `t260311_x3` self-death leading to `x5`, dialogue 2100300,
then setting 72600301 after dialogue ends. Dialogue assets are not transplanted.

The eighteen-encounter pool includes Witch of Hemwick through
Amygdala <- Witch <- Amelia. Witch combat includes its second body, three
minions, eight warp regions, twelve generator spawn regions and all three
original generators. Source pair revival/death logic controls the primary's
true death, preserving Amygdala's original terminal. Source generator records
are fingerprint-pinned; destination collision h002301 is checked by name and
its pinned actor anchor, without a separate full collision-record fingerprint.
All twenty regions preserve the original relative placements; arena fit still
requires gameplay validation.

Seeds `0` and `2` select distinct complete assignments, each verifying 51 native
files across nineteen physical maps. The seed-variation test
now checks eight seeds rather than assuming two specific seeds must differ
when the roster changes. All admitted donors still appear exactly once, and
no boss remains in its own arena.
