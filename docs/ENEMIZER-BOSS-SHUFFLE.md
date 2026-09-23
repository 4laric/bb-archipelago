# Boss shuffle implementation

The target is a seed-driven shuffle of all 22 AP boss encounters, including
multi-actor fights. This branch is under development. A successful offline
build is not evidence that entrance, combat, arena fit or AP completion works
in a running game. The experimental reviewed-pool option is separate from the
original single-encounter canary. All 22 encounters now have constructed donor
and destination adapters; full gameplay acceptance remains unfinished.

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
Wet Nurse, Witch of Hemwick, Celestial Emissary, Micolash, The One Reborn, Shadows,
Gehrman and Moon Presence.
The historical `aeb5d81` twenty-two-boss graph had 560 complete one-to-one assignments and
63 feasible directed arena/donor edges. Every arena had at least two feasible
donors, and every donor can reach at least two feasible destinations. The graph
remains deliberately restricted rather than all-to-all. All donors are used
once and no boss stays in its own arena. Cleric and
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
| Shadows of Yharnam | Constructed (Orphan) | Constructed (Ludwig) | Yes |
| Rom | Constructed | Constructed | Yes |
| The One Reborn | Constructed (Ebrietas) | Constructed (Rom) | Yes |
| Amygdala | Constructed | Constructed | Yes |
| Martyr Logarius | Constructed | Constructed | Yes |
| Celestial Emissary | Constructed (Paarl) | Constructed | Yes |
| Ebrietas | Constructed | Constructed | Yes |
| Micolash | Constructed (Moon Presence) | Constructed (Gehrman) | Yes |
| Mergo's Wet Nurse | Constructed | Constructed | Yes |
| Gehrman | Constructed | Constructed | Yes |
| Moon Presence | Constructed | Constructed | Yes |
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
standalone destination adapter. At this historical checkpoint, Celestial donor
construction had not yet been added.


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
original giant-based destination terminal. Celestial donor construction now
exists through its reviewed Paarl and Rom destination routes described below.

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

The next roster extension adds Celestial Emissary at Paarl, Micolash at Moon
Presence, One Reborn at Ebrietas, and Rom at One Reborn. Their standalone native
builds verify nine, eight, nine and nine files respectively. Celestial includes
its giant, seven wave bodies, two supports, eleven regions and seven generators
in both physical destination maps. Its giant death releases the retained Paarl
terminal. Micolash uses the original direct-combat AI commands with its local
dialogue retired; a project flag drives phase music without advancing Mensis.

One Reborn carries its body, controller, damage proxy and six casters. The native
AI writer accepts ThinkParam 0 only for boss-prepared actors with complete
source initialization and provenance evidence. Every physical primary needs a
matching binding; helpers need part and anchor pins. Original binary actor
verification still runs before the atomic output is published. No row 0 or AI
goal is invented. The AI receipt lists the exempt actors and retains exact goal
requirements for the controller and casters. Ordinary missing-AI swaps fail.
The caster counter reserves all four flag bits; entry notification uses a
separate flag. Collision tests reject aliases into any occupied counter bit.
The casters retain their original elevated relative placements; their fit and
accessibility in Ebrietas's arena are unresolved gameplay questions.

Rom at One Reborn includes all thirty spiders and two phase-warp regions in
both physical maps. Original One Reborn body, proxy and caster controllers are
retired. Only donor death releases the original destination terminal. The
unrelated destination entry/cutscene and progression remain in place.

Ludwig at Shadows independently verifies nine files. Both Ludwig forms retain
their phase routines, and all three destination snake generators and c5033/c2121
helpers are retired. Its bridge satisfies the original three-body terminal
after donor death. An explicitly pinned installed-source variant changes only
the unrelated quest initializer 12700907 to 12700910; it is preserved verbatim.

The earlier twenty-one-boss construction checkpoint verified 55 files per
assignment, including 122 physical helpers, 63 regions and 21 generators.
Those artifacts predate the counter-allocation correction and are superseded
by the full-roster validation below.

Shadows at Orphan independently verifies eight files. Three active Shadow
bodies, three snake bodies, four attachments, twelve regions and three
generators use one pinned placement transform anchored on the original second
Shadow. The original Orphan primary becomes an inert, hidden terminal proxy;
all three active bodies must die before the bridge kills that proxy. Original
terminal 13601800, including its OR-death branch, rewards and AP progression,
remains byte-identical. The copied source phase-music flag has no EMEVD setter;
its actor/TAE behavior remains a runtime question.

Maria and Laurence at Living Failures each independently verify eight files.
Maria's direct combat
health and phase routines replace the wave fight, while Maria's death releases
the original aggregate-proxy terminal. All generators, unused bodies and
support are retired. Laurence retains its original limbs and phase hitmask.
Together these routes expand the prior two complete assignments to six;
compatibility is still a restricted graph, not every possible boss/arena pair.

A source-wide counter audit found and corrected overlapping flag allocations
in Witch at Amygdala and both Living Failures donor routes. Witch reserves all
ten minion-counter bits; the two three-bit Living Failures counters have
disjoint ranges. The validators check every occupied bit and regressions
attempt aliases into those ranges. Celestial and Shadows source closures do
not use event-value counters. Earlier outputs with overlapping allocations
must be rebuilt; native file verification alone cannot detect that semantic
mistake.

Full-roster native validation passes all six distinct assignments, selected by
seeds `0`, `2`, `4`, `5`, `6` and `11`. Each verifies 59 output files across 23
physical maps, with 134 added actors, 75 regions and 24 generators. The receipts
contain the corrected Witch, One Reborn and Living Failures counter allocations.
A combined build also verifies 59 files with 308 ordinary enemy swaps plus all
22 boss encounters (331 physical/logical swap records), confirming joint map,
parameter, AI and event construction. These outputs remain offline artifacts;
no overlay was activated and no gameplay result is asserted.

The full Python run passes 1,559 collected tests with 55 expected skips. The
subsequently added installed-source regression passes in focused testing; the
committed collection floor is 1,560. That six-assignment checkpoint was also
checked independently across 64 seeds. Native suites pass, including 53 AI
assertions and actor, encounter, region, Object, SFX, FFX, scaling and event
verification. Original-input compiler tests remain optional where those local
fixtures are unavailable; their portable contract tests are required in CI.


## Compatibility expansion after full-roster construction

Wet Nurse at Logarius and Paarl at Wet Nurse each independently verify eight
native files. The former carries the complete proxy, support, six warp regions
and original model-point Object; it retires the Logarius sword-dependent camera
controller. The latter retains Wet Nurse's terminal proxy and releases it only
after Paarl actually dies, carrying Paarl's five limb slots and wake-up sequence.
Their full-roster seed `9` build verifies 59 files, including shared Mensis events.

Micolash at Gehrman and Moon Presence at Micolash each independently verify eight
files. They add a second permutation of the three final encounters. The shared
Micolash direct-combat extraction produces byte-identical Moon Presence-arena
events and an identical native plan to the preceding implementation. Gascoigne
at Hemwick also verifies eight files: both forms retain source state, Witch
controllers are retired, and the original two-body terminal is released only
after Gascoigne's actual human-or-beast death. Source pins cover exactly the
Gascoigne combat bodies consumed by this adapter.

At that checkpoint, these five additional directed adapters expanded the
complete assignment graph from six to 48. This was still restricted
compatibility, not unrestricted all-to-all replacement. Full-roster seed `8`, containing all three new final/Hemwick routes together,
also verifies 59 files. The focused expansion suite passes 69 tests. Runtime
entrance, geometry, phase behavior and completion remain unobserved.

The Archipelago test gate permits only individually named local compiler or
installed-source checks to skip. An unlisted skip or stale allowance fails.
AP-dependent modules explicitly require zero skips; baseline module rows retain
their executed-test floors. Five gate regressions cover these distinctions.

The `aeb5d81` checkpoint graph extended that checkpoint to 560 complete assignments.
Of its 67 declared directed edges, 63 occur in at least one complete assignment.
Each of the 22 arenas has multiple feasible donors, and each donor has multiple
feasible destinations, so no encounter is forced to one counterpart across all
seeds. [The tracked native matrix](boss-shuffle-native-matrix.json) records the
canonical graph hash, every feasible choice, the exact 63-edge union, and 13
deterministic full-roster mappings that cover that union. Those mappings form
a durable native-build schedule; mutable verification results are recorded
separately in the PR #427 verification record. The matrix itself makes no
native-build claim. Gameplay, arena fit, phases, retry behavior and completion
remain unvalidated at runtime.

The final four directed adapters are Celestial Emissary at Rom, Shadows at
Celestial Emissary, Witch at One Reborn, and One Reborn at Shadows. They carry
their complete source-backed multi-body and generator closures while retaining
the destination terminal/progression contract. Rom's Celestial entry and music
use the original Rom arena region; both physical states pin every retired spider.

Completion guards prevent copied Witch and Living Failures controllers from
reactivating minions, generators or support AI after victory. Cleanup disables
the complete owned helper set, including Living Failures support, with each
arena's own generator IDs. Native matrix construction also exposed and fixed
Orphan-at-Cleric primary provenance containing an inapplicable anchor field;
anchored additions retain their anchor evidence and original fingerprints.
These are construction and lifecycle fixes, not observations of game behavior.

## Broader composition work (September 23)

The user-approved design is to preserve donor combat and adapt arena-specific
traversal and set pieces to the destination. Reproducing Micolash's original
chase outside Mensis, for example, is not a prerequisite for moving his combat.
Boss combat phases and destination progression still need explicit handling.
The user also chose to skip character-specific entrance cinematics when a
replacement boss occupies the arena. Entry triggers, player relocation and
progression remain required; this decision does not remove donor combat-phase
transitions or destination ending sequences.
The existing one-of-each, no-self-placement policy gives 462 candidate directed
pairings across the 22 encounters. This is the work inventory, not a claim that
all 462 are implemented or playable.

A missing adapter is an implementation gap, not a finding of incompatibility.
The previous 67 implemented / 63 globally feasible pairings were a construction
checkpoint, not the intended final feature scope. Any proposed permanent
exclusion needs a concrete reason and a separate design decision. Source pins,
complete donor dependencies and protected destination progression remain
construction requirements; neither those checks nor a wider compatibility graph
establishes arena fit or live combat behavior.

Run the current implementation inventory with:

```powershell
python -m tools.build_boss_coverage --output work/boss-coverage.json
```

It reports unimplemented pairs separately from implemented pairs that cannot
participate in the current one-to-one assignment graph. It makes no native or
gameplay validation claim. The tracked 13-seed native matrix above belongs to
`aeb5d81`; changing the graph requires a new build schedule and new evidence.

The first composition step registers reusable generic contracts and the Maria
donor through one recipe lookup shared by event generation, native planning and
helper requirements. Special encounter adapters remain in place while their
combat/lifecycle boundaries are extracted. Adding a registry entry does not
substitute for implementing those boundaries.

The first composition checkpoint implemented 78 of the 462 directed pairings; all 78 participate
in complete assignments. The six base arena contracts expose 23 of their 30
off-diagonal pairs. Ebrietas's combat package now reaches all five other base
arenas, and Amelia also reaches Cleric and Ebrietas. Maria uses one donor adapter
across all six base arenas. The existing Blood-starved Beast at Celestial
Emissary adapter was included in the assignment graph. At that checkpoint,
the other 384 pairs remained implementation work.

Reusable routes preserve entry protection independently of removed model
animations. Native plans bind each physical primary and Ebrietas helper to an
explicit original source map state, including Cleric's extra state. Maria's
health/network, co-op scaling, camera and phase cleanup travel with her combat;
the destination retains its progression and health telemetry. This is static
construction evidence. Entry, combat, death, reload and arena fit still require
gameplay acceptance.

The first [composition native matrix](https://github.com/4laric/bb-archipelago/blob/4de3eb490b1f85625652dcda2797e4f275442509/docs/boss-composition-native-matrix.json) records
21 full-roster builds covering all 78 implemented pairs, with 59 verified files
per build. After correcting Maria's duplicate room-entry notification at Amelia,
both affected seeds were rebuilt; full-source comparisons prove the other five
Maria outputs unchanged. The combined `composition-26` build includes 308
normalized ordinary swaps, all 22 boss encounters and an actual Cathedral AP
event override. The frozen Windows builder reproduces all 59 output hashes and
the receipt exactly. Source, graph, tool and receipt hashes are recorded in the
matrix; these remain native construction results, not gameplay observations.

## Base arena completion and entrance policy

The next implementation step expands the graph to 90 directed pairings, all
usable in complete assignments. The initial six arenas now accept all 30
off-diagonal combinations of their six combat packages. Laurence's reusable
donor reaches those six arenas as well. This leaves 372 implementation gaps
in the full 462-pair inventory.

Specialized BSB/Paarl placements retire Amelia's original healing controller
and Amygdala's original head-part controller so they cannot manipulate the
replacement boss. Laurence carries his health/network lifecycle, five limb
bindings, phase hitmask and camera; the destination retains progression and
health telemetry.

`boss_entrances.py` inventories all 22 original entrance events and applies
the approved cinematic policy after each donor adapter. Twelve entrances
contain cinematics; the others retain their adapter output. Each cinematic
instruction is replaced one-for-one, retaining relative branch offsets,
entry conditions, control flags and encounter-start ordering. Maria, Laurence,
Gehrman and Moon Presence use their original explicit warp regions for a
same-map short-warp replacement. Laurence's original client branch remains
non-relocating. Combat-phase cinematics and ending sequences are outside this
policy.

The short-warp instruction's player operand and Area destination form are
separately witnessed in the original corpus. Their combination is an inferred
implementation, not a live observation of equivalent cinematic relocation.
Native compilation and receipt verification cannot establish its runtime
positioning, orientation or multiplayer behavior.

The preceding [native matrix](https://github.com/4laric/bb-archipelago/blob/692b57bc5cd969e9a3588895f835340d37c021c5/docs/boss-composition-native-matrix.json) records 27
full-roster builds covering all 90 implemented pairs, with 59 verified files
per build. The combined `composition-26` source and frozen builds include 308
normalized ordinary swaps, 22 boss encounters and the Cathedral AP event
override; all 59 output hashes and the receipt are identical. The entrance
validator's aggregate-warp and newline-preservation changes leave all 90
generated encounter scripts byte-identical on the builder's decoded inputs.
These results establish native construction and packaging, not gameplay.

A subsequent asset audit found a construction gap in the existing Logarius
routes: his sword routine references one-shot effect `623206`, which is present
in the original m25 effect bank but absent from the other inspected map banks.
Those adapters previously copied his AI and actors without declaring that
effect bank merge. Their earlier native receipts did not prove complete
Logarius effect delivery; the gameplay consequence has not been observed.

## Reusable Maria destination and Logarius effect delivery

The Maria destination now accepts Cleric Beast, Blood-starved Beast, Paarl,
Amelia, Amygdala, Ebrietas and Laurence. This raises implemented coverage to
95 of 462 directed pairings, all usable in complete assignments, leaving 367
implementation gaps. It does not establish unrestricted or gameplay-validated
shuffle coverage.

Donor health, cooperative scaling, combat phases and startup protections are
preserved with destination-owned entry, notification, telemetry and completion
flags. Donor wake sequences signal readiness before AI activation. Maria's
entry and cooperative restoration remain intact before the shared cinematic
normalizer applies the approved replacement policy. Ebrietas's projectile
owner stays active during combat and is cleaned after destination completion.
Single-boundary music uses Maria's opening/final tracks while retaining active
fight reload recovery; two-boundary donors retain both transitions. These music
and camera choices adapt destination presentation while retaining combat.

Logarius's existing Blood-starved Beast and Wet Nurse routes now declare the
EMEVD-only `623206` dependency and merge the pinned original m25 effect bank.
The native writer checks the source event instruction, rejects parameterized
effect operands, verifies the destination encounter owns the declared event,
and checks the effect operand in the final compiled event. Binder merge
coverage includes both map-linked and EMEVD-only effect requirements.

The preceding [native matrix](https://github.com/4laric/bb-archipelago/blob/197ebf4a8d5dad6196102ff4b35e885baff501b8/docs/boss-composition-native-matrix.json) records 18
full-roster builds covering all 95 implemented pairs, with 60 verified output
files per build. Python and native writer sources, writer binary and compiler
stayed unchanged throughout. The combined `composition-26` source and frozen
builds contain 308 ordinary enemy swaps, all 22 boss encounters and the actual
Cathedral AP override; all 60 output hashes and their receipts match exactly.
These results validate native construction and packaging, not gameplay.

## Logarius combat, Laurence and Gascoigne arenas

Reusable Logarius combat now reaches all six base arenas. The package retains
his primary, sword and projectile owner as distinct source-pinned actors,
including cooperative scaling, both sword initializers, aura and cleanup.
His event-only sword effect is delivered through the source-pinned area bank;
all m24 subareas use the m24 bank. Source `ShootBullet` behavior `223200590`
references BulletParam `232250`, whose recorded fields do not add an effect
bank dependency. Destination terminal, notification and telemetry remain
arena-owned. The actual Cleric client restoration event `12411703` is pinned
separately from the retired cloth controller.

Laurence and Gascoigne now accept all six base combat packages. Their adapters
retain donor startup protections, readiness ordering and combat controllers,
while preserving destination entry, cooperation, progression and neighboring
Ludwig/Cleric events. Ebrietas retains a materialized projectile owner through
combat. Gascoigne's three original beast states remain hidden, invincible
terminal witnesses until destination completion. Both Gascoigne-specific
initializers for generic navigation controller `12415238` are removed; the
generic event body and unrelated callers remain intact. Authored per-state
primary and proxy fingerprints reject source drift before writing.

The two-track music adaptations preserve reload recovery. Laurence uses the
donor's first declared combat boundary; Gascoigne uses the final boundary,
matching its original final transformation presentation. These are presentation
choices, not changes to combat phases or evidence of compatibility limits.

Maria also reaches Laurence's arena, retaining both source combat phase signals
and cleanup. Message 100 drives Laurence's single music transition; message
300 remains part of combat. Maria native bindings now carry the authored
original primary fingerprint and initialization fields across every route.

This checkpoint implements 110 of 462 directed pairings, all feasible within
complete one-of-each assignments. The remaining 352 are implementation gaps.
It does not establish unrestricted or gameplay-validated boss shuffle.

The preceding [native matrix](https://github.com/4laric/bb-archipelago/blob/9c5aa4e/docs/boss-composition-native-matrix.json) records 20 full-roster
builds covering all 110 implemented pairs, with 60 verified files per build.
The source and frozen combined build includes 308 ordinary swaps, 22 boss
encounters and the actual Cathedral AP override; all 60 file hashes and the
receipts match. Sources and tool binaries stayed unchanged throughout that
matrix. Both full test passes ran 1,836 tests with 57 optional skips, and the
generated-data and shipping checks passed.

Composition permits a new constructor call at the boundary of an independently
removed range while still rejecting insertions inside it. This preserves
Orphan's Cleric completion bridge when Gascoigne's old navigation calls are
removed from their shared event file; synthetic and real-source regressions
cover the ordering.

The matrix above records the sources at `9c5aa4e`, before the separate map-alias
fix from PR #460. With that fix applied, the actual saved launcher seed
`31879326883593218814:1` also builds successfully using its original ordinary
plan and extracted inputs: 332 composed swaps, 22 boss encounters across 15 event files and
60 verified files. That plan mixes bare and `.msb` map names, unlike the earlier
combined fixture. The matching native harness passes, including the new alias
regressions and the existing event-only FFX checks. These checks still make no
gameplay claim.

## Orphan combat and reusable Cainhurst encounters

Orphan's reusable donor package reaches all six base arenas with source-pinned
core, phase and support actors. Both helper actors carry source initialization
and destination scaling in every physical map state. The reviewed health,
phase, support, player-effect and camera events remain connected, including
saved-phase restoration. A death bridge preserves the destination terminal
event and cleans up helpers on live completion and completed reload. No region,
generator or FFX dependency is invented from an untyped integer reference;
transitive character AI/TAE/behavior/bullet/FXR closure remains an explicit
original-data investigation gap.

The [original character-asset audit](boss-orphan-asset-audit.json) has now
identified nine direct animation-effect dependencies present in m36 but absent
from the base destination banks and global effect banks. Delivery is unfinished.
A whole-m36-bank merge also encounters two different payloads under existing
m33 effect names, so simply merging the entire bank is insufficient. The event
and map build results below do not validate this missing asset delivery.

The [broader character screening](boss-character-asset-screening.json) records
original animation archive and TAE hashes for 30 declared actor models, with
direct type-96/100 effect requests checked against the available original area
and global banks. It exposes further delivery work, including Gascoigne
effects absent from m23. This screening does not account for already generated
donor-bank imports and is neither a full-roster asset census nor proof of
transitive effect closure. Missing assets remain implementation gaps.

Cainhurst accepts all six base combat packages. Its terminal, post-boss, fog
and music-cleanup events remain exact. The original sword and projectile owner
stay pinned and inert until destination completion, including completed reload.
Source-pinned client restoration, donor readiness and destination notification,
telemetry, music and camera adaptations replace the retired Logarius combat
controllers.

Logarius also reaches Maria, Laurence and Gascoigne. Maria's music moves to the
final track at his single phase boundary while retaining reload recovery;
Gascoigne's three physical states retain their original beast as an inert
terminal witness. Laurence's replacement uses Logarius's authored entry pose
and a readiness flag cleared before constructor initialization. Initial entry,
client restoration and saved-intro reload set that flag only after actor warp
and restoration; health waits for it even when its own event was completed on
a previous attempt. Destination progression remains unchanged.

This checkpoint implements 122 of 462 directed pairings, all feasible within
complete one-of-each assignments. The remaining 340 are implementation gaps,
not proven incompatibilities. Static and native checks do not establish live
combat, arena fit or multiplayer timing.

The [current native matrix](boss-composition-native-matrix.json) records 21
full-roster builds covering all 122 constructed pairings with unchanged source
and tool hashes. Each build verifies 60 files. The actual saved launcher plan
for `31879326883593218814:1`, including its mixed map-name spellings and AP
override, produces 330 composed swaps and all 22 boss contracts. Source and
packaged builders produce identical receipts and all 60 file hashes match.
This evidence covers the emitted event/map/parameter pipeline; the character
asset audit above records a separate known gap that these checks do not cover.

Both full test passes completed with 1,852 tests and 57 optional skips
(865.676s and 807.476s). Generated-data and shipping preflight passed.


## Character effect evidence and asset conflicts

The native encounter writer and Python builder accept an input-only
`--characters` directory for plans declaring `boss_character_ffx_requirements`.
Each requirement binds an exact source map/part/entity to its model, animation
archive, embedded TAE hash, animation count and ordered type-96/100/118 effect
witnesses. The verifier reads the original archives; it does not write a
character overlay or assert complete combat-asset closure. Shared models can
serve multiple source actors only when their archive evidence agrees.
Composition retains these requirements and rejects conflicting declarations
before calling the native writer.

A real Orphan-to-Cleric native CLI smoke verifies all three source bindings
and their 30/55/0 typed witnesses in the output receipt. The native harness
passes 36 character checks including installed-original Orphan, Ludwig and
shared-human archives. Ludwig has 265 ordered witnesses, including 30 type-118 blade
effects. These add roots 645115 and 645119 to the earlier 37-root set. Both
source Ludwig actors verify against the same pinned archive; changing a
type-118 operand is rejected even when the archive hashes are updated.
The separate event-effect validator now accepts a declared positive occurrence
count and checks that exact count in source and final events, including every
matched effect operand. This preserves Ludwig's sixteen original spawns of
645114 instead of collapsing his visual sequence; omitted counts retain the
previous single-occurrence behavior. Its 39 native FFX checks pass.

The [original area-bank conflict survey](boss-area-bank-conflicts.json) records
all 13 fixed-boss area bank hashes and the different-byte intersections. Thirteen
unordered bank pairs contain 82 conflicting entries, all FXRs; no non-FXR
resource conflicts occur in this pinned set. This supports retaining all
source textures/models/animation resources while developing selective FXR
delivery. It does not prove an FXR can safely be omitted or establish runtime
bank precedence. Indexed effect and action-resource references still need
resolution before the conflicting Ludwig and Orphan routes have complete
asset delivery. Character proofs are not yet enabled by production donors.

The [direct-root availability audit](boss-character-direct-root-availability.json)
checks Ludwig and Orphan against all 37 original effect banks. Every one of
Ludwig's 39 and Orphan's 12 decoded direct roots has an original bank entry.
This locates input assets; it does not establish destination availability,
recursive effect closure, or engine load order. The typed animation decoder
is partial: the default profile covers only types 96, 100 and 118. An explicit
expanded profile now covers 96, 99, 100, 108, 109, 112 and 118. Omitted profiles
retain the legacy interpretation; arbitrary subsets and reordered profiles are
rejected. Each TAE entry carries its profile into receipt and shared-archive
comparison, so a proof cannot silently change its coverage during composition.

The expanded native harness passes 86 character assertions, including an
original corpus of 37 archives, 116 TAE entries and 44,641 ordered witnesses.
A separate full native CLI build bound the original c0000 archive to Micolash's
actual source actor (m26_00_00_00/c0000_0005/2600850): all 80 entries, 24,880
witnesses and 248 direct roots matched the nested receipt exactly, and all 60
output hashes and sizes verified. This is an archive census, not evidence of
which animations Micolash selects. It does not deliver character FXRs or prove
recursive effect closure, floor/material selection semantics or live combat.

The [additional character archive census](boss-additional-character-archive-census.json)
records seven more original archives: Gehrman, Moon Presence, Maria, Laurence,
Rom, his spider model and the shared human model used by Micolash. The last
archive contains 80 separate TAE entries. Its inventory does not identify
which entries Micolash uses. The v2 character-proof format now supports an
ordered `source_tae_entries` list per source actor/archive, and v1 normalizes
to a one-entry proof. Receipts retain each entry ID/path/hash, decoded event
types, `coverage_scope: partial-typed-witness`, and
`fxr_delivery_status: not-validated`. A full native CLI smoke verifies all
80 entries and 4,742 selected witnesses on the materialized Micolash source
binding, with 60 output files verified. This is archive evidence only, not
proof that Micolash executes every listed animation.

## Ludwig destination integration in progress

The reusable Ludwig destination is wired for five additional base donors;
the existing Cleric and Laurence destination routes retain their dedicated
implementations. That checkpoint's graph has 142 directed routes and 105
reusable recipe bindings. Every graph edge can participate in a complete
22-boss, one-of-each, no-self assignment. This is graph feasibility evidence,
not native-build or gameplay validation, and the [six direct native builds](boss-ludwig-arena-native-matrix.json) now
pass against original inputs, with eight receipt-verified files per build.
The reusable module also passes all seven focused checks, including compilation
of all six donor variants. [Five complete-roster composition builds](boss-ludwig-arena-full22-matrix.json)
cover all five new destination routes, with 22 boss contracts, 15 event files,
and 60–61 receipt-verified files per build. No gameplay or complete
character-effect delivery is claimed. The other 320 directed
pairings remain implementation work, not established incompatibilities.

The frozen preceding 137-route worktree passed both full regression passes:
1,876 tests and 57 optional skips each, in 963.692 and 972.727 seconds.
Generated-data and shipping preflight also passed. Those results do not cover
the newer Ludwig destination, multi-TAE proof, or Moon limb correction in this
worktree; these changes have separate focused and native checks.

The later frozen 142-route commit also [passed both full regression runs and
preflight](boss-142-regression-checkpoint.json): 1,884 tests and 57 optional
skips each, in 970.750 and 989.448 seconds. That checkpoint covers the Ludwig
destination, multi-TAE proof and Moon limb correction. It does not cover the
subsequent expanded typed profile or reusable final-boss donors and arenas.

Review of the next reusable donors found and corrected Moon Presence's third
limb break animation from 8010 to the original 8030. The dedicated Gehrman
route now derives every limb initializer from the shared package and verifies
each exact original initializer before emission. Its source-comparison tests
and original-input native build pass.

## Final-boss donors in progress

Gehrman and Moon Presence now expose reusable combat packages at all six base
arenas. Their source combat phases, Moon's five limb routines and player-effect
controller, and Gehrman's physical event-target actor are transplanted with
original-source pins. Destination progression and co-op entry remain owned by
the arena. Gehrman's transplanted combat actor receives TalkID 0; the separate
Hunter's Dream quest NPC is not imported.

All [twelve direct native builds](boss-final-donor-native-matrix.json) pass
against original inputs, with 8–10 receipt-verified files each. Eight focused
tests include compilation of all twelve variants. Registry integration checks
also exercise each donor/arena binding rather than only counting entries.
Two isolated shared-map native probes place Gehrman and Moon Presence together
at BSB/Paarl in both orders. Each combines both encounters into one event file,
materializes the helper in both physical map states, and verifies nine output
files. These probes explicitly override assignment selection to test shared-map
composition; they are not full-roster seeds or evidence of planner feasibility.

This brings the local adapter registry to 154 directed routes, but the twelve
new routes cannot yet occur in a full22 one-of-each assignment. The Gehrman,
Moon Presence and Micolash arenas still accept only those three donors, so
moving one outside that group leaves a destination unfilled. Incoming reusable
arena adapters are the missing implementation; this is not evidence that the
outgoing pairings are incompatible. The prior 142 graph edges remain feasible.
Character-effect delivery and live combat remain unverified for these donors.

## Reusable final arenas in progress

Gehrman and Moon Presence now accept all six base combat packages through
source-pinned arena adapters. The Gehrman adapter retains the separate dialogue
NPC, original entry trigger and warp, endings and progression; it replaces only
the combat actor. Both arenas preserve first-entry and saved-fight readiness,
client restoration and destination completion. Central replacement-entrance
handling skips the boss cinematics while retaining the required warps.

All [twelve direct original-input native builds](boss-final-arena-native-matrix.json)
pass with eight receipt-verified output files each. Each arena has seven focused
tests, including compilation of every base donor. Both adapters protect donors
until their source-authored wake sequence permits damage. An earlier
Moon/Ebrietas build hit a Windows staging-directory move error and passed a
serial retry; after the protection correction all six Moon variants passed
without retry. The evidence distinguishes these stages.

These incoming routes resolve the preceding final-group assignment restriction:
all 166 implemented directed routes now participate in complete 22-boss,
one-of-each, no-self assignments. The remaining 296 routes are implementation
gaps. [Thirteen complete-roster native builds](boss-final-arena-full22-matrix.json)
cover all 24 new outgoing and incoming final-boss routes, each with 22 contracts,
15 event files and 60–61 verified output files. After the Moon protection fix,
all six affected seeds were rebuilt successfully. Fixture selection avoided
the known Ludwig/m23 effect-bank collision without changing production planner
policy. These builds do not prove complete character-effect delivery or
gameplay behavior.

## Micolash destination and Wet Nurse donor integration

The reusable Micolash destination keeps replacement combat in the original
initial encounter area, within the original fight and music volumes. Chase,
mirror, cage and talk controllers remain inert without completing their event
flags. The original terminal and post-boss progression remain unchanged; a
bridge supplies the talk-owned death flag only after actual donor death.
All [six base-donor native builds](boss-micolash-arena-native-matrix.json)
pass with eight receipt-verified files each. Seven focused arena tests include
compilation of all six variants. Runtime navigation and arena fit remain
unobserved.

The reusable Wet Nurse donor preserves its core, support apparition and damage
proxy, six source warp regions, model-point object and nightmare combat
controllers. The destination owns entry, camera, environmental audio and
progression. All [six base-arena native builds](boss-wet-nurse-donor-native-matrix.json)
pass with 9–11 verified files each. The writer retains the entire 281-entry
source effect bank, including the original bytes of effect 655108. Its exact
EMEVD dependency manifest covers effect 655105; character animation roots and
recursive effect delivery remain separate unfinished work.

The local construction graph has 177 directed routes, all feasible in complete
one-of-each, no-self assignments. The other 285 routes remain implementation
gaps. [Seven complete-roster native builds](boss-nightmare-adapters-full22-matrix.json)
cover all twelve reusable bindings, with 22 contracts, 15 event files and
60–62 verified outputs per build. One seed exposed conflicting leading readiness
resets in the shared m34 constructor. After narrowly permitting independent
literal OFF resets before initialization, that seed rebuilt successfully;
all 19 composition tests pass, including rejection of mixed or late writes.
The preceding 166-route commit passed its first full 1,906-test regression
run (57 optional skips) and all CI checks; its second local pass remains active.
