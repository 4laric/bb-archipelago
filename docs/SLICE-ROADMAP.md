# The content-slice roadmap: from the Blood-starved Beast to Mergo's Wet Nurse

Regenerated 2026-08-26 against `80a6341be03ad999a9f9ba60239b9d52cf5d8d94`
(`git log --oneline -1`). Every number below names the command that reproduces
it. Anything not reproducible from the committed corpus is labelled `TO-MINE`
(the corpus cannot answer it yet) or `INFERRED` (the corpus corroborates it but
does not settle it), per `docs/RESEARCH-BASELINE.md`.

This is a specification for the remaining base game, not a schedule. It says
what each slice must contain, what evidence already exists for it, and what
would have to be mined or witnessed before it could ship. It deliberately does
not promise that a slice will be built.

**Companion document.** This file is the *content* layer: which rows each slice
seeds and how the suppression plan grows. The *reachability* layer — which
pooled item or event flag opens which region, with the EMEVD condition that
evidences it — is `docs/LOGIC-RULES-ROADMAP.md`. Three findings there correct
or extend claims made here: the Cainhurst carriage requires the Hemwick boss
(cited), the Tonsil Stone amygdala is an `m28` character rather than a Cathedral
Ward one (cited), and the Yahar'gul abduction path is now traced end to end.

## Where the project actually stands

Slice 3 seeds Central Yharnam, Cathedral Ward, Old Yharnam and the Grand
Cathedral, with the Blood-starved Beast as the goal:

```bash
python3 -c "from worlds.bloodborne import data; import collections; \
print(len(data.SLICE_LOCATION_KEYS)); \
print(collections.Counter(l.region for l in data.LOCATIONS if l.key in data.SLICE_LOCATION_KEYS))"
# 167
# Cathedral Ward 62, Old Yharnam 55, Central Yharnam 48, Grand Cathedral 2
```

```bash
python3 tools/plan_vanilla_suppression.py --output /tmp/plan.json
python3 -c "import json; print(len(json.load(open('/tmp/plan.json'))['edits']))"   # 179
```

167 network locations, a 179-edit suppression plan, zero refusals. The world
model itself is much larger than the slice — `len(data.LOCATIONS)` is 195 and
`data.REGIONS` already names all 25 regions including the DLC — and, critically,
`data.ITEMS` already carries the locked event items for **Shadows of Yharnam,
Rom, The One Reborn, Micolash, Mergo's Wet Nurse and the Forbidden Woods
password**. The scaffolding for the end of the base game exists. What does not
exist is the seeded content behind it.

So the work each slice adds is not "invent a model". It is: pull rows out of the
location catalog into the shipping manifest, give them ids, let the suppression
planner regrow, rebuild and pin the binder, and run a witness pass on regions
nobody has ever observed.

## The corpus, and what it can and cannot see

Three sources carry this document:

- `research/catalog/fixed_location_catalog.tsv` — 651 canonical MSB-placed fixed
  treasures across 16 maps.
- the decompiled event archives in the inputs bundle — 27 files
  (`python3 tools/bb_inputs.py --list`), which is **every base-game map plus
  `common.emevd`**.
- `research/joined/lot_items.tsv`, the ItemLotParam join that turns a lot into
  items and acquisition flags.

The bundle covers `m21` (Hunter's Dream / Abandoned Workshop), `m22`, `m23`,
`m24_00/01/02`, `m25`, `m26`, `m27`, `m28`, `m32`, `m33`, plus the DLC block
`m34`-`m36` and the chalice archive `m29`. **No slice in this roadmap fails
closed for missing MSB or EMEVD coverage.** That is worth saying plainly,
because it is the failure mode this section was written to look for and it did
not occur.

Two things the corpus genuinely cannot see, and both bite later slices harder
than they bit slice 3:

1. **Boss-flag writes.** Per `docs/SLICE3-WITNESS-PASS.md`, no `SetEventFlag`
   anywhere in the 27 archives writes a boss flag; the engine turns on an
   event's own ID when the event reaches `End`. Every boss check in every slice
   below inherits `corpus_gap: implicit_write`. Mining cannot close it.
2. **ESD talk awards** (bb#204). Dialogue-granted goods are invisible to
   `plan_vanilla_suppression.py` — it refuses ambiguity but cannot refuse what
   it cannot see. `docs/PROGRESSION-VALIDATION.md` records that a 271-file ESD
   dump exists on the owner's machine; it is **not** in `research/bb_inputs.db`.
   Every NPC-dense slice below therefore carries an unmeasured award surface.

### The candidate-count estimator, and why it is trustworthy

For each map, take the canonical catalog rows, drop the `差し替え用`
("replacement") rows that slice methodology collapses into their canonical
pickup, and add the continuation rows — extra ItemLotParam rows sharing one
acquisition flag, the Hunter Set shape. That sum should predict the suppression
plan's size.

```bash
python3 - <<'PY'
import csv, collections
lots = collections.defaultdict(set)
for r in csv.DictReader(open('research/joined/lot_items.tsv'), delimiter='\t'):
    for f in (r['slot_acquisition_flag'], r['generic_acquisition_flag']):
        if f and f not in ('0', '-1'):
            lots[f].add(r['item_lot_id'])
net, extra = collections.Counter(), collections.Counter()
for r in csv.DictReader(open('research/catalog/fixed_location_catalog.tsv'), delimiter='\t'):
    if '差し替え' in r['event_names']:
        continue
    net[r['canonical_map']] += 1
    n = len(lots.get(r['location_flag'], ()))
    if n > 1:
        extra[r['canonical_map']] += n - 1
for m in sorted(net):
    print(m, net[m], extra[m], net[m] + extra[m], sep='\t')
PY
```

Run against the three maps slice 3 actually shipped, that estimator returns
**178**. The plan is **179**. The single-row difference is lot `31000`, the
Oedon Tomb Key's script award — the one `SCRIPT_AWARD_SUPPRESSIONS` entry,
which by construction has no MSB placement to be counted from. The estimator is
therefore calibrated rather than guessed, and the per-slice numbers below
inherit that calibration. They remain estimates: a review that rejects a row for
a shared or absent flag lowers the seeded count without lowering the plan.

| map | net catalog rows | continuation rows | plan estimate | unresolved (gem) rows |
|---|---:|---:|---:|---:|
| m21_00_00_00 Hunter's Dream | 1 | 0 | 1 | 0 |
| m21_01_00_00 Abandoned Workshop | 3 | 5 | 8 | 0 |
| m22_00_00_00 Hemwick | 32 | 0 | 32 | 3 |
| m23_00_00_00 Old Yharnam *(shipped)* | 54 | 2 | 56 | 3 |
| m24_00_00_00 Cathedral Ward *(shipped)* | 61 | 8 | 69 | 7 |
| m24_01_00_00 Central Yharnam *(shipped)* | 50 | 3 | 53 | 1 |
| m24_02_00_00 Upper Cathedral Ward | 19 | 6 | 25 | 1 |
| m25_00_00_00 Cainhurst | 27 | 4 | 31 | 2 |
| m26_00_00_00 Nightmare of Mensis | 53 | 0 | 53 | 8 |
| m27_00_00_00 Forbidden Woods | 75 | 5 | 80 | 10 |
| m28_00_00_00 Yahar'gul | 49 | 7 | 56 | 6 |
| m32_00_00_00 Byrgenwerth + Lecture Building | 17 | 2 | 19 | 2 |
| m33_00_00_00 Nightmare Frontier | 40 | 0 | 40 | 6 |

The "unresolved" column counts category-8 rows: procedurally generated blood
gems, which `research/catalog/fixed_location_items.tsv` classifies
`generated_blood_gem` with an empty English name. They have real acquisition
flags, so they can be checks; what they cannot be yet is *pool items*, because a
generated gem has no static identity to grant. Treat them as check-only rows and
expect filler to absorb the difference. `TO-MINE`: whether a category-8
descriptor can be granted natively at all.

### The boss roster, from one query

Every boss in the game, with the event that ends its fight and the entity it
kills, is recoverable in one pass. This is the roster the rest of the document
uses; nothing below names a boss that is not in it.

```bash
python3 tools/bb_inputs.py --extract work/inputs
python3 - <<'PY'
import re, glob, os
for f in sorted(glob.glob('work/inputs/event/m*.emevd.dcx.js')):
    cur = None
    for i, l in enumerate(open(f, encoding='utf-8', errors='replace'), 1):
        m = re.search(r'\$Event\(\s*(\d+)', l)
        if m: cur = m.group(1)
        d = re.search(r'HandleBossDefeat\((\d+)\)', l)
        if d: print(os.path.basename(f), i, cur, d.group(1), sep='\t')
PY
```

| map | event (= flag) | entity | identity |
|---|---|---|---|
| m21_00_00_00 | 12101800, 12101850 | 2100800, 2100810 | Hunter's Dream fights — `TO-MINE` |
| m22_00_00_00 | 12201800 | 2200800 | Witch of Hemwick (`INFERRED` from the map) |
| m23_00_00_00 | 12301800 / 12301700 | 2300800 / 2300810 | Blood-starved Beast *(shipped)* / second Cleric Beast |
| m24_00_00_00 | 12401800 | 2400800 | Vicar Amelia *(shipped)* |
| m24_01_00_00 | 12411700, 12411800 | 2410800, 2410810/2410811 | Cleric Beast, Gascoigne *(shipped)* |
| m24_02_00_00 | 12421800, 12421700 | 2420800, 2420811 | Celestial Emissary / Ebrietas (`INFERRED`) |
| m25_00_00_00 | 12501800 | 2500800 | Martyr Logarius (`INFERRED`) |
| m26_00_00_00 | 12601800, 12601850 | 2600803, 2600850 | Mergo's Wet Nurse, Micolash — **already in `data.py`** |
| m27_00_00_00 | 12701800 | 2700800 | Shadows of Yharnam — **already in `data.py`** |
| m28_00_00_00 | 12801800 | 2800803 | The One Reborn — **already in `data.py`** |
| m32_00_00_00 | 13201800 | 3200800 | Rom — **already in `data.py`** |
| m33_00_00_00 | 13301800 | 3300800 | Amygdala (`INFERRED`) |

The five flags already in `data.py` (12701800, 13201800, 12801800, 12601850,
12601800) were written from the model side, and this query independently agrees
with all five. The six not in `data.py` are new bindings each slice must add,
and each needs its `HandleBossDefeat` entity resolved against `NpcParam` the way
`SLICE3-WITNESS-PASS.md` resolved 2300800 and 2400800 — that is the step that
turns "an ID in the right range" into a named boss. It is cheap, purely static,
and **not done for any of the six.**

### The script-award census

`SCRIPT_AWARD_SUPPRESSIONS` exists because lot `31000` is awarded by EMEVD, not
placed in an MSB, and its `getItemFlagId` is `-1`. Every map has this shape.

```bash
for f in work/inputs/event/m*.emevd.dcx.js work/inputs/event/common.emevd.dcx.js; do
  echo "$(basename $f) $(grep -o 'AwardItemLot([0-9]*)' $f | sort -u | tr '\n' ' ')"
done
```

Resolved through `lot_items.tsv`, the awards that matter per map are:

| map | lot | awards | flag |
|---|---|---|---|
| m22 | 21002950 | ritual material x4, Witch of Hemwick reward | **-1** |
| m24_01 | 2410990 | goods 4003, the marked Cainhurst invitation (Iosefka's clinic) | 52410990 |
| m24_02 | 2420900 | goods 4006, Orphanage 1F key, brainsucker fixed drop | 52420900 |
| m24_02 | 25700000 / 25700005 | messenger gift rows | -1 |
| m24_02 | 80000300 | fixed chalice — **out of scope** | 5009 |
| m25 | 2500910 | goods 4308, the *unmarked* Cainhurst invitation | 52500910 |
| m25 | 2502000 | post-boss treasure (Logarius) | 52502000 |
| m26 | 21000 | Mergo's Wet Nurse drop | **-1** |
| m26 | 2605000 / 2605010 | gesture award and kill award at the `邪眼` | 52605000 / 52605010 |
| m26 | 55100000 | goods 4323, Third Umbilical Cord | 50000305 |
| m27 | 2700990 / 2700995 | Shadows of Yharnam forced award | 52700950 |
| m27 | 43100, 43840 | League leader departure; executioner NPC kill | 50002300 / 50002640 |
| m28 | 50700000 | The One Reborn reward | **-1** |
| m32 | 3200810 | goods 4013, the Provost's-attic key | 53200810 |
| **common** | 3200800 | **Rom's defeat award** | 53200800 |
| m33 | 80000200 | fixed chalice — **out of scope** | 5006 |

Two findings here change how the work must be done.

**Rom's award lives in `common.emevd`, not in `m32`.** A per-map EMEVD sweep —
exactly the sweep that would feel sufficient — misses it. Any slice touching Rom
must grep `common.emevd.dcx.js` as a first-class source. Slice 3 never had to,
so this is a new failure mode rather than a known one.

**Four script awards carry `getItemFlagId = -1`,** the same shape as lot 31000:
Hemwick, Mergo's Wet Nurse, The One Reborn and the messenger rows. Each is a
`SCRIPT_AWARD_SUPPRESSIONS` decision, each records `-1` literally, and — exactly
as with Gascoigne — the *check* for those fights is the boss's own defeat flag,
not the lot. Budget one reviewed declaration per row, not one per map.

---

## Slice 4 — Hemwick Charnel Lane (m22) and Castle Cainhurst (m25)

Two optional side-spurs off the Grand Cathedral, neither on the critical path,
both already modelled in `data.py` (`Road to Hemwick`, `Cainhurst carriage`).

- **Maps.** `m22_00_00_00` (Hemwick Charnel Lane), `m25_00_00_00` (Forsaken
  Castle Cainhurst).
- **Entry gates.** `Grand Cathedral -> Hemwick Charnel Lane` is free
  (`data.py`, `Road to Hemwick`; the road starts left of the cathedral
  entrance, which is why it hangs off the plaza and not off Cathedral Ward).
  `Hemwick -> Castle Cainhurst` costs the pooled `cainhurst_summons`.
  Evidence class: **pooled key in `data.py`** for the summons; **INFERRED** for
  the obelisk interaction, which no committed EMEVD condition has been traced
  to — the corpus has both *invitation* lots (2410990 marked, 2500910 unmarked)
  but nothing yet ties either to the carriage. `TO-MINE`.
- **Candidate checks.** m22: 32 net (+0 continuation) → plan ≈ 32, 3 gem rows.
  m25: 27 net (+4) → plan ≈ 31, 2 gem rows. Together **≈ 59 new locations, plan
  growth ≈ 63 edits** (179 → ~242).
- **Key items in the ground.** m22 holds the Rune Workshop Tool (52200360),
  already a `data.py` location. m25 holds the Vileblood Register (52500170),
  Executioner's Gloves (52500250, already modelled), Reiterpallasch, Evelyn and
  the Knight and Executioner sets — an unusually equipment-dense map, which
  makes it the strongest base-game argument for the #207 pool work landing
  first.
- **Bosses and goal.** Witch of Hemwick (12201800 / 2200800) and Martyr Logarius
  (12501800 / 2500800). Neither is a defensible goal: both are optional in
  vanilla, and a goal on an optional spur makes every non-spur check filler.
  **Slice 4 should keep the Blood-starved Beast goal and simply widen the seed.**
  It is a pool-growth slice, not a progression slice, and calling it that is
  more honest than inventing a goal for it.
- **Witness posture.** Two new boss flags, both `corpus_gap: implicit_write`,
  both still needing the entity→`NpcParam` identity step. Two new pickup
  canaries — one per map archive, since per the slice-3 checklist one region's
  canary is not another's.
- **Script awards.** m22 lot 21002950 (flagless, Witch reward); m25 lots 2500910
  and 2502000. Three declarations.
- **ESD exposure.** **High for m25.** `docs/PROGRESSION-VALIDATION.md` already
  records the Cainhurst Badge as having no fixed placement and no
  `AwardItemLot`: Annalise's `t250307.py` sets flags 72500332 and 72500312 on the
  Vileblood oath and the badge appears to be a covenant side effect. That is
  bb#204's shape sitting in the region this slice would seed. m22 is nearly
  NPC-free by comparison.
- **Risks.** The badge above is the honest blocker: a slice that seeds Cainhurst
  and cannot see one of its two signature rewards is shipping a known hole.
  Second, subtler: the Cainhurst Summons is a *script* award in `m24_01` (lot
  2410990, flag 52410990) sitting in Iosefka's Clinic — a region reachable only
  past Amelia through the Forbidden Woods. Its check therefore belongs to slice
  5, not slice 4, even though the item it grants gates slice 4. The pool makes
  that fine; the *logic* must not quietly assume the vanilla source is in-slice.

## Slice 5 — Forbidden Woods (m27), Byrgenwerth (m32) and the Rom goal

The first genuinely progression-shaped slice since slice 3, and the largest
single content step in the roadmap.

- **Maps.** `m27_00_00_00` (Forbidden Woods, and the clinic's far side),
  `m32_00_00_00` (Byrgenwerth — **and the Lecture Building**, see below).
- **Entry gates.** `Cathedral Ward -> Forbidden Woods` costs
  `event_forbidden_woods_password`, which slice 3 *already emits*: the
  `interaction_laurences_skull` check (flag 12401803) carries it as a locked
  item. Slice 5's front door is already built and already seeded — **the
  cheapest entry gate in the roadmap.** `Forbidden Woods -> Iosefka's Clinic` is
  free; `Forbidden Woods -> Byrgenwerth` costs `event_shadows_defeated`. All
  three are pooled/`data.py` evidence class.
- **Candidate checks.** m27: 75 net (+5) → plan ≈ 80, **10 gem rows** (the
  largest unresolved block in the base game). m32: 17 net (+2) → plan ≈ 19.
  Plus the two deferred Iosefka's Clinic manifest rows that already exist and
  are already suppressed (`fixed_central_yharnam_lot_2410140`,
  `fixed_central_yharnam_lot_2410640`, per `docs/FIXED-LOCATION-CHECKS.md`) and
  the Cainhurst Summons script award (52410990). **≈ 95 new locations, plan
  growth ≈ 96 edits**, since the clinic pair is already planned.
- **🛑 The corpus contradicts the proposed grouping.** `m32_00_00_00` is not
  Byrgenwerth alone. Seven of its 17 net rows are tagged `悪夢教室` ("nightmare
  classroom") — the Lecture Building — including the Augur of Ebrietas
  (53200600) and the Red Jelly and Madman's rows on 1F and 2F. The Lecture
  Building is **not `m33`**. `m33_00_00_00` is the Nightmare Frontier: 40 net
  rows, all generic `Item_宝死体NN` corpses, holding the Messenger's Gift
  (53300330) and Amygdala (13301800). Both halves of "slice 7 = Lecture Building
  (m33)" are wrong, and this document adopts the corpus split instead: m32 =
  Byrgenwerth (10 rows) + Lecture Building (7 rows); m33 = Nightmare Frontier.
  Because regions are logical rather than map-keyed, a slice can seed the ten
  Byrgenwerth rows and defer the seven `悪夢教室` ones by event name — a per-row
  split, cheap, but it must be *deliberate*, or the Lecture Building leaks into
  a seed with no route to it.

```bash
python3 - <<'PY'
import csv
rows = [r for r in csv.DictReader(open('research/catalog/fixed_location_catalog.tsv'), delimiter='\t')
        if r['canonical_map'] == 'm32_00_00_00' and '差し替え' not in r['event_names']]
lec = [r for r in rows if '悪夢教室' in r['event_names']]
print(len(rows), len(lec), len(rows) - len(lec))   # 17 7 10
PY
```
- **Bosses and goal.** Shadows of Yharnam (12701800) and Rom (13201800), both
  already in `data.py`. **Rom is the goal candidate**, and a good one: the model
  already carries `event_rom_defeated`, Rom is on the vanilla critical path, and
  the slice's front gate is already seeded.
- **Witness posture.** Two boss flags, both `implicit_write`. Two new map
  canaries. One extra: 53200810 (the Provost's-attic key, goods 4013) is *both*
  a placed treasure and an `AwardItemLot` target, a shape slice 3 never had —
  witness it directly rather than assuming which path sets the flag.
- **Script awards.** m27: 2700990 / 2700995 (the Shadows' forced award — note
  its flag is **52700950**, which does *not* match the lot number, so the usual
  lot↔flag heuristic silently fails here), 43100 (League leader), 43840
  (executioner NPC drop). m32: 3200810. **`common.emevd` 3200800 — Rom's
  award.** Five declarations, one of them in a file per-map tooling does not
  read.
- **ESD exposure.** **The worst in the base game.** The Forbidden Woods is where
  the League (Valtr), Alfred and the woods NPCs live, and two of the three m27
  script awards are already NPC-conditioned. bb#204 step 1 — packing the ESDs
  into `bb_inputs.db` plus a census tool — should be treated as a
  **prerequisite** for this slice rather than a follow-up. Shipping m27 blind to
  talk awards means shipping a region whose award surface has never been
  counted.
- **Risks.** Size. 95 locations is more than slice 3 added in total, and it
  pushes the seed past 260 checks against a pool that, even post-#207, is only
  just large enough. Splitting into 5a (Forbidden Woods, no goal) and 5b
  (Byrgenwerth + the Rom goal) is the obvious relief valve and costs one extra
  witness pass.

## Slice 6 — Yahar'gul, the Unseen Village (m28) and The One Reborn

- **Maps.** `m28_00_00_00`.
- **Entry gate.** `Byrgenwerth -> Yahar'gul` costs `event_rom_defeated` — the
  Blood Moon transition, `data.py`, pooled-event evidence class. If slice 5
  shipped Rom as its goal, slice 6's gate needs no new work at all.
- **Candidate checks.** 49 net (+7 continuation) → **plan ≈ 56**, 6 gem rows.
- **Key items in the ground.** The **Upper Cathedral Key** (52800290, event tag
  `宝死体29_ミイラ` — the mummy) is an m28 pickup and is already a `data.py`
  location assigned to Yahar'gul. This is the corpus settling a question the
  proposed shape left open: the Upper Cathedral Key's *vanilla home is slice 6*.
- **Bosses and goal.** The One Reborn (12801800 / 2800803), already in
  `data.py`. It is a serviceable goal — on the critical path, exactly one region
  deep — but a weak one, because Yahar'gul alone is a thin slice and the region
  past it is one door away. **Consider folding slice 6 into slice 7** unless the
  seed size after slice 5 argues for a breather. An option, not a decision.
- **Witness posture.** One boss flag, `implicit_write`. One map canary.
- **Script awards.** Lot 50700000 (The One Reborn's reward), flag **-1** — the
  Gascoigne shape. One declaration.
- **ESD exposure.** Low to moderate; Yahar'gul's NPCs are mostly hostile.
- **Risks.** The kidnapper-abduction path is `TO-MINE`. Nothing in this document
  traces how the early, pre-Blood-Moon Yahar'gul variant is flagged, and a seed
  that lets a player be abducted into a region the logic believes is locked is a
  real hazard rather than a cosmetic one. **This is the most important unmined
  thing in slice 6.**

## Slice 7 — Lecture Building (m32, `悪夢教室`) and Nightmare of Mensis (m26), ending at Mergo's Wet Nurse

The end of the base game.

- **Maps.** the `m32_00_00_00` Lecture Building rows (7 net) and
  `m26_00_00_00` (Nightmare of Mensis, 53 net).
- **Entry gates.** `Yahar'gul -> Lecture Building 2F` costs
  `event_one_reborn_defeated` (`data.py`, the Advent Plaza mummy).
  `Lecture Building 2F -> Nightmare of Mensis` is free (the giant door).
  Mergo's Wet Nurse costs `event_micolash_defeated`, already expressed as a rule
  on `boss_mergos_wet_nurse`. All pooled/`data.py`.
- **Candidate checks.** m26: 53 net (+0) → plan ≈ 53, **8 gem rows**. The m32
  Lecture Building remainder: 7 net. **≈ 60 new locations, plan growth ≈ 60.**
- **Key items in the ground.** Two **Iron Door Key** rows in m26 — 52600550
  (inside the `悪夢の主宝死体` tag, the Wet Nurse's own corpse) and 52600610.
  Two rows, one item name: precisely the "flags shared by unrelated lots" shape
  the expansion procedure says to reject until the coupling is understood.
  `TO-MINE`, and it sits on the critical path's doorstep. The Lecture Theatre
  Key (53200720) and the Provost's-attic key (goods 4013) also want pool
  entries; neither is in `data.ITEMS` today.
- **Bosses and goal.** Micolash (12601850 / 2600850) and **Mergo's Wet Nurse
  (12601800 / 2600803) — the base-game goal.** Both already in `data.py` with
  the correct dependency between them.
- **Witness posture.** Two boss flags, `implicit_write`. Two canaries.
- **Script awards.** m26 lot 21000 (the Wet Nurse drop, flag **-1**), 2605000
  and 2605010 (the `邪眼` gesture award and kill award — a *gesture*-conditioned
  award, a mechanism this project has never suppressed), and 55100000 (Third
  Umbilical Cord, goods 4323, flag 50000305). Four declarations, one of a novel
  kind.
- **ESD exposure.** Moderate. Micolash's dialogue is scripted rather than
  award-bearing, but the umbilical-cord economy touches the ending choice, and
  the cords are exactly the item class most likely to ride an ESD grant.
- **Risks.** The ending — see below.

---

## Out of scope, and the questions that decide it

**Upper Cathedral Ward (`m24_02`).** 19 net rows (+6 continuation) → plan ≈ 25;
two bosses (12421800 Celestial Emissary, 12421700 Ebrietas, both `INFERRED`);
one script award for the Orphanage key (2420900, goods 4006) and one fixed
chalice award (80000300) that is out of scope by the chalice rule. Both its
gating keys — `upper_cathedral_key` and `orphanage_key` — are **already pooled
in `data.ITEMS`**, its entrance already carries the correct "key + Blood-starved
Beast" rule, and both `script_award_orphanage_key` and
`treasure_cosmic_eye_watcher_badge` are already `data.py` locations. It is the
most *ready* unshipped region in the game. Because the Upper Cathedral Key's
vanilla home is Yahar'gul but the key itself is shuffled, UCW can attach to any
slice from 4 onward without a logic contradiction. **Recommendation: a ~25-edit
mini-slice attached to slice 4**, which gives that otherwise goal-less
pool-growth slice a real progression spine — two pooled keys that open real
checks — and stops the already-written UCW bindings from rotting. Ebrietas as an
*optional* goal is a genuine possibility and is left open.

**Hunter's Dream and the Abandoned Workshop (`m21`).** 4 net rows across two
archives, but `m21_01_00_00` shows 5 continuation rows against 3 net — a ratio
that says the Workshop's lots are shared-flag-heavy and need review before any
of them seed. `m21_00_00_00` also holds 10 distinct `AwardItemLot` calls, more
than any other base-game map: the Dream is where the game hands out starting
kit, messenger gifts and Insight rewards. Both facts point the same way — **the
Dream is a suppression problem, not a content problem** — and it should be
scoped on its own rather than bolted onto a slice.
`treasure_old_hunter_bone` (52110000) already sits in `data.py` under the
Healing Church Workshop.

**Nightmare Frontier (`m33`) and Lecture Building 1F.** 40 net rows, Amygdala
(13301800), reached by `Amygdala's grasp` from Cathedral Ward at the cost of the
pooled `tonsil_stone`. Entirely optional, entirely modelled, and almost entirely
filler: 39 of its 40 rows are filler or gems, the exception being the
Messenger's Gift. It is the cheapest possible pool-growth slice and the least
interesting one. Attach where convenient.

**Chalice Dungeons.** Out, per `docs/PROGRESSION-DAG.md`. `m29.emevd.dcx.js` is
in the bundle (445 KB) but no chalice MSB rows are in the catalog, and the two
fixed-chalice `AwardItemLot` rows found above (80000200 in m33, 80000300 in
m24_02) should be left unsuppressed: suppressing a chalice award in a build with
no chalice content buys nothing and perturbs the ritual economy for free.

**The Old Hunters.** Out. Its maps (`m34`-`m36`, 144 net rows) are fully bundled
and its regions fully modelled, so the DLC is a *deliberate* deferral rather
than a blocked one. Note the pool boundary already recorded in `data.py`:
`EquipParamWeapon` ids ≥ 23000000 are the DLC block and are deliberately absent
from the wave-1 weapon pool.

**The endings.** Unanswered, and it needs answering before slice 7 can be called
finished rather than merely built. Mergo's Wet Nurse is not the last event of
the base game; it is the last *boss before a choice*. Three questions, none
settled by the corpus: whether the goal should fire on the Wet Nurse flag
(12601800) or on an ending flag; whether the three umbilical cords become pool
items, which would make the third ending a logic requirement; and whether
Gehrman and the Moon Presence become bosses at all. Recorded here as an open
design question in the shape `docs/LOGIC-MODEL.md` uses, not as a task.

---

## The per-slice engineering checklist

Distilled from what slice 3 actually touched (`git show --stat 1ac7537`, 23
files) plus the witness pass that followed it (`bfa2da6`). This is a template; a
slice that skips a step should say why in its commit message.

1. **Regions and gates.** Add the region to `data.SLICE_REGIONS`; add or verify
   its `Entrance` rows. Every entrance must appear in `DOCUMENTED_GATES` or
   `DOCUMENTED_FREE` in `tests/test_bloodborne_gates.py` — an undocumented edge
   fails a test rather than going unnoticed, which is how the Hemwick edge was
   eventually caught. Add new scripted checks to
   `SLICE_SCRIPTED_LOCATION_KEYS` explicitly; region membership alone must never
   sweep an unreviewed check into multidata.
2. **Bindings.** For each new boss, resolve the `HandleBossDefeat` entity
   against MSB and `NpcParam`, and cite the *event body*, never a reader of the
   flag. `SourceCitationTests.test_every_scripted_binding_cites_its_own_event_definition`
   enforces the citation.
3. **`ids.tsv`.** Append only. Never renumber a published id.
4. **`fixed_locations.tsv`.** Rows come from
   `tools/build_fixed_location_slice.py` reading the catalog; the builder
   refuses a row whose flag/lot pair has no MSB or EMEVD placement reference.
   Reject flags shared by unrelated lots until the coupling is understood — the
   Hunter Hat row (flag 52410610, four lots) is the standing example of a
   correct refusal.
5. **Script awards.** Any EMEVD `AwardItemLot` in the new maps that awards a
   pooled item, or that has `getItemFlagId = -1`, needs a reviewed
   `SCRIPT_AWARD_SUPPRESSIONS` entry. **Grep `common.emevd` too.**
6. **Plan regen and pin move.** `python3 tools/plan_vanilla_suppression.py`;
   zero refusals, or an explicit decision per refusal; move the plan pin
   (`tools/check_suppression_plan_pin.py`) and the digest in the same commit.
7. **Binder rebuild.** Rebuild from the bundle's `parambnd/` bytes so CI can
   reproduce it (bb#138), and confirm the build-manifest hash the runtime
   compares against before arming.
8. **Counts.** Raise `tests/expected_counts.tsv` in the commit that earns it. A
   green run that collected fewer tests is not a green run.
9. **Witness pass.** The static half first — `tools/audit_slice3_witnesses.py`
   generalised to the new maps — so the live session is as short as possible.
   Then the live half: two quiescent control snapshots, one pickup canary *per
   map archive*, each boss flag confirmed after the `HandleBossDefeat` delay and
   again after a full restart, and a final check that no earlier step turned on
   a flag a later step was supposed to turn on.
10. **Playtest seed.** One generated seed played to the slice goal, recorded in
    `docs/PLAYTESTING.md` with serial and AppVer.

## What would most improve this document

Three mines, in the order they pay off:

1. **The ESD corpus** (bb#204 step 1). It is a prerequisite for slice 5, and it
   is the only item here that can invalidate a shipped slice's honesty rather
   than merely delay one.
2. **Boss entity → `NpcParam` identities** for the six unbound bosses. Cheap,
   purely static, and it converts six `INFERRED` roster rows into
   `corpus_complete` ones.
3. **The Yahar'gul abduction path.** Unmined, and unlike the other two it is a
   *logic* risk rather than an evidence one.
