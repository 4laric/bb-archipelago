# Bloodborne Archipelago logic model

This repository now has an intentionally small, dependency-free world model in
`worlds/bloodborne`. The model now has a small Archipelago adapter and packages
as a distributable `.apworld`.

## Separation of concerns

- `data.py` owns stable project keys, player-facing names, regions, entrances,
  checks, and logical requirements.
- `runtime_bindings.py` owns Bloodborne item descriptors and event flags. Unknown
  values are explicit `None` values; they are not guessed.
- Archipelago numeric IDs will be derived from stable project keys in an adapter.
  They must not equal or encode Bloodborne runtime IDs.

The broader research scaffold still models boss and world-state transitions as
locked local event items. Those later regions are not emitted by the current
generator. In the playable slice, Cleric Beast and Father Gascoigne are ordinary
network locations backed by their defeat flags; the client reports the
Gascoigne check and then sends Archipelago goal status.

## Current vertical slice

The generated slice is Central Yharnam, Cathedral Ward and Old Yharnam, ending
at the Blood-starved Beast, plus the Grand Cathedral behind the Hunter Chief
Emblem. It contains 160 canonical, first-cycle physical pickup flags across
maps `m24_01_00_00`, `m24_00_00_00` and `m23_00_00_00`, plus six scripted
checks, for 166 network locations total. (This paragraph said 162/168 before
#220; it was already stale by one — the true count was 161/167 — so the
correction here is worth two, not one.) Observed replacement flags are
collapsed into their canonical pickup flags, and each shared-acquisition-flag
award group (Hunter Set, Top Hat, Black Church, Rumpled Yharnam, Charred Hunter
Garb) is represented by one location. The shuffled pool stays deliberately
small: the validated key items, the Saw Spear, and Blood Vial filler.

Every fixed check records its exact acquisition flag, item-lot row, item category,
item ID, and MSB or EMEVD source in `runtime_bindings.py`. The suppression planner
includes each check's vanilla award, including all four Hunter Set rows, so the
slice cannot silently produce both the original reward and the Archipelago
reward. The full post-Gascoigne model remains research scaffolding only.

## Explicit open design questions

1. How far should the pool grow beyond Central Yharnam, and which NPC
   rewards can be made non-missable?
2. Do progression key items keep their vanilla gate behavior after delivery, or
   must the client set a separate gate flag?
3. Should Vicar Amelia's password interaction be represented solely by her defeat
   event, or by a separately observed altar/skull-interaction event?
4. **Answered for the slice (2026-08-24).** Cathedral Ward's alternate routing
   is now modelled as what it is: two edges into the Grand Cathedral, one
   costing the Hunter Chief Emblem and one running through the Healing Church
   Workshop behind the Blood-starved Beast. The seeded slice contains only the
   first, so the emblem gates real checks. Whether later slices should keep
   both routes seeded — which makes the emblem optional again, exactly as in
   vanilla — is the open half.
5. Which later completion goals should become options after the Gascoigne slice?
   The first slice has one explicit goal: Father Gascoigne's defeat flag.
6. How should missable NPC quest rewards be handled so multiworld generation never
   requires an irreversibly failed check?
7. Chalice Dungeons are outside this slice and need separate option and logic
   designs. The Old Hunters is modelled behind `include_dlc` but has never been
   played live; see `docs/KNOWN-LIMITATIONS.md`.

Run `python -m unittest discover -s tests` to validate schema references and the
hard boundary between design and runtime mappings.
