Bloodborne Archipelago launcher (Windows x64)
================================================

Run BloodborneAPLauncher.exe. The package contains the enemy planner, the
compressed-map miner, and the guarded native map/param writers. It contains no
Bloodborne or shadPS4 files.

Randomize Enemies is enabled by default. Select the shadPS4 game folder and the
launcher will find the installed compressed MapStudio files and build its enemy
inventory automatically. A failed build never writes to the base/update game
trees; successful outputs enter a verified external cache before activation.

This release slice still asks for the seed's .bbenemizer.json, a previously
built suppression binder and build-manifest.json, and a hash-pinned process
plan. See docs/LAUNCHER.md for the formats and safety model.

The optional native AP client is present under tools when its prebuilt
executable was supplied to the packaging command.
