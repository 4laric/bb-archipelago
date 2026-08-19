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

The generated slice is Central Yharnam through Father Gascoigne. It contains all
51 canonical, first-cycle physical pickup flags in map `m24_01_00_00`, plus the
Cleric Beast and Father Gascoigne defeat checks, for 53 network locations total.
The two observed replacement flags are collapsed into their canonical pickup
flags, and the four-row Hunter Set award group is represented by one location.
The shuffled pool is intentionally minimal for this first end-to-end slice: one
Saw Spear and Blood Vial filler.

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
4. Cathedral Ward has alternate routing through Old Yharnam. Until that region and
   its exact gates are modeled, the prototype conservatively requires the Hunter
   Chief Emblem for the Grand Cathedral route.
5. Which later completion goals should become options after the Gascoigne slice?
   The first slice has one explicit goal: Father Gascoigne's defeat flag.
6. How should missable NPC quest rewards be handled so multiworld generation never
   requires an irreversibly failed check?
7. Chalice Dungeons and DLC are outside this initial slice and need separate option
   and logic designs.

Run `python -m unittest discover -s tests` to validate schema references and the
hard boundary between design and runtime mappings.
