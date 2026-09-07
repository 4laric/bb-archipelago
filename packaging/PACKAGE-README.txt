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
the Bloodborne apworld the launcher can install for seed generators,
and -- when the build had one -- the vanilla-suppression binder with its
build manifest. It contains no Bloodborne or shadPS4 files, and it never
writes to your base or update game trees; every change lives in a verified
overlay the launcher owns and can roll back.

See docs\LAUNCHER.md for the safety model and file formats.
See https://github.com/4laric/bb-archipelago/security/policy for the security
model, release-provenance checks, and private vulnerability reporting.

Every release links its VirusTotal scan. The client reads game-process memory,
so a few heuristic engines routinely flag unsigned tooling of this kind; the
signal to watch is the major engines and that results stay consistent release
to release. The artifact hashes below and this command prove any download is
exactly what this public CI built from this public source:

  gh attestation verify BloodborneAPLauncher-win-x64.zip --repo 4laric/bb-archipelago

bloodborne.apworld ships INSIDE this package, at worlds\bloodborne.apworld,
and is also attached alongside the zip. Only the person GENERATING seeds
needs it. You do not have to place it yourself: on Create & host, pick your
Archipelago installation and press Create seed -- if the Bloodborne world is
missing or is a different version, the launcher says so and offers one button
that installs or updates it in that installation's custom_worlds. Nothing is
installed until you press it. Archipelago reads its worlds at start, so close
and reopen ArchipelagoLauncher afterwards.

Copying it by hand still works: drop bloodborne.apworld in
Archipelago\custom_worlds, or install it with ArchipelagoLauncher. If your
Archipelago is a source checkout that already carries the world under
worlds\bloodborne, update that checkout instead -- the launcher refuses to
install beside it. Players who only connect to a hosted server need none of
this.

Verify that the launcher archive was built by this repository's public CI:
gh attestation verify BloodborneAPLauncher-win-x64.zip --repo 4laric/bb-archipelago
