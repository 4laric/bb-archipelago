# Experimental chalice boss donors

Eight new boss families have direct encounter adapters. Bloodletting has two
separate variants, giving nine explicit donor choices. The public experimental
registry currently permits **Cleric Beast's arena only**. These adapters are not
added to the normal reviewed shuffle or presented as a completed good-boss mode.

| Family | CLI donor | Combat carried over |
| --- | --- | --- |
| Pthumerian Descendant | `pthumerian-descendant` | Original NPC/AI, wake animation, phase message |
| Pthumerian Elder | `pthumerian-elder` | Distinct original NPC/AI, wake animation, phase message |
| Keeper of the Old Lords | `keeper-of-old-lords` | Original NPC/AI; destination entry replaces dungeon spawn |
| Abhorrent Beast | `abhorrent-beast` | Original NPC/AI and five limb controllers |
| Beast-Possessed Soul | `beast-possessed-soul` | Exact boss NPC/AI, including MSB ThinkParam `750090` |
| Watchdog of the Old Lords | `watchdog-of-the-old-lords` | Original NPC/AI and five limb controllers |
| Undead Giant | `undead-giant` | Original NPC/AI; selected source variant `10313090 / 313090` |
| Bloodletting Beast | `bloodletting-beast` | Normal variant's limbs, recovery masks, roar, and cloth controllers |
| Bloodletting Beast | `headless-bloodletting-beast` | Separate original NPC/AI; does not inherit another actor's limb scripts |

Every route replaces all three Cleric map states and retains the destination's
fog, victory, rewards, lamp progression, and co-op lifecycle. Imported combat
event IDs are checked against the original event corpus. Source map constructors,
actor fingerprints, initialization fields, animation binders, and effect banks
are pinned. The game installation is read only during a build.

## Build a test encounter

Use the existing pinned DarkScript compiler and the native writer built from
this branch. `GAME` below is an original `dvdroot_ps4` directory; use an empty
output directory. Nothing is installed or launched by this command.

```powershell
python -m tools.build_boss_encounters `
  --darkscript PATH_TO_DARKSCRIPT3_EXE --writer PATH_TO_BBENEMIZERWRITER_EXE `
  --gameparam "$GAME/param/gameparam/gameparam.parambnd.dcx" `
  --paramdef "$GAME/paramdef/paramdef.paramdefbnd.dcx" `
  --maps "$GAME/map/mapstudio" --scripts "$GAME/script" `
  --events "$GAME/event" --sfx "$GAME/sfx" --characters "$GAME/chr" `
  --arena cleric-beast --donor pthumerian-elder --seed chalice-canary `
  --output work/chalice/elder --apply
```

For a DLL writer, also provide `--dotnet dotnet`. Per-map m29 files are resolved
inside their original group directory, for example
`m29_05_00_00/m29_05_00_11.msb.dcx`. The source constructor manifest also checks
the nested EMEVD before work begins.

## Asset delivery and known limits

Chalice effects live in `m29a`, `m29b`, and `m29c`, not the empty `m29` bank.
The adapters merge the complete required source banks into Cleric's `m24_01`
subarea bank, retaining existing destination entries. Conflicting bytes fail
the build. Multiple source banks can supply distinct roots for the same actor;
duplicate root declarations across banks are rejected. Native receipts check
the typed animation witnesses and the final delivered root bytes.

This proves direct-root delivery, not recursive FXR dependencies or runtime
precedence over the shared `m24` bank. Global-bank roots and unresolved typed
roots are recorded separately in `boss_contract.chalice_character_effect_limits`.
They must not be described as complete effect closure.

The selected chalice NPC rows have no source tier understood by the current
scaler. Builds explicitly report a scaling skip and retain the source stats.
Chalice depth effects and arena balance therefore still need work. Tests do
not establish that a fight fits the bridge or that all attacks/phases work in
the emulator.

## Validation and next steps

Development validation includes Python adapter/integration tests, the native
writer suite, and original-file builds of all nine variants at Cleric. The
receipt always reports `runtime_validated: false`. No gameplay validation has
been performed for these routes.

Before enabling the complete good-boss preset:

1. Playtest entry, AI, health bar, each phase/limb response, death, fog removal,
   lamp, save/reload, and effects for these donor packages.
2. Add reviewed scaling for chalice source stats and depth effects.
3. Expand destination entry/arena and effect-bank proofs beyond Cleric.
4. Complete the 22-family assignment policy: each family once, one chosen
   Bloodletting variant and one chosen Paarl/Loran variant, with no repeats.
   Loran Darkbeast remains separate work from these eight missing families.

See [Giant and Bloodletting source evidence](CHALICE-GIANT-BLOODLETTING-EVIDENCE.md)
for the distinction between the two Bloodletting actors and their controllers.
