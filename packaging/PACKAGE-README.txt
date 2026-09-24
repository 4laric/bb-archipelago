Bloodborne Archipelago downloads (Windows x64)
==============================================

This release offers two launcher downloads. Unzip either one into its own
folder and keep that folder intact. Neither archive includes Bloodborne or
shadPS4 files.

BBLauncher-AP-win-x64.zip is the BBLauncher fork. It combines the existing
BBLauncher settings and mod manager with Archipelago and standalone local
randomization. Select your game and emulator in Settings, then choose a mode
on the randomizer page. Randomize prepares an inactive mod; Launch verifies
and activates that prepared run before starting the emulator. Archipelago
mode uses an AP seed/player and client. Standalone uses a seed string and
starts no AP client or server. Enemy randomization is optional; reviewed boss
shuffle runs with Archipelago enemy randomization. Scaling defaults on. The package
contains its frozen backend, native tools, client, and provenance manifest.
On first launch it can import an existing regular BBLauncher setup from nearby
folders or Downloads, preserving the original configuration.

BloodborneAPLauncher-win-x64.zip is the original Archipelago launcher. Run
BloodborneAPLauncher.exe, select shadPS4, your AP seed request and server,
save Setup, then use its plan/Doctor and Play flow. It remains available for
existing players and download links.

bloodborne.apworld is attached separately for people generating seeds. The
original launcher archive also contains it at worlds\bloodborne.apworld and
can install it into a selected Archipelago installation. Players connecting
to an existing seed do not need to install the apworld themselves.

Keep the previous launcher folder for rollback, and stop the game before
changing launchers or active mods. For the BBLauncher fork's short integration
check, see docs\BBLAUNCHER-NEXT-RUN.md in that archive. For original launcher
setup, see docs\PLAYTESTING.md in its archive.

These archives and the apworld are built from this repository's release tag.
Verify the exact download with GitHub's attestation command:

  gh attestation verify BBLauncher-AP-win-x64.zip --repo 4laric/bb-archipelago
  gh attestation verify BloodborneAPLauncher-win-x64.zip --repo 4laric/bb-archipelago

See https://github.com/4laric/bb-archipelago/security/policy for release
provenance and private vulnerability reporting. Release notes link the scans
and hashes for the published assets.
