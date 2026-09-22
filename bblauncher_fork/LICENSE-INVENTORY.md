# License / redistribution inventory (phase 0, living document)

Upstream BBLauncher headers specify **GPL-3.0-or-later** (`LICENSE` in
`rainmakerv3/BB_Launcher` at baseline `ca12c2f`). This fork preserves all
notices, identifies modifications (`bblauncher_fork/` + branch
`codex/bblauncher-service-extraction` in the separate `work/BB_Launcher`
checkout), and must distribute corresponding source + build instructions
with any binary.

Status: **audit in progress -- no public build may ship from this yet.**

| Component | License (claimed) | Redistribution terms | Verified? |
| --- | --- | --- | --- |
| Upstream BBLauncher source (fork base) | GPL-3.0-or-later | source + build instructions with binaries | headers confirmed in `work/BB_Launcher` (`ModManager.h`, `CheckUpdate.cpp`); full `LICENSE` text re-check pending |
| `bblauncher_fork/ModService.*` (extraction) | GPL-3.0-or-later (same) | same as upstream | notices preserved |
| `bblauncher_fork/ApCoordinator.h` | GPL-3.0-or-later | same as upstream | notices preserved |
| Qt (upstream dependency) | LGPL/commercial (TBD by version) | dynamic-link + license notice obligations | **NOT YET INVENTORIED** -- record exact Qt version + modules before packaging |
| Bundled AP backend/client/tools | per-repo licenses (TBD) | frozen bundle ships one coherent set | **NOT YET INVENTORIED** -- record pins + licenses before packaging |
| Assets (icons, docs) | TBD | public source availability is not redistribution permission | **NOT YET INVENTORIED** -- resolve missing grants before packaging |

Rules carried from the spec: a process boundary is an engineering
decision, not a claim that licensing obligations disappear. Keep generic
service refactors (`ModService`) separate from AP-specific changes
(`ApCoordinator`) so the former can be offered upstream. Do not imply
upstream endorsement: draft/collaborator-only branding until accepted,
independent update feed (`fork-update.json`).
