# Bloodborne fixture forge

Synthesizes the binary fixtures the **synthetic end-to-end chain** CI leg runs
the real tools against:

- `mapstudio/m99_00_00_00.msb` + `m99_00_00_01.msb` — two alternate map states
  with the same four invented placements (two ordinary enemies, one talk-bound
  NPC, one dummy spawn). Mined by `msbb_miner`, planned by `bb_enemizer`, and
  rewritten by `bb_enemizer_writer`.
- `param/gameparam.parambnd.dcx` + `paramdef/paramdef.paramdefbnd.dcx` — a
  synthetic one-param binder whose `ItemLotParam` rows are rebuilt from a real
  `plan_vanilla_suppression.py` plan, written by `bb_suppression_writer`.

Nothing emitted is derived from game files: every id, name, and row is
invented, so the fixtures can be produced fresh in CI without licensed content.
The forge re-reads everything it writes before exiting.

```powershell
dotnet run --project tools/bb_fixture_forge/BBFixtureForge.csproj -c Release `
  -p:SoulsFormatsNextRoot=C:\path\to\SoulsFormatsNEXT -- `
  work\fixtures --suppression-plan work\suppression-plan.json
```
