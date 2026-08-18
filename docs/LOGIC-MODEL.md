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

Boss and world-state transitions are modeled as locked local event items. For
example, checking Father Gascoigne also grants `event_gascoigne_defeated`, which
makes Cathedral Ward reachable in logic. Such event items are never shuffled and
do not imply that the client grants a physical game item.

## Current vertical slice

The first slice describes the critical path from Central Yharnam through Mergo's
Wet Nurse plus four optional destinations. It includes only ten candidate checks:
seven bosses and three key-item pickups. This small set is meant to give event-flag
research exact targets while avoiding unsupported claims about hundreds of loose
pickups.

## Explicit open design questions

1. Which checks are in the first playable pool: bosses only, key items, fixed
   treasures, NPC rewards, or all of those?
2. Do progression key items keep their vanilla gate behavior after delivery, or
   must the client set a separate gate flag?
3. Should Vicar Amelia's password interaction be represented solely by her defeat
   event, or by a separately observed altar/skull-interaction event?
4. Cathedral Ward has alternate routing through Old Yharnam. Until that region and
   its exact gates are modeled, the prototype conservatively requires the Hunter
   Chief Emblem for the Grand Cathedral route.
5. What is the completion goal: Wet Nurse, one of the three endings, all bosses,
   or an option? The current model exposes the Wet Nurse event but declares no
   Archipelago completion condition.
6. How should missable NPC quest rewards be handled so multiworld generation never
   requires an irreversibly failed check?
7. Chalice Dungeons and DLC are outside this initial slice and need separate option
   and logic designs.

Run `python -m unittest discover -s tests` to validate schema references and the
hard boundary between design and runtime mappings.
