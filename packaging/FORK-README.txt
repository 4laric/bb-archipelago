BBLauncher-AP: local next-run candidate

Keep this folder intact and run BBLauncher-AP.exe. Select your existing
Bloodborne installation and shadPS4 build in the launcher's settings.

Open the Archipelago page:
- Archipelago: choose your AP seed file and player/connection details.
- Standalone: enter any seed text and choose whether to include the DLC.
  No AP server or client is needed for this mode.

Randomize prepares an inactive mod. Launch verifies and activates the selected
run, then starts the game. Changed generation inputs invalidate preparation.
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
