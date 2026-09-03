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

The transform fails closed on a source hash or event-shape mismatch.

The launcher applies the same two edits directly to the licensed
`m24_00_00_00.emevd.dcx` with `tools/bb_event_writer` (bundled as
`BBEventWriter.exe`), instruction by instruction, and refuses the result
unless every unrelated event is byte-identical to the source. The source
transform above remains the reviewed specification, and
`tools/build_cathedral_emevd.py` still compiles it with DarkScript 3.6.3 as
the development oracle the writer's owned events are checked against. See
`docs/EVENT-WRITER.md`. Live acceptance remains the four-step sequence in
issue #277.
