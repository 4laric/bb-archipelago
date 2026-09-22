# Full boss shuffle: multi-actor encounter dossier

Status: static-design evidence, 2026-09-22. This is a feasibility dossier, not a
claim that any transplant has been played.

## Evidence boundary

All IDs are derived from the committed research/bb_inputs.db corpus: CUSA03173,
AppVer 01.09. Event roles come from the named original event/*.emevd.dcx.js
source and placements/NpcParams from mined/msb_enemies.tsv. They are inferred
static facts. Runtime behavior, collision, AI navigation, animation, co-op, and
completion after rewriting remain unvalidated and require the live controls in
docs/CONTRIBUTING-LIVE-PROBES.md.

The present boss catalog begins at terminal defeat and health-bar operands. It is
a useful census, but not a donor contract: it misses actors reachable only from
phase, generator, and parameterized support events.

## Design rule

A shuffled placement has two graphs.

| Graph | Owner | Required treatment |
| --- | --- | --- |
| Arena/progression | destination map | Preserve fog/action, entry/cutscene, BGM, completion event/flag, AP check, award, exit, and post-defeat state. It waits on normalized combat-complete. |
| Combat | donor encounter | Transplant explicitly mapped bodies, HP proxies, phase edges, support actors, generators, NPC parts and combat AI only. No donor reward, fog, cutscene, or completion identity may remain. |

Copying a donor terminal event would bring its HandleBossDefeat, rewards, map
flags, and cleanup. A donor must be a rewritten combat module. C means combat
body, P phase/health proxy, S support/generated combat actor, and D
destination-only infrastructure. none means the event names an entity without a
fixed-map MSB placement.

## Actor rosters

### Witch of Hemwick: m22_00_00_00, completion Event 12201800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C/P | 2200800 and 2200801, c2100 / NpcParam 210020 | Completion waits for both. Event 12204802 starts first bar; 12204807 exposes second; 12204810 enables 2200801 at 2200800 half HP. Keep pair and phase edge. |
| S | 2200810-2200812, c2050 / 205010; generators 2205000-2205002 | 12201803 stops generators and kills all three at completion. 12204811 changes core AI after 2200810 dies. These are catalog omissions. |
| D | fog 2201800/2201801, regions 2202800-2202805, music 2203800-2203803, rewards/flags | Retain at destination. |

Sources: Event 12201800 lines 311-358; 12201802 371-389; 12201803 392-410;
12204802 494-527; 12204807 578-586; 12204810 602-633; 12204811 636-644.

### Father Gascoigne: m24_01_00_00, completion Event 12411800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C/P | 2410810 (c2710 / 271000), 2410811 (c2720 / 272000) | 12414802 creates a referred-damage pair, enables both AIs and bars. Terminal completion accepts the death branch and handles both. Atomic phase pair. |
| D | entry cutscene 24010010, fog 2411810, regions 2412815/2412830, terminal award/flags | Preserve at destination. |

No other specialized combat actor is evidenced. 2410800 is Cleric Beast on the
same map, so broad map-prefix replacement is prohibited. Sources: 12411800
1362-1411; 12411802 1427-1456; 12414802 1536-1587.

### Celestial Emissary: m24_02_00_00, completion Event 12421700

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C/P | small core 2420810 (c2500 / 250080), large core 2420811 (c2570 / 257010) | 12424790 pairs damage, transfers below 0.6 HP, disables/warps small core, and enables large core/bar. Completion waits on large core. |
| S | 2420711, 12, 13, 16, 17, 19, 20, all c2500 / 250081; generators 2423711, 12, 13, 16, 17, 19, 20 | Entry 12421702/03 enables group; 12424770 kills/deactivates it when large core dies. |
| S | 2420750/51, c2571 / 257100 and 257101 | 12424791 warps them at 30%; 12424792 controls animation/effects. |
| D | fog 2421700/01, regions, SFX/music, terminal rewards/flags | Destination-owned. |

Nearby entities 2420714, 15, 18, 21-31, 2420800 and 2420801 are not proven
part of this graph by the cited events. Sources: 12421700 568-633; 12421702
646-690; 12424702 797-868; 12424770 925-936; 12424790 992-1013; 12424791
1016-1024; 12424792 1027-1042.

### Martyr Logarius: m25_00_00_00, completion Event 12501800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C | 2500800, c2320 / 232000 | Terminal, bar and phase source. |
| S | 2500801, c2321 / 232100 | 12504802 starts it hidden/immortal; 12504806 warps/enables it after core message, then disables on damage, timeout, or core death. |
| S | 2500802, c9010 / 232000 | 12504802 creates bullet owner; 12504807 shoots from it. Allocate effect-owner, not normal NPC slot. |
| D | fog/action 2501800, arena 2502807, terminal award/flags | Destination-owned. |

Sources: 12501800 1279-1321; 12504802 1463-1514; 12504806 1566-1588;
12504807 1591-1598.

### Mergo's Wet Nurse: m26_00_00_00, completion Event 12601800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C | 2600800, c5510 / 551000 | Main controlled actor. |
| S | 2600801, c5510 / 551000 | 12604840 enables, warps, commands then disables it in response to 2600800. |
| P | 2600802, c5510 / 551000 | 12604802 displays bar and creates referred-damage pairs from 2600800/01. |
| P, none | 2600803 | Terminal handles defeat on 2600803 and 12604804 waits on its death, yet it has no fixed placement. Resolve creation/link ownership before generic use. |
| D | fog 2601800, breakable 2601856, phase marker 2601857, arena/reward logic | Destination-owned unless a proven combat warp needs a marker. |

Sources: 12601800 537-587; 12601802 600-633; 12604802 715-771;
12604804 803-808; 12604840 887-926.

### Shadows of Yharnam: m27_00_00_00, completion Event 12701800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C | 2700800, c2120 / 212700; 2700801 / 212710; 2700802 / 212720 | Completion waits all three. 12704802 displays bars; 12704806 drives group death/HP AI commands. |
| S | 2700803-05, c5033 / 503300; generators 2705001-03 | 12704802 disables/sets invincibility and 12701800 disables generators at defeat. Catalog omissions. |
| S | 2700810, c2121 / 212750; 2700811/13 / 212751; 2700814 / 212750 | Constructor passes them to parameterized 12704815 as hit/attachment auxiliaries. Resolve bindings. |
| D | fog, regions, music, rewards/progress | Destination-owned. |

Sources: 12701800 386-442; 12701802 462-485; 12704802 565-628;
12704806 684-712; constructor calls for 12704807/12/15/25/30.

### The One Reborn: m28_00_00_00, completion Event 12801800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C/P | 2800800, c5070 / 507000; 2800801, c5071 / 507100; 2800802, c5072 / 507200; 2800803, c1050 / 507000 | 12804802 controls all, bars 2800803, pairs 2800800/01 to it and sets event target. 12804830 uses 2800802 as helper. Atomic multipart graph. |
| S | 2800520, 22, 24, 25, 27, 29; c1050 / 105810, CharInit 6553600 | Completion establishes backread/force-kills them; 12804802 controls their AI. |
| S | NPC part/control events 12804820, 12804830, 12804840 | Parameterized body/target bindings need resolution. |
| D | fog, entry cutscene, SFX/music, terminal flags | Destination-owned. |

Sources: 12801800 1571-1638; 12801802 1651-1683; 12804802 1768-1849;
12804820 1926-1963; 12804830 1966-1979.

### Ludwig: m34_00_00_00, completion Event 13401800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C/P | 3400800, c4510 / 451000; 3400801, c4510 / 451001 | 13404802 pairs damage, transfers update ownership and displays phase bars. |
| D | 3400810 | 13401802/03 make it invincible/treasure post-death actor; retain as destination post-completion infrastructure. |
| D | cutscenes 34000020/40, fog/rewards/flags | Do not transplant. |

Sources: 13401800 793-854; 13401801 875-904; 13401802 907-917;
13404802 989-1046.

### Living Failures: m35_00_00_00, completion Event 13501850

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| P | 3500850, c4030 / 403050 | Terminal waits on HP proxy; 13504852 displays bar. |
| C | 3500851 / 403000, 3500852 / 403010, 3500853 / 403020, 3500854 / 403030; all c4030 | 13504852 pairs every body to 3500850 and enables AIs. 13504854, 65, 81 observe group. |
| S | 3500860 | 13504852 enables it; 13505680 drives its AI commands from four bodies. Catalog omission. |
| D | fog/action 3501810, arena transition/hits, reward/post-fight flags | Destination-owned. Lady Maria is separate. |

Sources: 13501850 1053-1106; 13504852 1187-1247; 13504854, 13504865,
13504881, 13504895, 13505655, 13505680 1586-1633.

### Orphan of Kos: m36_00_00_00, completion Event 13601800

| Role | IDs and static evidence | Contract requirement |
| --- | --- | --- |
| C/P | 3600800, c4540 / 454000; 3600801, c4541 / 454100 | 13604802 pairs damage and bars 3600801; 13604820 changes phase below half HP. |
| S | 3600803, c4543 / 454300 | 13604830 commands it from phase-two event messages/effects. Catalog omission. |
| D | 3600802, c4550 / 455000 | 13601802 stages it and 13601803 waits for death for post-fight cutscene/arena state. Not a phase body. |
| D | fog 3601800, object 3601811, cutscenes 36000000/10, SFX/reward | Destination-owned. |

Sources: 13601800 715-761; 13601802 814-828; 13601803 831-897;
13604802 960-1020; 13604820 1099-1121; 13604830 1124-1137.

## Recommended generic architecture

Implement a typed, evidence-pinned EncounterContract, not a collection of
ordered-pair hand-written swaps.

1. Extend tools/build_boss_catalog.py with bounded dependency traversal. Start
   at terminal, bars and constructor bindings; follow only resolved event calls,
   character/generator operations, referred-damage/event-target links and phase
   predicates. Store event ID, source line, binding and digest. An unresolved
   parameter is a build error.
2. Each donor declares capabilities: core, phase, hp_proxy, support, generator,
   effect_owner and required marker/region. Each destination declares supplied
   slots/markers. Reject cardinality/capability mismatches before writes; never
   map numeric suffixes.
3. Clone only contract-listed combat events into destination allocated event
   range. Rewrite every declared actor, generator, region/marker and local flag
   through typed maps. Replace donor entry with destination encounter_start and
   donor terminal with encounter_complete. Reject unclassified numeric operands
   and hash-pin original blocks.
4. Preserve the original destination terminal event. Replace only its death
   condition with normalized completion, retaining AP location, award, exit,
   fog cleanup and progression identity.
5. Extend the writer to clone/map exact MSB actor records and generator bindings,
   including model, NpcParam, ThinkParam and CharaInit. Verify each rewritten
   EMEVD entity exists in output MSB. Manifest donor/destination mappings,
   source/output hashes and untouched destination terminal hash.

## Delivery and blockers

Make these rosters golden static fixtures first; tests must explicitly witness
Witch 2200810-12, Shadows 2700803-05/generators, Living Failures 3500860, and
Orphan 3600803. Then add the destination completion adapter and writer verifier
before enabling any new pair.

Resolve Wet Nurse 2600803 creation/link, generator/marker cloning, target-arena
floor/home/warp constraints, and co-op with narrow pre-registered live controls.
Validate representative shapes separately: phase pair, proxy-plus-clone,
ensemble-plus-proxy, generated support, transformation/warp, multipart body.
A pair becomes supported only after boot, entry, phases/auxiliaries, bar/damage,
destination AP check/reward/exit, save/reload, and no donor progression change.

Multi-actor encounters therefore do not make full shuffle infeasible. They rule
out a single-NPC-param substitution model: the generic unit is a typed donor
combat graph plus a destination-owned progression adapter.
