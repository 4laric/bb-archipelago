# Bloodborne MSBB miner

This offline research tool reads decompressed Bloodborne `.msb` files and emits
physical-provenance TSVs for treasures, enemies, and entity-bearing regions. It
does not assign Archipelago regions or infer acquisition flags.

It requires a checkout of `soulsmods/SoulsFormatsNEXT` and intentionally keeps
that GPL-3.0 dependency out of the shipped Archipelago runtime. The first
validated run used commit `ee1dd619`.

```powershell
dotnet run --project tools/msbb_miner/MSBBMiner.csproj -c Release `
  -p:SoulsFormatsNextRoot=C:\path\to\SoulsFormatsNEXT -- `
  C:\path\to\mapstudio C:\path\to\research\mined
```

Outputs:

- `msb_treasures.tsv`: treasure events, all three item-lot fields, linked part,
  coordinates, event identifiers, and fixed-map/Chalice-template scope.
- `msb_enemies.tsv`: enemy and dummy-enemy placements with NPC, think, talk,
  character-init, collision, entity, and coordinate fields.
- `msb_regions.tsv`: entity-bearing regions and coordinates.
- `msb_failures.tsv`: one row per unreadable map; a header-only file means the
  corpus parsed without failures.

The next joins are deliberately separate: treasure lots to Bloodborne
`ItemLotParam`, enemies to `NPCParam` drop lots, and EMEVD awards/enablers to map
event identifiers.
