# BBLauncher AP fork: license and source inventory

This records the evidence bundled with a Windows package. It is a living
inventory, not a legal conclusion about every dependency or asset.

| Component | Evidence in the package | Remaining attribution work |
| --- | --- | --- |
| BBLauncher fork | `licenses/BBLauncher-GPL-3.0.txt` is copied from the exact fork checkout; upstream code headers specify GPL-3.0-or-later. `SOURCE-PROVENANCE.json` gives the fork remote and commit. | The fork's corresponding source and build instructions are available at the recorded commit; confirm that any release page links them clearly. |
| Qt 6.10.0 (dynamic Windows build) | The package deploys Qt DLLs rather than a static Qt build. `licenses/qt-sbom/` holds the installed Qt 6.10.0 binary SPDX inventories; their SPDX license identifiers and dependency records describe the exact installed modules. | Check the deployed Qt modules and their notices against the release artifact and Qt redistribution terms. |
| Fork external libraries | Their `LICENSE`, `COPYING`, and `NOTICE` files from the checked-out `externals/` tree are copied under `licenses/fork-externals/`, preserving paths. | Confirm any additional notices required by the final binary dependency set. |
| AP backend, client, and native tools | `SOURCE-PROVENANCE.json` records the backend commit and pinned client revision; the release manifest records exact signed binary hashes. | The backend checkout has no repository-root `LICENSE` file. Confirm attribution and redistribution permission for backend/client/tool source before publication; the BBLauncher GPL text does not establish those terms. |
| Icons, docs, and game-derived data | Fork and backend source commits identify their provenance; the package manifest inventories shipped bytes. | Confirm asset and data redistribution terms separately. Public source availability alone does not prove permission. |

The launcher's source boundary does not remove the obligations of a bundled
binary. Preserve this inventory, the source provenance, and the exact file
manifest with every release candidate. No game installation or save data is
included by the bundle builder.
