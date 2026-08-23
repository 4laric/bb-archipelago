Bloodborne Archipelago launcher (Windows x64)
================================================

New here? Read docs\PLAYTESTING.md first -- it is the five-minute setup
guide written for players, including what to send back after a session.

Quick version:

1. Run BloodborneAPLauncher.exe.
2. Pick your shadPS4.exe, your AP seed request (....bbenemizer.json, from
   whoever generated the seed), and the Archipelago server address.
   Everything else fills itself in. Save Setup.
3. Click Generate Launch Plan once, then Doctor -- every line should say
   PASS before you play.
4. Randomize & Launch.

One character per session, never switch characters while connected, and if
something looks wrong, stop and report it (see the PLAYTESTING guide).

The package contains the launcher, the enemy planner, the map miner, the
guarded native writers, the item-grant Cheat Engine table, the AP client,
and -- when the build had one -- the vanilla-suppression binder with its
build manifest. It contains no Bloodborne or shadPS4 files, and it never
writes to your base or update game trees; every change lives in a verified
overlay the launcher owns and can roll back.

See docs\LAUNCHER.md for the safety model and file formats.
