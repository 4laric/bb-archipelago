# Experimental chalice boss donors

Eight new boss families have direct encounter adapters. Bloodletting has two
separate variants, giving nine explicit donor choices. The public experimental
registry permits **52 directed routes across 10 arenas**. These routes support
the experimental `good` pool: all 22 main/DLC arenas receive the 22 requested
families exactly once, with no self-pairs or repeated families. The normal
reviewed pool remains separate. Selection uses a deterministic matching of
registered routes and fails explicitly if a complete assignment is impossible.

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

Every route replaces the destination's pinned map states and retains its
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

To build the complete roster, replace `--arena ... --donor ...` with
`--pool good`. One normal or headless Bloodletting variant is selected per seed.
Paarl currently supplies the Darkbeast family; Loran Darkbeast has no adapter
and is explicitly reported unavailable.

## Asset delivery and known limits

Chalice effects live in `m29a`, `m29b`, and `m29c`, not the empty `m29` bank.
The adapters merge the complete required source banks into the selected destination
subarea bank, retaining existing destination entries. Conflicting bytes fail
the build. Multiple source banks can supply distinct roots for the same actor;
duplicate root declarations across banks are rejected. Native receipts check
the typed animation witnesses and the final delivered root bytes.

This proves direct-root delivery, not recursive FXR dependencies or runtime
precedence over shared map banks. Global-bank roots and unresolved typed
roots are recorded separately in `boss_contract.chalice_character_effect_limits`.
They must not be described as complete effect closure.

The selected chalice NPC rows have no source tier understood by the current
scaler. Builds explicitly report a scaling skip and retain the source stats.
Chalice depth effects and arena balance therefore still need work. Tests do
not establish that a fight fits its destination or that all attacks/phases work in
the emulator.

## Validation and next steps

Development validation includes Python adapter/integration tests, the native
writer suite, original-file builds of all nine variants at Cleric, individual
expanded Maria/Gehrman/Ebrietas/Rom builds, and two complete 22-family native builds covering normal and headless Bloodletting.
The builds verify 68 and 67 output files and resolve all missing AI scripts.
See [full-roster native evidence](good-boss-native-smoke.json) for the exact seed,
assignment, and event hashes. Assignment tests cover both Bloodletting variants
across multiple seeds. The receipt always reports `runtime_validated: false`.

The remaining validation is in-game: entry, AI, health bars, phases/limbs, death,
fog removal, lamps, save/reload, and effects. Chalice scaling and Loran's adapter
remain follow-up work. This is an experimental pool, not gameplay certification.

See [Giant and Bloodletting source evidence](CHALICE-GIANT-BLOODLETTING-EVIDENCE.md)
for the distinction between the two Bloodletting actors and their controllers.
