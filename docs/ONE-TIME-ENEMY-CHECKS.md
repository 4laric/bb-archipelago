# One-time hunter and unique-enemy checks

`one_time_enemy_checks` is an opt-in YAML toggle. It adds combat checks only
when the encounter has a unique, durable, save-backed completion witness.
Ordinary respawning enemies and item-acquisition flags are never sufficient.

## Initial census

| Encounter | Map/entity | Witness | Classification | Reason |
|---|---|---|---|---|
| Yurie, the Last Scholar | `m32_00_00_00`, `3200110` | event-slot flag `13200500` | safe standalone check | MSB places `c0000_0002` with NpcParam `6450`; that row has `disableRespawn=1`. Dedicated EMEVD event `13200500` waits for `CharacterDead(3200110)`, and its completed event-slot flag survives reload. The witness is independent of Yurie’s drop lot. |
| Byrgenwerth Patches | `m32_00_00_00`, `3200101` | quest state `1431` on death | excluded: quest NPC | Patches can remain friendly and alive. A kill-only check would make a hostile quest outcome mandatory; no equivalent peaceful-resolution witness is established. |
| Master Willem | `m32_00_00_00`, `3200100` | quest state `1061` on death | excluded: non-hostile NPC | Not a hostile encounter; killing him must not become progression. |
| Djura | `m23_00_00_00` | badge acquisition flag `50001700` | excluded from this category | Friendship and death already converge on the existing Powder Keg Hunter Badge award check. Adding a second kill check would punish the peaceful route. |
| Eileen / Bloody Crow / Henryk | quest-dependent | multiple quest flags | needs event patch/design | Outcomes share a branching quest. No single reviewed witness currently proves a quest-friendly completion for each proposed encounter. |
| Yahar’gul hunter trio | Yahar’gul | not established | needs event patch | Completion must mean all three hunters are dead. No reviewed durable composite witness is committed yet. |
| Nightmare Frontier hunters | Nightmare Frontier | not established | needs evidence | Non-respawn behavior alone is insufficient; entity identities and unique durable flags still need a map/event join. |
| DLC NPC hunters | Old Hunters maps | quest-dependent or not established | needs evidence | DLC gating, alternate outcomes, and unique witnesses require a separate reviewed tranche. |

## Runtime and migration behavior

The client polls `13200500` like every other runtime location flag. AP’s
checked-location set provides exactly-once network behavior. Because the
witness is persistent, an existing save on which Yurie is already defeated
reconciles the check when the client next reads the flag; no item-drop state is
consulted. The option defaults off, preserving the prior location count.

Live acceptance still requires killing Yurie through normal play, an
environmental/friendly source where practical, then reloading and revisiting
to confirm that the flag remains on and the check is not resent.
