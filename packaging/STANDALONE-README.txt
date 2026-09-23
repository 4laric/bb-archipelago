Bloodborne Standalone Randomizer
================================

This package generates a local item randomizer overlay, with optional ordinary
enemy randomization, for an existing Bloodborne installation. It does not need
Python or .NET. It does not install or replace BBLauncher, activate mods, start
the game, connect to a server, or touch save files.

The examples below use PowerShell. Replace paths with your own paths. The game
root is the installed dvdroot_ps4 directory, not its CUSA03173 parent.

1. Build a verified local overlay
---------------------------------

Item randomization:

  .\BloodborneRandomizer.exe build `
    --game-root "D:\Games\CUSA03173\dvdroot_ps4" `
    --seed "my-seed" `
    --output "D:\BBRandomizer\my-seed-overlay"

Items plus ordinary enemies and static scaling normalization:

  .\BloodborneRandomizer.exe build `
    --game-root "D:\Games\CUSA03173\dvdroot_ps4" `
    --seed "my-seed" `
    --output "D:\BBRandomizer\my-seed-overlay" `
    --randomize-enemies `
    --normalize-enemy-scaling

The output path must not already exist and must stay outside the game folder.
The builder reads the original game files and writes a new overlay directory.
It verifies its native writer receipts and records exact file hashes.

Run this for every available build option:

  .\BloodborneRandomizer.exe build --help

2. Export for the existing BBLauncher
-------------------------------------

To create a ZIP that can be extracted into BBLauncher's Mods directory:

  New-Item -ItemType Directory "D:\BBRandomizer\exports"
  .\BloodborneRandomizer.exe export `
    --overlay "D:\BBRandomizer\my-seed-overlay" `
    --zip-root "D:\BBRandomizer\exports" `
    --receipt-root "D:\BBRandomizer\exports"

Extract the ZIP directly into BBLauncher\Mods. The archive contains one
top-level mod folder. Open your existing BBLauncher and activate that folder
with its Mod Manager.

To write the package directly into an existing inactive Mods library, keep the
receipt somewhere outside the BBLauncher directory:

  New-Item -ItemType Directory "D:\BBRandomizer\receipts"
  .\BloodborneRandomizer.exe export `
    --overlay "D:\BBRandomizer\my-seed-overlay" `
    --mods-root "D:\BBLauncher\Mods" `
    --receipt-root "D:\BBRandomizer\receipts"

The exporter refuses Mods-Active (DO NOT DELETE), existing package names,
unexpected game-data paths, missing files, extra files, and hash drift. It
never activates the package.

3. Verify an export
-------------------

  .\BloodborneRandomizer.exe verify `
    --package "D:\BBRandomizer\exports\Bloodborne-Standalone-my-seed-ABC.zip" `
    --receipt "D:\BBRandomizer\exports\Bloodborne-Standalone-my-seed-ABC.export-receipt.json" `
    --overlay "D:\BBRandomizer\my-seed-overlay"

Use the exact generated names printed by the export command. Supplying the
overlay checks the exported files and their original build provenance.

Safety and compatibility
------------------------

- Keep original game files, generated overlays, exports, and receipts in
  separate directories.
- Deactivate conflicting mods in BBLauncher before activating a generated
  randomizer package.
- The package contains generators, native writers, data tables, and a pinned
  research bundle. It contains no player game files or save data.
- A valid build or export receipt proves byte integrity. It does not claim that
  a seed has completed live gameplay testing.
