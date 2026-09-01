# Laurence's Skull witness patch

The Grand Cathedral altar interaction is event `12401803`. Vanilla marks that
event complete after its cutscene, which also makes flag `12401803` true. That
flag is now owned by the shuffled `"Fear the old blood"` item, so it cannot also
serve as the altar location witness.

`tools/patch_laurence_skull.py` pins the supported `m24_00_00_00` DarkScript
source and makes two narrow changes inside event `12401803`:

- completion is guarded by AP-only witness flag `12401898`, rather than
  `ThisEvent()` / password flag `12401803`;
- after the interaction and cutscene, it sets `12401898` and restarts the event
  so the vanilla event-completion flag is never awarded.

The transform fails closed on a source hash or event-shape mismatch. The
activation builder, `tools/build_cathedral_emevd.py`, decompiles a user-owned
`m24_00_00_00.emevd.dcx` with pinned DarkScript 3.6.3, composes both owned
source transforms, compiles it, decompiles the result again, and refuses the
artifact unless both target events and every unrelated event round-trip.
The emitted manifest owns `dvdroot_ps4/event/m24_00_00_00.emevd.dcx` and pins
the compiler, source, and output hashes. The licensed input and compiled output
remain local and are never committed.

Example (PowerShell):

```powershell
python tools/build_cathedral_emevd.py --darkscript C:\tools\DarkScript3.exe `
  --source C:\game\event\m24_00_00_00.emevd.dcx `
  --output work\cathedral-emevd\dvdroot_ps4\event\m24_00_00_00.emevd.dcx `
  --manifest work\cathedral-emevd\build-manifest.json --apply
```

Copy the emitted `dvdroot_ps4` tree into the launcher's user-files directory;
the launcher merges it into the same managed overlay as suppression and
enemizer output. Live acceptance remains the four-step sequence in issue #277.
