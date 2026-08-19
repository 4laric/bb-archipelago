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
| `docs/` | Research baseline, logic model, progression DAG, event-flag lanes, enemizer, vertical slice. |
| `research/` | Mined and joined game data plus the catalogs the enemizer and validation run against. |
| `tools/` | Python miners and planners; `msbb_miner` and `bb_enemizer_writer` are C# over SoulsFormatsNEXT. |
| `tables/` | Cheat Engine tables, including the validated native item-grant harness. |
| `tests/` | `python -m unittest discover -s tests`. |

## Not in the repo

`Archipelago/` (pin upstream instead of vendoring), `research/mined/` (raw extractions from your
own game files — regenerate with `tools/msbb_miner` and `tools/mine_*.py`), build outputs, and
anything under `work/`, `saves/`, or the game dump itself.

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

## Current boundary

Checks are reported **manually** with `/check <exact location name>` in the client. Fifteen fixed
location acquisition flags are mapped statically, but no live flag-manager accessor has been
validated, so nothing is automatic yet. `docs/EVENT-FLAG-RESEARCH.md` Lane B is the path out.

Item delivery is real: the client queues received items into the Cheat Engine harness one at a
time and advances a durable receipt only after the harness confirms completion. Absent-item
insertion and save persistence across a full emulator restart are both validated.
