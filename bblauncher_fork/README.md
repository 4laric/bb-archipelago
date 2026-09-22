# BBLauncher-AP fork records

Upstream: `rainmakerv3/BB_Launcher` at baseline
`ca12c2fc38b8ba485e508bde815e8ea8cb49ac10`
(local sparse checkout: `work/BB_Launcher`, branch
`codex/bblauncher-service-extraction`; not vendored into this repo).

Fork (proposed): `4laric/BB_Launcher-AP`, application `BBLauncher-AP`.
This directory holds the fork-side integration surface:

- `ModService.h` / `ModService.cpp` -- generic extraction of
  activation/deactivation, active folders, overlay and backups out of
  `modules/ModManager.*`. No AP logic. Offerable upstream as-is.
  GPL-3.0-or-later, upstream notices preserved.
- `ApCoordinator.*` -- AP-specific sequencing on top of `ModService`
  (plan/journal/lock, preflight on every startup route). Not for upstream.
- `fork-update.json` -- distinct update feed example. The fork's
  `CheckUpdate` build must point here, never at upstream release
  endpoints, so an update cannot self-replace the fork with upstream.
- `LICENSE-INVENTORY.md` -- dependency/redistribution audit.

First release: Windows x64, CUSA03173 01.09 directory installs,
standard-user copy activation only. No developer bypass checkbox:
distributed builds carry the explicitly accepted set in
`bb_launcher/integrated/fork_identity.py`.
