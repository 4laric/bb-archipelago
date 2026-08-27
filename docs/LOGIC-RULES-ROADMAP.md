# The item-logic rule map: reachability for the rest of the base game

Mined 2026-08-26 against `5d7c541` (`git log --oneline -1`), using the committed
inputs bundle (`python3 tools/bb_inputs.py --extract work/inputs`) — all 27
base-game event archives plus `common.emevd`, and `params/EquipParamGoods.csv`.

This is the **logic layer** on top of `docs/SLICE-ROADMAP.md` (bb#210). That
document says *what content each slice contains*. This one says *what has to be
in the player's inventory for it to be reachable*.

## Why this is a separate file and not the second half of SLICE-ROADMAP.md

They have different evidence bases, different consumers and different lifecycles.

- SLICE-ROADMAP's numbers come from the **catalog and ItemLotParam** — how many
  rows a map contributes, how the suppression plan grows. Its per-slice sections
  are consumed once, by the PR that ships that slice's manifest.
- This document's claims come from **EMEVD conditions** — `PlayerHasItem`,
  `EventFlag`, `ObjActEventFlag`, `WarpPlayerToRespawnPoint`. Its per-item rows
  are consumed *repeatedly*: every slice that touches a region re-reads the same
  eleven item rules, and a rule can be revised (by a mine or a playtest) without
  any slice's content changing.

Folding them would mean a rule correction rewrites the roadmap's slice sections,
and a count recalibration rewrites the rule table. They are kept apart on
purpose. Cross-references are by section name in both directions.

## Evidence vocabulary

Per `CONTRIBUTING.md` and `docs/RESEARCH-BASELINE.md`, plus one extension this
document needs:

- **CITED** — a named EMEVD event in a named archive, quoted. The strongest class
  available without a game session.
- **INFERRED** — the corpus corroborates but does not settle it. Two common
  shapes here: a Japanese `EquipParamGoods` name that identifies an item beyond
  reasonable doubt but is not an English string, and a door whose *registration*
  is cited but whose item requirement lives in `ObjActParam`.
- **TO-MINE** — the corpus cannot answer it and a named artefact could.
- **GEOMETRIC** — the requirement is real in play but is MSB collision and
  loading-zone geometry, which no EMEVD instruction expresses. This is not a
  weaker `INFERRED`; it is a different *kind* of fact, and it is the single
  largest class in Bloodborne's world graph.

### The structural finding that shapes everything below

**Almost no region adjacency in Bloodborne is expressed in EMEVD.** Across all
27 archives there are exactly six `WarpPlayerToRespawnPoint` calls that move the
*player* between maps outside death and respawn handling:

```bash
grep -n "WarpPlayerToRespawnPoint" work/inputs/event/*.js | grep -v m29
# m22_00_00_00:1180 -> 2502959   Cainhurst carriage
# m24_00_00_00:1695 -> 3402959   DLC amygdala grab
# m28_00_00_00:1288 -> 3202959   Yahar'gul mummy      -> Lecture Building
# m28_00_00_00:1316 -> 3202958   Yahar'gul amygdala   -> Lecture Building
# m32_00_00_00:618  -> 2602959   Lecture Building     -> Nightmare of Mensis
# m32_00_00_00:626  -> 3302959   Lecture Building     -> Nightmare Frontier
```

Everything else — Central Yharnam to Cathedral Ward, Cathedral Ward to Old
Yharnam, the Forbidden Woods to Byrgenwerth — is walked. So a rule on those
edges can never be CITED; the honest ceiling is a cited *door* plus GEOMETRIC
adjacency. This document does not pretend otherwise, and it means the answer to
"can we cite this rule?" is legitimately "no" for most of `data.ENTRANCES`.
That is a fact about the game, not a gap in the mining.

## The rule vocabulary we are writing into

`worlds/bloodborne/model.py`:

```python
class Rule:
    """Disjunctive normal form: any clause may satisfy the rule."""
    any_of: tuple[frozenset[str], ...] = (frozenset(),)
    @classmethod
    def all(cls, *item_keys): ...        # one conjunctive clause
    @classmethod
    def any(cls, *clauses): ...          # several clauses, any satisfies
```

Two things follow, and both matter for the rules below.

1. **There is no negation.** A rule can say "you need X"; it cannot say "you must
   not yet have done Y". Every check-closing hazard in this document therefore
   has to be handled by placement policy or by a forward requirement, never by a
   rule clause. See *Part 3*.
2. **`Rule.any` is the only way to model an alternate route, and collapsing two
   routes into one conjunctive rule makes an item vacuous.** `data.py` already
   carries that lesson in a comment: the Hunter Chief Emblem was vacuous until
   the emblem gate and the Healing Church Workshop route were split into two
   `Entrance` hops. Every "OR" below is written as two entrances or a `Rule.any`,
   deliberately.

The reference gate is the Oedon Tomb Key, and it is worth restating because it
is the shape most of the new rules take:

```python
Entrance("Tomb of Oedon gate", "Central Yharnam", "Cathedral Ward",
         Rule.all("oedon_tomb_key", "event_gascoigne_defeated"))
```

Two requirements from two different evidence classes in one clause: the key
requirement is INFERRED (it lives in `ObjActParam` row 2410080, registered by
`m24_01_00_00` event `12410110` slot 5 — no `PlayerHasItem(Goods, 4000)` test
exists anywhere), and the Gascoigne requirement is GEOMETRIC (the door is behind
his arena). Vanilla hid the coupling by awarding the key on his death.

## Goods-id ground truth

Read out of the repo's own bundle
(`python3 tools/bb_inputs.py --get params/EquipParamGoods.csv`). The Japanese
names are the params' own; the English identifications are INFERRED from them.

| goods id | param name | identified as | class |
|---:|---|---|---|
| 4000 | 聖堂街Bの鍵 | Oedon Tomb Key | INFERRED |
| 4003 | 古城への招待状 | Cainhurst Summons | INFERRED |
| 4006 | 聖堂街C孤児院1Fの鍵 | Orphanage Key | INFERRED |
| 4010 | 聖堂街Cへの鍵 | Upper Cathedral Key | INFERRED |
| 4011 | 旧市街への鍵 | Hunter Chief Emblem | **CITED** (see below) |
| 4012 | 悪夢教室の鍵 | Lecture Building key | INFERRED |
| 4017 | 祭壇エレベーター起動アイテム | Eye Pendant (DLC) | INFERRED |
| 4308 | 古城への招待状（無記名） | Cainhurst Summons, unsigned | INFERRED |
| 4310 | 邪神投げで故郷へワープできるアイテム | **Tonsil Stone** | **CITED** |
| 4311 | 【DLC】邪神投げで聖堂街Dへワープできるアイテム | Eye of a Blood-drunk Hunter | **CITED** |

4310 and 4311 are cited rather than inferred because their param names literally
describe the mechanic ("item that warps you via the evil-god throw") and the
events that consume them perform exactly that warp.

---

# Part 1 — the eleven pooled progression items

Every one of these is already in `data.ITEMS` as `ItemKind.PROGRESSION`. What
follows is, per item: what it gates in vanilla, the evidence, and the rule
proposed for AP. Draft clauses are marked `DRAFT` and are **not wired**.

## Summary table

| item | gates in vanilla | proposed AP rule | evidence |
|---|---|---|---|
| Hunter Chief Emblem | Cathedral Ward plaza gate | unchanged (two-hop, emblem OR workshop) | **CITED** |
| Oedon Tomb Key | Tomb of Oedon door | unchanged | INFERRED + GEOMETRIC |
| Cainhurst Summons | Hemwick obelisk carriage | **+ `event_witch_of_hemwick_defeated`** | **CITED** |
| Tonsil Stone | Yahar'gul amygdala -> Lecture 1F | **source region Yahar'gul, not Cathedral Ward** | **CITED** |
| Orphanage Key | UCW interior orphanage door | unchanged | INFERRED (ObjActParam TO-MINE) |
| Upper Cathedral Key | Cathedral Ward -> UCW | unchanged | INFERRED + GEOMETRIC |
| Laurence's Skull | DLC Laurence summon only | unchanged; password stays an EVENT | TO-MINE (woods gate is ESD) |
| Eye of a Blood-drunk Hunter | Cathedral Ward amygdala -> DLC | unchanged | **CITED** |
| Eye Pendant | DLC surgery altar (goods 4017) | unchanged; **no UCW role** | INFERRED (negative result) |
| Celestial Dial | DLC astral clock | unchanged | INFERRED |
| Astral Clocktower Key | DLC clocktower door | unchanged | INFERRED |

## 1. Hunter Chief Emblem — `hunter_chief_emblem`

**Vanilla.** Opens the Cathedral Ward round-plaza gate onto the Grand Cathedral.

**Evidence: CITED.** `m24_00_00_00.emevd` event `12400760` (`円形広場の門の開閉`):

```js
itemAct  = !PlayerHasItem(ItemType.Goods, 4011) && ActionButtonInArea(2400030, 2401220);
itemAct2 =  PlayerHasItem(ItemType.Goods, 4011) && ActionButtonInArea(2400030, 2401220);
WaitFor(itemAct || itemAct2 || ObjActEventFlag(12400170));
```

The `itemAct` (no-item) branch falls through to `DisplayGenericDialog(10010173)`
and `RestartEvent()` — a refusal. The `itemAct2` branch opens the gate. The third
disjunct, `ObjActEventFlag(12400170)`, is the gate being opened **from the far
side** — the Healing Church Workshop route.

**This is a direct confirmation of the two-hop model already in `data.py`**, and
it is the only base-game progression item whose requirement is expressed as a
`PlayerHasItem` condition rather than an `ObjActParam` row. No change proposed.

## 2. Oedon Tomb Key — `oedon_tomb_key`

**Vanilla.** Door 2411304 out of the Tomb of Oedon, into Cathedral Ward.

**Evidence: INFERRED (key) + GEOMETRIC (Gascoigne).** `m24_01_00_00` event
`12410110` slot 5: `$InitializeEvent(5, 12410110, 2411304, 12411307, 1, 2410080)`
— the requirement is `ObjActParam` row 2410080. Already documented in `data.py`.
No change proposed.

## 3. Cainhurst Summons — `cainhurst_summons`

**Vanilla.** Summons the phantom carriage at the Hemwick obelisk; riding it warps
you to Castle Cainhurst.

**Evidence: CITED, and it settles the open question.** `m22_00_00_00` events
`12200130` (`馬車が登場`, "the carriage appears") and `12200131` (`馬車ワープ`):

```js
$Event(12200130, Restart, function() {
    ...
    WaitFor(PlayerHasItem(ItemType.Goods, 4003) && EventFlag(12201800) && InArea(10000, 2202410));
    ... PlayCutsceneToPlayer(22000030, ...); SetEventFlag(12204020, ON);
});
$Event(12200131, Restart, function() {
    WaitFor(EventFlag(12200130) && !CharacterDead(2201310) && ActionButtonInArea(2200010, 2201300));
    ... WarpPlayerToRespawnPoint(2502959);
});
```

**Yes — the ride requires the Hemwick boss dead.** `12201800` is the Witch of
Hemwick's boss event id, and `common.emevd` corroborates the identification
(`if (EventFlag(12201800)) { SetEventFlag(9452, ON); ... }`, the boss-mirror
block at `common:203`). The carriage does not spawn without it, and `12200131`
gates the warp on `12200130` having completed.

`data.py` currently has `Rule.all("cainhurst_summons")` on this edge. That is
incomplete.

```python
# DRAFT — slice 4. Cited: m22_00_00_00 events 12200130 / 12200131.
Entrance("Cainhurst carriage", "Hemwick Charnel Lane", "Castle Cainhurst",
         Rule.all("cainhurst_summons", "event_witch_of_hemwick_defeated")),
```

This requires a new locked event item `event_witch_of_hemwick_defeated` and a
`boss_witch_of_hemwick` location in Hemwick Charnel Lane — both are slice-4
content anyway. **Do not ship the corrected Cainhurst entrance before the Hemwick
boss location exists**, or the edge is unsatisfiable and Cainhurst becomes a dead
region with placed items in it.

There is a second, unsigned summons (goods 4308, `古城への招待状（無記名）`).
`12200130` tests only 4003. Whether 4308 also works is **TO-MINE** — it is not
tested anywhere in the corpus, which suggests it is handled in ESD or by a
`goodsUseAnim`/SpEffect path. Treat 4308 as out-of-logic until mined.

## 4. Tonsil Stone — `tonsil_stone`

**Vanilla.** Held while the Amygdala at the Yahar'gul chapel notices you; it
grabs you and drops you in the Lecture Building.

**Evidence: CITED, and the current model has the wrong source region.**
`m28_00_00_00` event `12800431` (`悪夢教室へのワープ_01_邪神投げ`):

```js
WaitFor(CharacterHasEventMessage(2800745, 10) && PlayerHasItem(ItemType.Goods, 4310));
... WarpPlayerToRespawnPoint(3202958);
```

The grabbing Amygdala is entity **2800745 — an `m28` character.** The map prefix
is unambiguous. The Cathedral Ward amygdala grab is a *different* event,
`m24_00_00_00:12405263` (`邪神投げでDLCマップへ`), it tests goods **4311**, and
it warps to `3402959` — the DLC. `data.py` already models that one correctly.

`data.py` currently has:

```python
Entrance("Amygdala's grasp", "Cathedral Ward", "Lecture Building 1F", Rule.all("tonsil_stone")),
```

The source region is wrong. It should be Yahar'gul.

```python
# DRAFT — slice 6/7. Cited: m28_00_00_00 event 12800431, character 2800745,
# warp target 3202958. The Cathedral Ward grab is 4311/DLC, not this.
Entrance("Amygdala's grasp", "Yahar'gul", "Lecture Building 1F",
         Rule.all("tonsil_stone")),
```

**This is a live defect in the shipped model, not just a roadmap item**, because
it makes `treasure_augur_of_ebrietas` (Lecture Building 1F) reachable from
Cathedral Ward with one pooled item, in a seed with no Yahar'gul in it. It is
currently harmless only because Lecture Building 1F is not in any shipped slice.
Fix it in the slice that first seeds either region, or sooner as a standalone.

**Without the Tonsil Stone**, the Lecture Building is reached by
`m28_00_00_00:12800430` (`悪夢教室へのワープ_00_なり邪後` — "after The One
Reborn"), `ActionButtonInArea(2800020, 2801500)` -> `WarpPlayerToRespawnPoint(3202959)`,
the Advent Plaza mummy. Note the two warps land on **different respawn points**
(3202958 vs 3202959) — consistent with `data.py` routing them to Lecture Building
1F and 2F respectively. Keep that split.

**Caveat, honestly stated.** Event `12800430`'s body carries *no* `EventFlag(12801800)`
test. Its comment says "after The One Reborn" and the mummy sits behind the arena,
but the requirement is GEOMETRIC, not cited. `data.py`'s
`Rule.all("event_one_reborn_defeated")` on that edge is right for play and cannot
be upgraded above GEOMETRIC by any further mining of this corpus.

## 5. Orphanage Key — `orphanage_key`

**Vanilla.** Opens the orphanage door inside the Upper Cathedral Ward.

**Evidence: INFERRED, with the door registration CITED.** `m24_02_00_00`
constructor:

```js
$InitializeEvent(0, 12420000, 2421201, 1, 2420020, 12420120);
$InitializeEvent(1, 12420000, 2421223, 1, 2420030, 12420121);
```

Two key doors in the whole map, `ObjActParam` rows 2420020 and 2420030. Object
**2421201 is also registered from `m24_00_00_00`** (`$InitializeEvent(0, 12400070,
2421201, 1, 2420020, 12420120)` — same object, same param row, registered from
the Cathedral Ward side). A door registered from both maps is a **map-boundary**
door; the one registered only from `m24_02` is interior. Combined with the goods
names — 4010 is "the key **to** Cathedral Ward C", 4006 is "the key to Cathedral
Ward C **orphanage 1F**" — the assignment is:

- 2421201 / ObjActParam 2420020 -> **Upper Cathedral Key (4010)**, the entrance;
- 2421223 / ObjActParam 2420030 -> **Orphanage Key (4006)**, interior.

The final step (ObjActParam row -> goods id) is **TO-MINE**: `ObjActParam` is not
one of the four CSVs in the bundle, though `parambnd/gameparam.parambnd.dcx` is,
so a committed reader would close it. This is the single highest-value mine in
this document — it converts *five* INFERRED key rules to CITED at once.

`data.py` already carries `Rule.all("orphanage_key")` on
`treasure_cosmic_eye_watcher_badge`. No change proposed.

## 6. Upper Cathedral Key — `upper_cathedral_key`

**Vanilla.** Opens the Cathedral Ward chapel side door into the Upper Cathedral
Ward. Its vanilla home is Yahar'gul (52800290, the mummy) — already a `data.py`
location, per SLICE-ROADMAP.

**Evidence: INFERRED (see above) + the Blood-starved Beast term is GEOMETRIC.**
`data.py`'s existing rule already carries both terms:

```python
Entrance("Upper Cathedral door", "Cathedral Ward", "Upper Cathedral Ward",
         Rule.all("upper_cathedral_key", "event_blood_starved_beast_defeated"))
```

No change proposed. But note the **vanilla-placement circularity** this creates
once both regions are seeded: the key's vanilla home is Yahar'gul, which is
behind Rom, which is behind the Forbidden Woods. With the key shuffled that is
fine; with a vanilla-placement option it self-gates. `docs/PROGRESSION-VALIDATION.md`
should grow a case for it.

### The UCW interior: Celestial Emissary, Ebrietas, and what actually gates them

**Evidence: CITED.** The two UCW bosses are `m24_02_00_00` events **12421700**
(`月からの使者` — Celestial Emissary) and **12421800** (`月の落とし子` —
Ebrietas). The lift down to Ebrietas is `12420150`/`12420151`/`12420152`
(`月の落とし子前エレベーター`), and its conditions are:

```js
WaitFor((!EventFlag(12420154) && !EventFlag(12420155) && InArea(10000, 2422651))
     || (!EventFlag(12420154) && !EventFlag(12420155) && ObjActEventFlag(12420124)));
```

`12420154`/`12420155` are the lift's own position flags. **There is no item
condition and no boss condition on the lift.** So:

- both UCW bosses are **optional** and gated only by UCW entry;
- **the Eye Pendant plays no role here.** Goods 4001 (`金のペンダント`) is
  removed by `common.emevd:408` and tested nowhere in the base game; the
  `eye_pendant` item in `data.ITEMS` maps to goods **4017**
  (`祭壇エレベーター起動アイテム`, "altar elevator activation item"), which is
  the DLC Underground Corpse Pile surgery altar — exactly where `data.py`
  already uses it. **Any proposal to give the Eye Pendant a UCW role is
  unsupported by the corpus.** Label it out-of-logic for the base game.

```python
# DRAFT — UCW mini-slice. Both bosses gated only by region entry.
# Cited: m24_02_00_00 events 12421700, 12421800; lift 12420150-12420152.
Location("boss_celestial_emissary", location_name(12421700), "Upper Cathedral Ward",
         locked_item="event_celestial_emissary_defeated"),
Location("boss_ebrietas", location_name(12421800), "Upper Cathedral Ward",
         locked_item="event_ebrietas_defeated"),
```

Both inherit `corpus_gap: implicit_write` per `docs/SLICE3-WITNESS-PASS.md`.

## 7. Laurence's Skull — `laurences_skull`, and the Forbidden Woods password

**Vanilla (base game).** The skull on the Grand Cathedral altar, examined after
Vicar Amelia, teaches the Forbidden Woods password. **Vanilla (DLC).** A separate
item that summons Laurence in the Nightmare Grand Cathedral.

**The brief asks whether the password is an item rule or an event rule. It is an
event rule, the two roles are already correctly separated in `data.py`, and they
must not be merged.**

```python
Location("interaction_laurences_skull", location_name(12401803), "Grand Cathedral",
         Rule.all("event_amelia_defeated"), locked_item="event_forbidden_woods_password"),
Location("pickup_laurences_skull", location_name(53502000), "Research Hall"),
Location("boss_laurence", location_name(13401850), "Nightmare Grand Cathedral",
         Rule.all("laurences_skull"), locked_item="event_laurence_defeated"),
```

- The **base-game skull** is a fixed *interaction* at the Grand Cathedral altar
  that yields a locked event, `event_forbidden_woods_password`. It is not
  shuffled. Its own rule is `event_amelia_defeated` — you cannot stand at the
  altar until the arena is clear (GEOMETRIC).
- The **pooled `laurences_skull`** is the DLC summoning item from the Research
  Hall. It gates a DLC boss and nothing else.

They share an English name and nothing else.

**Why the password must stay an event** — a reason specific to this engine, not a
style preference. The woods door has no `PlayerHasItem` test anywhere in the
corpus; the password is delivered through NPC dialogue, i.e. ESD, which
`plan_vanilla_suppression.py` cannot see (bb#204). An event with a cited *source
location* is honest about that. An item would claim a grant path we can neither
implement through the native grant hook nor suppress in vanilla.

**TO-MINE:** the woods gate itself. There is no `m24_00_00_00` event that opens
a Forbidden Woods door on a flag or an item. Until the ESD corpus lands,
`event_forbidden_woods_password` is an **INFERRED** requirement on the edge —
vanilla knowledge, corroborated by the absence of any competing EMEVD gate, not
settled.

## 8. Eye of a Blood-drunk Hunter — `eye_of_blood_drunk_hunter`

**Vanilla.** Held in Cathedral Ward, the amygdala grabs you into the DLC.

**Evidence: CITED.** `m24_00_00_00` event `12405263`:
`WaitFor(CharacterHasEventMessage(2400899, 710) && PlayerHasItem(ItemType.Goods, 4311)); ... WarpPlayerToRespawnPoint(3402959);`

`data.py`'s existing rule
(`Rule.all("event_forbidden_woods_password", "eye_of_blood_drunk_hunter")`) is
correct on the item term. The password term is a proxy for "the Eye's vanilla
home is a woods corpse" and is a **project choice**, not a game fact — it is not
a condition of `12405263`. Worth an explicit comment when the woods ship, so a
later contributor does not read it as evidence.

## 9-11. Eye Pendant, Celestial Dial, Astral Clocktower Key — DLC only

**Evidence: INFERRED from goods names 4017 (`祭壇エレベーター起動アイテム`),
4021 (`時計盤起動アイテム`), 4019/4020 (`時計塔の扉の鍵` / `時計塔狩人部屋（ボス部屋）の鍵`).**
All three already have correct-shaped rules in `data.ENTRANCES` and none has a
base-game role. Listed here to close the brief's list and to record the negative
result for the Eye Pendant (see UCW above). No change proposed.

---

# Part 2 — the connective tissue, region by region

## Hemwick Charnel Lane (m22)

Entry is `Grand Cathedral -> Hemwick Charnel Lane`, unruled, GEOMETRIC (the road
starts left of the cathedral entrance — already commented in `data.py`).

New content: the Witch of Hemwick, event `12201800`. Required by the Cainhurst
carriage (CITED, above), so it is progression, not a spur.

```python
# DRAFT — slice 4.
Item("event_witch_of_hemwick_defeated", "Witch of Hemwick Defeated", E),
Location("boss_witch_of_hemwick", location_name(12201800), "Hemwick Charnel Lane",
         locked_item="event_witch_of_hemwick_defeated"),
```

## Castle Cainhurst (m25)

Entry: the carriage, ruled above. Interior: `m25_00_00_00` contains exactly one
`PlayerHasItem` test in the whole archive (`Goods, 4305`, `ピンク色の肉片` — an
NPC-quest good, not a key). **No key-door registrations, no map-boundary warps.**
Martyr Logarius is therefore gated only by region entry.

```python
# DRAFT — slice 4. No interior gate found in m25_00_00_00.
Location("boss_martyr_logarius", location_name(<TO-MINE>), "Castle Cainhurst",
         locked_item="event_martyr_logarius_defeated"),
```

The Logarius boss event id is **TO-MINE** — SLICE-ROADMAP already lists Logarius
among the six bosses with an entity id but no `NpcParam` identity. Per
`CONTRIBUTING.md` rule 2, do not commit a plausible `125018xx`; read it out of
`m25_00_00_00` first.

## Forbidden Woods (m27)

Entry: the password door, INFERRED (above). Interior: three key doors,
`$InitializeEvent(n, 12700110, ...)` with `ObjActParam` rows 2700030, 2700010,
2700010 — the repeated row is the same generic shortcut-door param used across
`m24_01` (2410010), so these are shortcut doors opened from the far side rather
than item doors. **TO-MINE** with the same ObjActParam reader.

Exit to Byrgenwerth: `Rule.all("event_shadows_defeated")` — GEOMETRIC (the
Shadows' arena is the gate to the lakeside path). Already in `data.py`.

## Iosefka's Clinic — the back entrance and the three inert pickups

**Evidence: CITED, and it resolves the `docs/PLAYTESTING.md` note.** The clinic
interior is part of `m24_01` (Central Yharnam) and is reached in vanilla only
through the woods passage. The Cainhurst Summons pickup is `m24_01_00_00` event
`12410510` (`診療所に古城への招待状出現`):

```js
if (!EventFlag(12410511)) { WaitFor(InArea(10000, 2412350)); SetEventFlag(12410511, ON); }
CreateObjectfollowingSFX(2411200, 200, 900201);
WaitFor(ActionButtonInArea(2410060, 2411200));
ForceAnimationPlayback(10000, 101140, false, false, false);
AwardItemLot(2410990);
```

**There is no item condition and no boss condition** — only being inside area
2412350, the clinic. So `pickup_cainhurst_summons` (flag 52410990) is free the
moment the region is reachable, and `data.py`'s unruled
`Entrance("Forbidden Woods clinic passage", "Forbidden Woods", "Iosefka's Clinic")`
is correct as written. **The three inert pickups become live in slice 5 with no
rule change at all** — they were inert only because the Forbidden Woods were
unseeded, not because a rule was missing.

One hazard worth naming: the clinic's occupant is replaced under a world-state
transition (`m24_01_00_00:2566`, `ニセ女医_狂った`,
`WaitFor(EventFlag(9802) && !CharacterDead(2410710))`). That changes who is
standing there, not `12410510`. The pickup itself does not close.

## Byrgenwerth and the Lecture Building (m32)

Per SLICE-ROADMAP, `m32_00_00_00` is **both** Byrgenwerth and the Lecture
Building. Its two `WarpPlayerToRespawnPoint` calls are the Lecture Building
doors:

```js
$Event(13200310) { WaitFor(ObjActEventFlag(13200124)); ... WarpPlayerToRespawnPoint(2602959); }  // -> Nightmare of Mensis
$Event(13200311) { WaitFor(ObjActEventFlag(13200123)); ... WarpPlayerToRespawnPoint(3302959); }  // -> Nightmare Frontier
```

Both are `ObjActEventFlag` doors, so both may carry an `ObjActParam` item
requirement — the obvious candidate being goods 4012 (`悪夢教室の鍵`).
`data.py` currently gives **both** edges no rule:

```python
Entrance("Lecture Hall giant door", "Lecture Building 2F", "Nightmare of Mensis"),
Entrance("Lecture Building frontier door", "Lecture Building 1F", "Nightmare Frontier"),
```

**TO-MINE, and it is a real risk**, because if 13200124 needs 4012 then the
Mensis edge is under-constrained and a seed can require the goal region before
the key. Until mined, the conservative posture is to keep the edges unruled
(matching vanilla-if-the-key-is-free) but **not** to place the goal behind them
in the same slice that first seeds the Lecture Building. Note that
`treasure_lecture_theatre_key` is already a `data.py` location in Lecture
Building 2F — i.e. on the far side of the 2F door — which is itself evidence
that the 2F door is *not* the one that key opens.

Rom: `m32_00_00_00` event `13201800`. Rom's *award* is in `common.emevd` event
`9410`, gated on `EventFlag(13201803)` (`ボス撃破後花嫁出現`, the post-Rom bride
event) and `InArea(10000, 2802010)` — an **m28** area. SLICE-ROADMAP already
flags that a per-map sweep misses it; the logic consequence is that **Rom's item
award is collected in Yahar'gul, not at the arena.** If that lot is ever a check,
its region is Yahar'gul, not Byrgenwerth.

## Yahar'gul (m28) and the One Reborn chain

Entry, intended: `Rule.all("event_rom_defeated")` on the Blood Moon transition —
GEOMETRIC/world-state (see Part 3).

`m28 -> Lecture Building 2F` on the mummy: GEOMETRIC on The One Reborn (event
`12800430` carries no flag test; see Tonsil Stone, above).

`Lecture Building 2F -> Nightmare of Mensis`: the m32 door, TO-MINE, above.

**Micolash before Mergo's Wet Nurse: CITED.** `m26_00_00_00` event `12601853`
(`悪夢の主_撃破後扉制御`, "Nightmare Lord — post-defeat door control"):

```js
SetObjactState(2601251, 2600000, Disabled);
WaitFor(EventFlag(12601850));
EndIf(!EventFlag(12604879));
SetObjactState(2601251, 2600000, Enabled);
WaitFor(ObjActEventFlag(12601261));
ForceAnimationPlayback(2601852, 1, false, false, false);
```

Objact 2601251 (door 2601852) is held Disabled until Micolash's flag `12601850`
is on. `data.py`'s
`Location("boss_mergos_wet_nurse", ..., Rule.all("event_micolash_defeated"))` is
therefore **cited**, not merely inferred. That is the strongest boss-ordering
evidence in the base game and is worth recording as such.

## Where the AP goal sits, per slice

| slice | goal | why |
|---|---|---|
| 3 *(shipped)* | Blood-starved Beast | current |
| 4 (Hemwick + Cainhurst + UCW) | Blood-starved Beast, unchanged | neither new region is on the critical path; Logarius and both UCW bosses are optional |
| 5 (Forbidden Woods + Byrgenwerth) | **Rom** | first goal with an unambiguous predecessor chain |
| 6 (Yahar'gul) | **The One Reborn** | |
| 7 (Lecture + Mensis) | **Mergo's Wet Nurse** | only after the m32 door's ObjActParam is mined — otherwise the goal sits behind an unmodelled key |

Slice 4 keeping the slice-3 goal is deliberate. Advancing the goal into Cainhurst
would put it behind `cainhurst_summons` **and** the Hemwick boss, i.e. two new
requirements at once in the first slice that has either.

---

# Part 3 — check-closing world state, as a class

## What the corpus actually says

The blood moon is event flag **9802**. It is read across nine archives and **set
nowhere in any of the 27 of them** — the same failure mode as the boss flags in
`docs/SLICE3-WITNESS-PASS.md`. Its trigger is TO-MINE and probably unmineable
from EMEVD.

```bash
grep -c 9802 work/inputs/event/*.js
# m28: 57  m24_01: 23  m24_00: 16  common: 7  m21_00: 4  m22_00: 4
# m24_02: 3  m23_00: 2  m27_00: 2  — and zero in m25, m26, m32, m33, the DLC
```

Now the load-bearing result. Every `9802` site was classified by the comment on
its enclosing event:

- **World dressing** (`時間帯変化_*` time-of-day swaps, BGM, enemy despawn, SFX,
  insight-driven visuals): the large majority. No award surface.
- **NPC state transitions**: `娼婦` (Arianna), `偏屈な老人`, `少女` (the little
  girl), `孤独な老婆`, `重病人`, `復讐者` (Henryk), `ニセ女医`, `囚われた尼僧`
  (Adella), `感染者の乞食`. This is where closing lives.
- **Snatcher spawn control**: `人さらい出現` in m24_00 and m27. See Part 4.

**Not one `9802` site in the corpus gates an `AwardItemLot` on an MSB-placed
fixed treasure.** That is a checkable claim and it is the most useful thing this
section can state: *the check-closing class in the base game is coextensive with
the NPC-quest award surface* — which is exactly the ESD talk-award surface
(bb#204) that `plan_vanilla_suppression.py` cannot see and that SLICE-ROADMAP
already names as a slice-5 prerequisite.

So: **there is no evidence that any check currently in the shipping manifest, or
any check derivable from the committed catalog, closes on the blood moon.** The
hazard is real but it lives entirely in content we have not counted yet.

## Policy options

1. **Logic-forbid.** Never place progression behind a closeable check. Costs
   placement variety; needs a closes-on list we do not have; and `Rule` has no
   negation, so it would have to be an exclusion set outside the rule system.
2. **Beatable-only.** Accept that some checks can be missed; guarantee only that
   the goal stays reachable. Cheap, and Archipelago-native.
3. **Release-on-transition.** When the client observes 9802 turn on, auto-release
   every check that just became unreachable. Correct in principle. Requires the
   closes-on list *and* a live flag read, and the client would be asserting
   unreachability it cannot verify.

## Recommendation: beatable-only now, plus a named exclusion set when the ESD corpus lands

This is the choice **already made** for Gascoigne/Amelia ordering, and
consistency argues for extending it rather than inventing a second policy. The
current model does not forbid the orderings that make Central Yharnam NPC
outcomes diverge; it routes progression through the boss flags and lets quest
outcomes be quest outcomes. Nothing about the blood moon is different in kind —
it is the same class of fact, one world-state step later.

Concretely:

- **Now.** Do nothing, and say so in `docs/LOGIC-MODEL.md`. The claim is
  defensible: no manifest check is known to close, and inventing a mitigation for
  an empty set is worse than no mitigation, because it would look like coverage.
- **When bb#204's ESD corpus lands.** Every talk award admitted as a check gets a
  `closes_on: 9802` annotation if its NPC appears in the list above. Those rows
  become an **exclusion set for progression placement** — option 1, applied to
  exactly the population that needs it, which by then will be enumerated rather
  than guessed. That is a placement-policy change, not a `Rule` change, so it
  needs no negation.
- **Never.** Release-on-transition. The client would have to assert a check is
  unreachable from a flag read, and a wrong assertion permanently removes a check
  from someone else's seed. `docs/SAVE-RECONCILIATION.md`'s posture — the client
  never invents state — rules it out.

A witness obligation comes with this, per `CONTRIBUTING.md`: "no manifest check
closes on 9802" is a **universal negative**, so any test asserting it must carry
a witness that the 9802 population it examined was non-empty (nine archives,
118 read sites). A green test that read zero `9802` sites is not evidence.

---

# Part 4 — the Yahar'gul abduction path

SLICE-ROADMAP flagged this untraced. It is now traced end to end, and the verdict
holds for a different reason than the one anticipated.

## The chain, fully cited

`m24_00_00_00` event `12400780` (`人さらいでの聖堂街→生贄の街ワープ`):

```js
$Event(12400780, Restart, function(chrEntityId) {
    EndIf(!CharacterType(10000, TargetType.Alive));
    WaitFor(!CharacterDead(chrEntityId)
            && CharacterDamagedBy(10000, chrEntityId)
            && HPRatio(10000) == 0
            && EventFlag(9401)
            && EventFlag(9404));
    SetEventFlag(9420, ON);
});
```

`common.emevd`:

```js
$Event(9404) { WaitFor(EventFlag(9401) && PlayerInsightAmount() >= 1 && CharacterDead(10000)); SetPlayerRespawnPoint(2102961); }
$Event(9421) { EndIf(EventFlag(9423)); WaitFor(EventFlag(9420)); SetPlayerRespawnPoint(2802959); SetEventFlag(9420, OFF); }
$Event(9422) { EndIf(EventFlag(9423)); EndIf(!(EventFlag(9421) && PlayerInMap(28, 0))); ... SetEventFlag(9423, ON); }
```

So: be killed by a snatcher, with `9401` on (set by `m24_01_00_00`'s constructor
when `12410999` is on — early Central Yharnam progress) and `9404` on (you have
already died once with Insight >= 1). Result: the respawn point becomes **2802959**,
an m28 point. `9423` latches it to once per save.

**And what gates the snatchers themselves** — `m24_00_00_00:12400791`
(`人さらい出現`) and its m27 twin `m27_00_00_00:1270501`:

```js
if (!EventFlag(9802)) { EndIf(EventFlag(9453)); }
SetCharacterBackreadState(chrEntityId, true);
```

`9453` is the **Blood-starved Beast** mirror flag (`common:209`:
`if (EventFlag(12301800)) { SetEventFlag(9453, ON); ... }`). So the snatchers
spawn **before the Blood-starved Beast is killed**, stop spawning after, and
resume unconditionally once the blood moon is up.

## Verdict: do not model the edge — but the reason is not the one expected

**Recommended rule: none.** Record the abduction in `docs/LOGIC-MODEL.md` as a
known out-of-logic entry, bounded by event `12800403`.

The reason matters, because the naive framing ("a future-slice hazard") is wrong
on two counts.

First, **the abduction window is open in a slice-3 seed today.** A player who has
died once with Insight >= 1 and is then killed by a snatcher in Cathedral Ward —
before beating the Blood-starved Beast, which is the *current goal* — is
teleported into m28. This is live now, not a slice-6 problem.

Second, what prevents the softlock is **cited**, `m28_00_00_00` event `12800403`
(`時間帯変化_生贄の街への大扉`, "the great door to the sacrificial town"):

```js
$Event(12800403, Default, function() {
    if (EventFlag(9802)) { ReproduceObjectAnimation(2801150, 1); ...; EndEvent(); }
    SetNetworkSyncState(Disabled);
    WaitFor(ActionButtonInArea(2800001, 2801150));
    DisplayGenericDialog(10010171, PromptType.OKCANCEL, NumberofOptions.OneButton, 2801150, 3);
    RestartEvent();
});
```

**The great door out of the Hypogean Gaol into Yahar'gul proper opens only under
the blood moon.** An abducted player lands in the Gaol, not in Yahar'gul, and the
route onward is closed until the blood moon is up anyway. The abduction therefore
grants access to a *strict subset* of m28 that the intended route also grants —
it never unlocks a check the logic believes is locked behind Rom.

And it cannot strand you: `SetPlayerRespawnPoint(2802959)` is a lamp-bearing
respawn point, so the Hunter's Dream is reachable and the world graph is
re-entered from the top. There is no softlock to guard against.

**Two conditions on that verdict, stated so a later contributor can overturn it
rather than rediscover it:**

1. It holds only while **no check in the shipping manifest is Gaol-side**. Which
   `m28` catalog rows are inside the Gaol versus in Yahar'gul proper is
   **TO-MINE** (an MSB region question; `mined/msb_regions.tsv` is in the
   bundle). If slice 6 seeds a Gaol-side check, the abduction becomes a genuine
   out-of-logic *source* of items. Beatable-only absorbs that, but the claim
   above stops being true and must be re-stated rather than quietly inherited.
2. It holds only alongside the Tonsil Stone correction. With the current (wrong)
   `Cathedral Ward -> Lecture Building 1F` edge, the Tonsil Stone bypasses
   Yahar'gul entirely from the starting side of the world. With the corrected
   `Yahar'gul -> Lecture Building 1F` edge, abduction plus a shuffled Tonsil
   Stone becomes the only way the Lecture Building could be entered early — and
   it is closed *if and only if* amygdala 2800745 is not Gaol-side. **That is
   the one place where getting the Gaol boundary wrong has a logic consequence
   rather than a cosmetic one.**

---

# Part 5 — the mining backlog this document generates

Ordered by how many rules each one converts.

| # | mine | converts | artefact |
|---:|---|---|---|
| 1 | `ObjActParam` reader over the committed `parambnd/gameparam.parambnd.dcx` | 5 key rules INFERRED -> CITED (Oedon Tomb, Orphanage, Upper Cathedral, Lecture, woods shortcuts) | bundle, already committed |
| 2 | Hypogean Gaol vs Yahar'gul-proper region split | bounds the abduction verdict; gates slice 6 | `mined/msb_regions.tsv`, already committed |
| 3 | ESD talk-award corpus (bb#204) | enumerates the check-closing set | owner's machine, not in the bundle |
| 4 | Boss event ids for Logarius, Witch of Hemwick, Celestial Emissary, Ebrietas | 4 DRAFT locations become commitable | `m22`/`m24_02`/`m25` archives, already committed |
| 5 | Goods 4308 (unsigned summons) consumption path | closes a pool question | ESD or `goodsUseAnim`, TO-MINE |

Items 1, 2 and 4 need no game session and no new inputs. They are
`no-game-needed` and they are the cheapest evidence available in the project
right now.

# Evidence tally

Of the 31 discrete rule claims in this document:

| class | count |
|---|---:|
| CITED | 12 |
| INFERRED | 8 |
| GEOMETRIC | 5 |
| TO-MINE | 6 |

Three claims about the *shipped* model changed status as a result of this pass:
the Wet Nurse ordering rose from unlabelled to CITED; the Cainhurst carriage
gained a cited second requirement it did not have; and the Tonsil Stone entrance
was found to have the wrong source region.

Nothing in this document is wired. Every `DRAFT` clause is lifted into `data.py`
by the slice PR that seeds its region, and each of those PRs owns the
`docs/PROGRESSION-VALIDATION.md` case that witnesses the new rule is not vacuous.
