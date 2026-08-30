# bb-archipelago

Bloodborne support for Archipelago: an apworld, a deterministic enemy randomizer, and the
runtime research that has to exist before either can report checks automatically.

Target: `CUSA00900` / `CUSA03173`, AppVer `01.09`, running under shadPS4.

This project does not reuse or adapt the existing Bloodborne randomizer. Its code, binaries,
extracted datasets, address tables, and patches are out of scope. See `docs/RESEARCH-BASELINE.md`
for the evidence boundary and the labelling discipline every address claim is held to.
See `CONTRIBUTING.md` for the repo-only contributor path, claiming protocol, and
the evidence and validation requirements used in review.
Player-visible changes and known release limitations are recorded in `CHANGELOG.md`.

## Layout

| Path | What |
| --- | --- |
| `worlds/bloodborne/` | The apworld. `data.py` is design, `runtime_bindings.py` is runtime IDs, and the two must not mix. |
| `bb_launcher/` | Hash-addressed seed cache, transactional shadPS4 overlay activation/recovery, vanilla bypass, and coordinated launch core. |
| `docs/` | Research baseline, logic model, progression DAG, event-flag lanes, enemizer, vertical slice. |
| `research/` | Mined and joined game data plus the catalogs the enemizer and validation run against. |
| `tools/` | Python miners and planners; `msbb_miner` and `bb_enemizer_writer` are C# over SoulsFormatsNEXT. |
| `tables/` | Cheat Engine tables, including the validated native item-grant harness. |
| `tests/` | `python -m unittest discover -s tests`. |

## Not in the repo

`Archipelago/` (pin upstream instead of vendoring), `research/mined/` (raw extractions from your
own game files — regenerate with `tools/msbb_miner` and `tools/mine_*.py`), build outputs, and
anything under `work/`, `saves/`, or the game dump itself.

The first product-launcher slice is documented in `docs/LAUNCHER.md`. Its
headless core refuses unowned mods, never mutates base/update trees, and can be
exercised with `python -m bb_launcher --help`.

The desktop surface is available with `python -m bb_launcher ui`. Its
**Randomize Enemies** option runs the deterministic planner and guarded MSBB
writer, includes the verified map outputs in the seed cache, activates the
overlay, and starts the configured shadPS4/client/bridge processes.

## Generate

```bash
python Generate.py --player_files_path Players --outputpath out --spoiler 3
```

Verified against Archipelago **0.6.7** on Python 3.11. The world writes the usual multidata plus
`*.bbenemizer.json`; both carry the same `enemizer_seed`. Feed that file to the planner:

```bash
python -m tools.bb_enemizer.cli --ap-request <request> --output work/enemizer/ap-plan.json
```

then apply it with the guarded writer as documented in `docs/ENEMIZER.md`.

For the reproducible varied-grant playtest, copy
`examples/central-yharnam-variety.yaml` into Archipelago's player directory and
generate with seed `52100005`. See `docs/HANDOFF.md` for the complete two-repo
build and live-test procedure.

## Current boundary

Generation emits the complete base-game scope plus the optional Old Hunters
route through Fishing Hamlet:
Central Yharnam, Cathedral Ward, Old Yharnam, Hemwick, Cainhurst, Forbidden
Woods, Iosefka's Clinic, Byrgenwerth, Yahar'gul, both Lecture Building floors,
Nightmare of Mensis, and Nightmare Frontier. Set `include_dlc: true` in the
player YAML to add all seven DLC regions, their progression items, bosses, and
checks; it defaults off. There are 490 base-game locations and 641 with DLC enabled.
The `goal` YAML option follows Bloodborne's three
endings: `submit_to_gehrman` completes after Mergo's Wet Nurse,
`refuse_gehrman` requires Gehrman, and the default `moon_presence` requires
Gehrman plus any three of the four shuffled Third Umbilical Cords. The fixed-pickup
manifest is regenerated from the canonical map catalog, and the two boss flags
(`12411700`, `12411800`) come from Central Yharnam EMEVD; the Blood-starved
Beast (`12301800`) and Vicar Amelia (`12401800`) flags come from the committed
`m23_00_00_00` / `m24_00_00_00` EMEVD decompiles and have not been seen fire.

The complete suppression plan rewrites the full base-game slice with zero refusals,
including Saw Spear, Torch, the Hunter Set award group, and the category-8
blood-gem pickup. Its slice-1 predecessor (54 edits) was installed and
playtested on shadPS4 0.18.0: a suppressed pickup awarded the one-Vial
placeholder, retained its acquisition flag, and remained collected after
restart. Slice 3 changed the plan digest, so that binder no longer satisfies a
current seed -- rebuild and reinstall it. Seeds require the matching
installed-binder hash witness before the native client arms.

The apworld's Python client remains a manual-check fallback. The native client
in `from-software-archipelago-clients` consumes every runtime flag binding the seed sends,
debounces true reads three times, delivers the Saw Spear and category-4 goods
through the durable r7 grant bridge, and sends Archipelago goal status for the seed's
`goal_location`. Its explicit `--assume-correct-save` MVP mode has reported
three pickups automatically and acknowledged their AP rewards in order during
a live run. This mode is operator-attested, not real save identification: never
switch characters while connected. Normal live mode remains fail closed.
