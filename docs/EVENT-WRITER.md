# Event overlay writer

`tools/bb_event_writer` (bundled as `tools/BBEventWriter.exe`) writes the two
Archipelago event overlays directly into the player's licensed EMEVD files
with SoulsFormatsNEXT. It replaced the DarkScript3 compile step on
2026-09-03 so that players no longer install a script compiler and the .NET 6
runtime it needed.

## What it writes

| overlay | file | edits |
| --- | --- | --- |
| Cathedral | `dvdroot_ps4/event/m24_00_00_00.emevd.dcx` | event `12401803`: guard `EndIf(ThisEvent())` becomes `EndIf(EventFlag(12401898))`; tail gains `SetEventFlag(12401898, ON); RestartEvent();`. Event `12400760`: the `ObjActEventFlag(12400170)` disjunct and its OR-group compile are removed. |
| Common | `dvdroot_ps4/event/common.emevd.dcx` | event `0` gains one `InitializeEvent(slot, 98000000, token, lot, ackFlag)` per reviewed category-8 row at the top of the constructor; event `98000000` (Restart) is appended with the token-consume / `AwardItemLot` body and five parameter records. |

The reviewed specifications remain the source transforms in
`tools/patch_laurence_skull.py`, `tools/patch_emblem_chokepoint.py`, and
`tools/patch_category8_awards.py`. The writer is an instruction-level
rendering of those three; it adds no behaviour.

## How it avoids an instruction table

DarkScript3's Bloodborne EMEDF is all-rights-reserved, so the writer does not
vendor it. Instead every new instruction is cloned from a vanilla instruction
of the same bank and id, with the same argument length and no layer mask,
found in the same licensed file. The clone proves the game exercises the
instruction and fixes its argument layout. If a required shape is absent the
writer refuses, which is the correct outcome for an unsupported build.

Argument encodings were taken from a DarkScript3 3.6.3 compile of the source
transforms, read back with `BBEventWriter dump`, and are asserted against the
vanilla instruction they replace before any write (`Expect` in the source).

## Verification

The writer checks, before writing, that every event it does not own has an
identical instruction and parameter fingerprint to the source, and that the
owned events changed only as specified.

The verification record for `CUSA03173` 01.09 (2026-09-03, owner's files):

- A plain SoulsFormatsNEXT read and write of both vanilla files reproduces
  the decompressed EMEVD byte for byte (0 differing bytes). Only the DCX
  container bytes differ, as with any recompression.
- Owned events `98000000`, `12401803`, and `12400760`, and the 58 new
  initializers in common event `0`, are instruction- and parameter-identical
  to the DarkScript3 3.6.3 compile of the same transforms.
- The DarkScript3 compile itself is **not** faithful to vanilla: its
  decompile-and-recompile re-encoded 23 of 83 events in `common` and 112 of
  246 events in `m24_00_00_00` that nothing had edited, renumbering condition
  registers, flipping condition polarity encodings, and in fourteen events
  changing the instruction count. The previous builder's "unrelated events
  round-trip" check compared decompiled *source*, which normalised those
  differences away. The writer's output carries none of them.

The DarkScript3 path is kept as a development oracle:
`tools/build_cathedral_emevd.py` and `tools/build_common_emevd.py` compile the
source transforms with a pinned compiler and are the reference the writer's
owned events are diffed against when a transform changes. They are not used
by the launcher.

## Commands

```
BBEventWriter dump <emevd.dcx> [eventId ...]
BBEventWriter decompress <in.emevd.dcx> <out.emevd>
BBEventWriter cathedral --source <m24_00_00_00.emevd.dcx> --output <path> --manifest <path>
BBEventWriter common --source <common.emevd.dcx> --request <rows.json> --output <path> --manifest <path>
```

`rows.json` carries `category8_awards` as either a list (what the launcher
writes from the full reviewed table) or the seed's dictionary keyed by AP
item id. The writer refuses to overwrite an existing output or manifest.

## Re-verifying after a transform change

1. Compile the changed transform with the oracle:
   `python tools/build_common_emevd.py` or `build_cathedral_emevd.py` with a
   DarkScript3 3.6.3 executable.
2. Update the writer's instruction bytes to match, run it on the same source.
3. `BBEventWriter dump` both outputs and compare the owned events only; the
   rest are expected to differ because the oracle re-encodes them.
4. Record the result here with the date and image.
