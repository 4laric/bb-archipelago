# Bloodborne pickup names

Normal launches now name every mapped physical pickup with its actual seeded
item and recipient, including filler. The clone is a pickup-name placeholder;
Archipelago still delivers the actual item through the existing client.
Boss/event-only checks without an ItemLot binding and received-item popups are
separate features (see NATIVE-ITEM-POPUPS.md).

## Live observation and release decision

On 2026-09-21, the user confirmed the physical popup worked with **Bold Hunter's
Mark x2**, after a 629-pickup build was installed for CUSA03173 AppVer 01.09 on
shadPS4 0.18.0. The game file-open log showed `msg/enggb/item.msgbnd.dcx`; the
initial engus-only overlay could not affect that archive. Both installed English
archives are now patched automatically, without changing emulator settings.

This is an **observed pickup-name rendering result**. Separate storage, shop,
and reload outcomes were not reported and are not claimed as validated. The
user explicitly authorized normal activation and release on this observation,
with no further gameplay requests. Further regressions should be investigated
from logs and offline reproduction before spending additional player time.

## Seed and archive contract

- Goods IDs `900000..900999` come from the reserved, empty range in the bundled
  EquipParamGoods census. New seeds allocate deterministically by location ID.
- All physical checks with mapped lots are named, including filler. Normal
  generation emits an enabled plan. Older inert plans are enabled at launch
  without changing their goods IDs; older plans only name the placements they
  contain. A new seed is needed for full filler coverage in those older plans.
- Names use `Item name (recipient)` within 48 UTF-16 code units.
- The goods clone retains Blood Vial 1000's stackable acquisition shape. The
  writer refuses a modal-dialog ID, unique-item flag, occupied ID range, or lot
  without exactly one Blood Vial placeholder slot.
- Parameters are composed first, names next, optional enemy scaling last.
  Each language starts from the same input parameters and must produce the same
  parameter hash. All outputs activate together in the owned overlay.
- Text, source archives, paramdefs, and selected playtest scope participate in
  cache identity. Cache verification, ownership, and Doctor hash the archives.
  The client receives the final composed parameter hash, including on reconnect.
- Base and update game files are read-only. Languages other than English are
  outside the currently supported naming path.

## Optional focused debugging

Ordinary play needs no canary command. For a focused reproduction only:

```powershell
python -m bb_launcher pickup-name-canary --settings path/to/launcher-settings.json --all
python -m bb_launcher pickup-name-canary --settings path/to/launcher-settings.json --list
python -m bb_launcher pickup-name-canary --settings path/to/launcher-settings.json --location LOCATION_KEY --language enggb
```

`--all` allows the tester to follow any route. `--location` and `--language`
restrict a reproduction when that restriction answers a specific question.
The playtest writer mode keeps its plan inert and does not manufacture a passing
verdict. Both writer modes require `--apply` and verify reopened outputs.
