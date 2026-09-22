# BBLauncher integration

Status, 2026-09-22: **development candidate; unsupported for general play**.
The adapter is implemented, but its live acceptance matrix is incomplete. It
fails closed unless the operator explicitly enables the pinned live-acceptance
candidate. Do not describe a local source build or a passing filesystem fixture
as supported BBLauncher integration.

This mode exports a seed-specific data mod for rainmakerv3's BBLauncher. It
does not embed the AP client in BBLauncher and does not let the standalone
launcher transaction adopt BBLauncher's overlay.

## Player workflow

Use the **BBLauncher** tab in the desktop launcher:

1. Select **Use BBLauncher to manage and start Bloodborne** and choose the
   **BBLauncher app**. The companion detects its inactive `BBLauncher/Mods`
   library. Choose your game installation, AP seed and player in **Play**.
2. During development acceptance only, select **Enable experimental BBLauncher
   integration for this session**. A normal invocation refuses the candidate.
3. Select **Build mod for BBLauncher**. The companion remembers the prepared
   mod and shows its name; no receipt file selection is needed.
4. With shadPS4 stopped, open Mod Manager in BBLauncher. Deactivate any previous
   Archipelago mod, then activate the named prepared mod. Keep only one AP mod
   active. If BBLauncher reports a file conflict, cancel and deactivate the
   conflicting mod; do not accept an override or use Mod Merger.
5. With shadPS4 still stopped, select **Check activated mod** in the companion.
6. Start Bloodborne from BBLauncher, then select **Connect to game** here.

The game's `install/CUSA03173-mods` folder is the activated overlay, not the
export destination. An incorrect saved folder gets an inline explanation and
**Use detected mod folder** correction. Custom library paths are available
under **Advanced settings**, along with recovery of an earlier export from
its saved JSON record if the remembered selection is lost.

For the next session, start the game in BBLauncher and connect again. A server
failure does not require rebuilding the package. If activation or any AP-owned
file changes, stop the game, verify again, and perform a fresh boot.

To play without AP, stop the AP client and shadPS4, deactivate the AP package in
BBLauncher, and start the game there. **How to play without Archipelago** explains
this sequence; it does not deactivate other BBLauncher mods.

The same development flow is available from the CLI:

```powershell
python -m bb_launcher bblauncher-export --settings launcher-settings.json --live-acceptance-candidate
python -m bb_launcher bblauncher-verify --settings launcher-settings.json --live-acceptance-candidate
python -m bb_launcher bblauncher-connect --settings launcher-settings.json --live-acceptance-candidate
```

## Responsibility split

The companion builds and exports locally derived game data, owns the receipt,
seed identity, runtime configuration, and durable AP ledger, verifies the active
installation, and starts the AP client. BBLauncher owns package activation,
deactivation, conflict backup/restoration, the active-package directory, the
`CUSA03173-mods` overlay, and starting shadPS4.

The exported package contains generated game data only. It contains no
executable, AP server/password, save, log, ledger, runtime configuration, or
receipt. Public releases must not ship a universal game-derived package.

Standalone **Randomize & Launch**, **Launch Vanilla**, **Restore Previous**, and
the standalone **Connect to running game** ownership path are unavailable in
BBLauncher mode. The external verifier returns a separate
`VerifiedExternalActivation`; it never creates `.bb-ap-owner.json`, weakens the
standalone owner check, repairs BBLauncher state, or activates a package.

## Settings and persistent state

`launcher-settings.json` adds these fields:

| Field | Meaning |
| --- | --- |
| `integration_mode` | `"bblauncher"` selects this mode; `"standalone"` keeps the existing transaction. |
| `bblauncher_executable` | Exact pinned `BB_Launcher.exe` used for this export and connection. |
| `bblauncher_mods` | BBLauncher's inactive `Mods` directory, never its `Mods-Active (DO NOT DELETE)` directory. |
| `bblauncher_receipt` | Receipt selected for verification and connection; the UI fills it after export. |

The usual `game_root`, `cache_root`, `ap_request`, suppression binder/manifest,
`process_plan`, `state_root`, and shadPS4 log settings still apply. Cache data
may live under `<state_root>/seeds`; receipts live under
`<state_root>/external/receipts`; boot observations and seed/slot ledgers remain
outside BBLauncher's movable directories.

The receipt records the selected seed and slot even though the build cache key
deliberately excludes them when two sessions produce identical bytes. It also
records source hashes, seed options, suppression identities, all exported file
hashes, game/AppVer, build-manifest digest, cache/ledger namespaces, companion,
world, runtime, client provenance, and the exact BBLauncher commit/executable
hash.

## Verification and limitations

Verification is case-insensitive and requires exactly one instance of every
AP-owned path. It accepts BBLauncher's regular-file copy route and its expected
per-file symlink route. It rejects partial activation, changed or missing files,
duplicate-case paths, dangling/cyclic/escaping links, directory reparses, an
unexpected link target, a standalone owner manifest, multiple AP packages, and
every collision from any other active package even when the bytes are equal.
The effective installed binder is passed to the client; a matching binder does
not excuse a changed event, map, message, or AI file.

Current scope is Windows, a directory-backed `CUSA03173` AppVer `01.09`
installation, and explicitly pinned BBLauncher binaries. Linux, archive/ZAR
installs, unpinned or later BBLauncher builds, automatic activation/deactivation,
and one-button launch from BBLauncher's Play button are unsupported. Deletion or
tombstone mods are unsupported beside AP. Additive cosmetic/SFX mods are allowed
only when they do not occupy an AP-owned path.

The only accepted development candidates currently come from BBLauncher commit
`f092023f6cdf36a83ce735f7124b7835e9cf03b0` (Release 16.10 source):

- UAC/symlink executable SHA-256
  `a990d5507f22d8b0590d8b9426519c98de6fe86042a61a32e679e4a1a66b2d0a`;
- no-UAC/copy executable SHA-256
  `2cfa43cf05a16e0c0ebaf87275d295961afff32c91ea57962e83c474358881f0`.

Both remain candidates. The opt-in flag records development intent; it is not a
support override for arbitrary builds.

## Live acceptance record

The implementation becomes supported only after both pinned Windows routes pass
the complete matrix. Current evidence is deliberately narrower:

| Check | no-UAC copy | UAC symlink |
| --- | --- | --- |
| BBLauncher GUI activation | Passed | Pending |
| Companion verifies every installed file | Passed | Pending |
| shadPS4 starts the selected game to the title screen | Passed | Pending |
| Native AP attach after copy/symlink activation | Passed after fixing the first copy-attach bug | Pending |
| Connect, receive/check, save, restart, and reload without duplicate delivery | Pending | Pending |
| Additive SFX coexistence and AP-path conflict refusal | Pending | Pending |
| Seed switch with reverse-order deactivation/restoration | Pending | Pending |
| Interrupted activation recovery through BBLauncher | Pending | Pending |
| Base/update hashes unchanged across the run | Passed: 29,273 files rehashed, 0 changed or added | Pending |

Acceptance must capture the BBLauncher executable hash, package receipt,
activation route, process identity, connection result, delivery ledger across
reload, conflict/recovery observations, and before/after base/update hashes.
Automated fixtures cover export interruption, copy and symlink shapes, file-set
and link failures, collisions, boot ordering, and state-write boundaries, but do
not replace this live matrix.

Implementation boundaries are in `bb_launcher/external.py` (artifact and
read-only verifier), `bb_launcher/external_workflow.py` (prepare/export, fresh
boot observation, and client-only connection), and `bb_launcher/external_ui.py`
(the desktop controls). Focused fixtures are in
`tests/test_launcher_external.py` and
`tests/test_launcher_external_workflow.py`.
