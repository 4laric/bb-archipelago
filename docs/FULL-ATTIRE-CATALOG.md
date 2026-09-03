# Full player-attire catalog

`worlds/bloodborne/attire_additions.tsv` expands the original 68-row
starting-attire corpus to all 127 distinct, obtainable player inventory rows in
game version 1.09 plus The Old Hunters. The AP armor option consumes this full
catalog; starting-attire selection deliberately keeps its smaller coherent-set
catalog.

The row IDs were reconciled against the bundled `EquipParamProtector` binder,
the datamined armor item-ID table, and the player-facing armor/storage lists.
Names that share visible text but use distinct protector rows remain distinct:

- `Hunter Garb (Cape)` (`71000`) and `Hunter Garb` (`281000`);
- the black and white `Surgical Long Gloves` (`112000`, `292000`);
- both `Student Uniform` rows (`191000`, `301000`);
- `Master's Iron Helm` (`260000`) and `One-eyed Iron Helm` (`380000`).

The previously published 68-row catalog had several display labels attached to
the right row but the wrong ensemble name. Their permanent AP keys are retained
for seed compatibility; only the display names are corrected. In particular,
protector rows `70000..73000` are the Hunter set, while `60000..63000` are the
Yharnam Hunter set.

## Explicit exclusions

- `192000` is Micolash's hidden arm equipment, not a player inventory item.
- `362000` is not a player-facing Decorative Old Hunter arm item; that ensemble
  uses the ordinary Old Hunter Gloves (`352000`).
- transformation/system, ghost, NPC-only, bloodied NPC duplicate, wandering,
  and cut rows at `480000` and above are excluded.
- Hair/face rows below `10000` and the cut base-game `330000` wolf-head record
  are not treated as attire. In the final DLC params, `330000` is the obtainable
  Butcher Mask.

Every admitted row has one literal category-1 descriptor
`1:<EquipParamProtector ID>:1`, a slot-specific receive effect, and a permanent
network ID. DLC rows are explicitly tagged so `include_dlc: false` removes all
32 Old Hunters pieces.
