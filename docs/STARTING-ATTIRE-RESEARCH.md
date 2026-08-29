# Starting attire research

Issue: bb-archipelago#234.

## Corpus finding

The bundled `gameparam.parambnd.dcx` and matching Paramdef contain a direct
starting-attire surface. `CharaInitParam` rows 2000 through 2009 are the ten
real origin rows (their internal names say “initial character” plus the origin
name). Every row carries the same four exact fields and values:

| field | protector id | evidenced slot |
|---|---:|---|
| `equip_Helm` | 230000 | head |
| `equip_Armer` | 231000 | body |
| `equip_Gaunt` | 232000 | arms |
| `equip_Leg` | 233000 | legs |

`EquipParamProtector` identifies those four rows as the initial-equipment head,
body, arms, and legs respectively. Its literal slot flags agree: `headEquip`,
`bodyEquip`, `armEquip`, and `legEquip` each select exactly the corresponding
row.

Rows 3000 through 3009 are a parallel character-creation-screen block. They use
the same body, arms, and legs, while `equip_Helm` is `-1`. This means an
implementation must decide deliberately whether to change only the final
character rows or also make the creation preview reflect the seed choice.

The read-only command below reproduces this finding from the bundle rather than
depending on this document's transcription:

```powershell
dotnet run --project tools/bb_suppression_writer/BBSuppressionWriter.csproj -- `
  --inspect-starting-attire gameparam.parambnd.dcx paramdef.paramdefbnd.dcx
```

## What this proves

- Bloodborne has explicit initial-attire parameter fields for every origin.
- A seed-owned GameParam implementation can cover every origin without live
  equip-slot writes.
- The selected values are `EquipParamProtector` row ids, so choices can be
  validated against the protector table and its body-slot flags.

## What still needs a witness

The corpus does not prove when the game consumes these rows. Before exposing a
YAML option, build one canary binder that changes all ten 2000-series rows to a
reviewed four-piece set, then create a fresh character and verify:

1. the four pieces are present and equipped after character creation;
2. they survive the first wake-up, death, Dream warp, save/reload, and launcher
   restart;
3. an already-created character is unchanged;
4. changing the 3000-series preview rows is cosmetic only and does not create
   duplicate inventory instances.

Only after that witness should the implementation add deterministic seed
choices and the `randomize_starting_attire` option.
