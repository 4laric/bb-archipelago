# Experimental boss encounter adapter

`bsb-at-cleric-v1` builds Blood-starved Beast into Cleric Beast's encounter
from CUSA03173 AppVer 01.09 original inputs. It is an offline construction
canary, not a runtime-validated boss randomization option.

The combined writer updates all three original map states, clones the donor
NPC with the experimental destination normalization effect, imports its
missing map-local AI, and merges nine reviewed encounter events. The original
Cleric defeat event 12411700, constructor, fog/entry guards, rewards and AP
progression event instructions remain unchanged. NPC reward fields inherit
the donor, as in the existing scaling writer; destination event awards remain.

The adapter replaces Cleric's leap with BSB animation 7001 at the original
placed coordinates, removes the leap warp/gravity setup, changes the health
bar label, uses the normal camera, disables Cleric-specific limb/cloth events,
and transplants BSB's native 67% and 33% HP phase scripts. Destination-owned
events 12414707/12414708 hold the phase state; no new flags are allocated.
Original BSB defeat/progression flags are not transplanted.

Source event bodies and compiled replacement instructions are hash-pinned.
The compiler's whole-file output is never installed: only the nine pinned
events are merged into the original file. Every other event fingerprint,
event order, link offsets and string data must survive serialization unchanged.
Ordinary map/scaling writer entry points reject boss-marked plans, so they
cannot emit an apparently complete boss build without its event adapter.

## Building

Build `tools/bb_enemizer_writer` against the pinned SoulsFormatsNEXT release
used by the regular enemizer. Supply DarkScript 3.6.3 (the builder checks its
executable hash), the managed writer DLL and SDK, original effective maps and
scripts, original paramdefs, and the already-built AP suppression gameparam.
The event directory must contain original `m24_01_00_00.emevd.dcx` (patch),
`m23_00_00_00.emevd.dcx` (base), and `common.emevd.dcx` (patch).

```powershell
python tools/build_boss_canary.py --darkscript <DarkScript3.exe> `
  --writer <BBEnemizerWriter.dll> --dotnet <dotnet.exe> `
  --gameparam <built-gameparam.parambnd.dcx> --paramdef <paramdef.paramdefbnd.dcx> `
  --maps <original-MapStudio-directory> --scripts <original-script-directory> `
  --events <original-event-directory> --output <new-overlay-directory> --apply
```

Output must be new and outside input directories. The writer stages all
components before publishing the overlay directory. Receipts include
`boss-adapter-report.json`, the source and adjusted plans, AI provenance, and
scaling verification. The tool does not install the overlay or launch the game.

## Live evidence still required

Use a backed-up test character with Cleric undefeated. Check first entry,
fog re-entry after death, save/reload, attacks and pursuit, both poison phase
transitions, health bar and music, bridge collision/arena containment, defeat,
lamp unlock, destination rewards and exactly one Cleric AP check. Existing
destination phase flags on a previously played save may affect this experiment.
Co-op and NG+ scaling also remain unvalidated. Record failures with the overlay
receipts and the bad-enemy report. Do not promote this adapter into the normal
boss pool based only on successful construction.

## Remaining roster

`python tools/build_boss_catalog.py --check` verifies the generated original
encounter census in `research/enemizer/boss_catalog.json`. It matches all 22 AP
boss bindings, with 12 single referenced actor encounters and 10 involving
multiple actors or proxies. It records literal actor references, initializer
arguments, health bars, terminal predicates, cutscene/animation calls and
unresolved references. This is conservative evidence, not full control-flow
analysis or an approval list. Witches require both actors dead; Mergo's defeat
actor is a proxy without a fixed-map placement. Those contracts need dedicated
adapters before wider boss randomization.
