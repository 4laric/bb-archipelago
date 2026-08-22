# Cheat Engine table support status

Only `Bloodborne-native-item-grant-auto-v2.CT` is a current player-facing
grant harness. It resolves the launch-specific eboot base and relocates its
guarded assembly template before installation. The tables with `shad-0.18` in
their names are bounded diagnostics from the emulator-update revalidation, not
parts of the normal client path.

The current harness uses portable temporary/AppData paths, respects the process
already attached in Cheat Engine, validates any eboot base read from the shad
log, and falls back to a live signature scan. It visibly reports setup and
bootstrap outcomes. Re-executing it in the same process is ignored as
`already_ready`; restart Cheat Engine before loading a replacement table after
hooks have already been installed.

`SAFE-READ-ONLY-portable-inventory-geometry.CT` is the supported cross-machine
inventory diagnostic. Run it only after the player-facing harness has installed
in the same process. It writes `%TEMP%\bb-inventory-geometry.txt`, scans only a
bounded active/probe window, and distinguishes canonical Vial/Bullet runtime
IDs from low-ID collisions in equipment-shaped records.

Absent-stack Blood Vial insertion is deliberately refused. Cross-machine
testing returned a native slot while creating invalid raw descriptor
`0xF00003E8` (`?ItemInfo?`) rather than the expected `0xB00003E8`. Existing Vial
stack increments and the previously validated absent Pebble path are distinct
code paths and remain supported. See issue #70.

`legacy-v017.tsv` is the reviewed inventory of fixed-address tables that must
not be loaded on current shadPS4. `archive` means the file remains useful as
reverse-engineering evidence; `retire` means it was a duplicate or one-shot
cleanup artifact. Neither disposition means “supported.” The successor column
points to the current implementation where one exists.

Run `python tools/audit_ce_tables.py --check` after adding or changing a table.
The audit fails when a tracked table contains an unresolved v0.17 absolute but
is absent from the inventory, or when the current grant table loses its
launch-relative relocation guard. This intentionally ignores untracked local
playtest tables.
