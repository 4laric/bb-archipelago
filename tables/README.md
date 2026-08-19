# Cheat Engine table support status

Only `Bloodborne-native-item-grant-auto-v2.CT` is a current player-facing
grant harness. It resolves the launch-specific eboot base and relocates its
guarded assembly template before installation. The tables with `shad-0.18` in
their names are bounded diagnostics from the emulator-update revalidation, not
parts of the normal client path.

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
