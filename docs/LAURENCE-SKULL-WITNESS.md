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

The transform fails closed on a source hash or event-shape mismatch and emits
an ownership manifest. It deliberately produces source, not a pretend game
artifact: activation still requires the managed-overlay EMEVD compiler/install
lane, binary diff verification, and the live acceptance sequence in issue #277.

This patch shares `m24_00_00_00` with the Hunter Chief Emblem patch. The binary
builder must compose both source transforms before compiling and must verify
both target events while proving unrelated events unchanged.
