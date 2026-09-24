BBLauncher-AP: local next-run candidate

Keep this folder intact and run BBLauncher-AP.exe. Select your existing
Bloodborne installation and shadPS4 build in the launcher's settings.
On first launch, the AP fork looks for a regular BBLauncher setup beside its
folder or in Downloads and imports valid game/emulator paths and ordinary
preferences. It preserves the original config and any existing AP config.

Open the Archipelago page:
- Archipelago: choose your AP seed file and player/connection details.
- Standalone: enter any seed text and choose whether to include the DLC.
  No AP server or client is needed for this mode.

Randomize prepares an inactive mod. Launch verifies and activates the selected
run, then starts the game. Changed generation inputs invalidate preparation.
If a prepared AP mod already exists, Rerandomize enemies chooses a fresh enemy
and boss seed while keeping the AP world and item placements.
Enemy randomization includes boss shuffle in AP mode. Scaling defaults on.
On Launch, a verified mod from the previous AP launcher is retired automatically
before the new mod is activated; unrelated merged files are preserved.
Regular play removes the randomizer package owned by this launcher while
preserving unrelated mods. Stop the game before changing active mods or modes.

Both modes support reviewed or expanded ordinary-enemy coverage. AP also
supports reviewed boss shuffle; standalone does not shuffle bosses. Boss gameplay and the full
roster expansion remain experimental; this package includes landed fixes.

The candidate has offline build and fixture-test evidence, not completed live
gameplay acceptance. See docs/BBLAUNCHER-NEXT-RUN.md for the short next-run check.
candidate-manifest.json records the bundled versions and file hashes.

This candidate is a separate application folder. It does not replace your
existing launcher during extraction. Retain the previous folder for rollback;
do not switch back while the game is running or leave a randomizer mod active
under two different mod managers.
