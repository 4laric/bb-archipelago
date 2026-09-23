# BBLauncher-AP fork

Upstream baseline: `rainmakerv3/BB_Launcher` at
`ca12c2fc38b8ba485e508bde815e8ea8cb49ac10`.
Fork: [4laric/BB_Launcher-AP](https://github.com/4laric/BB_Launcher-AP).
The development checkout is `work/BB_Launcher` (ignored, not vendored).

The Qt app owns mod activation and emulator startup. The Python backend owns
seed preparation, receipt verification and the native AP client. The coordinator
passes prepared-session handles between them; it does not ask the player to
choose receipt files or manually activate each seed.

Following [PR #446](https://github.com/4laric/bb-archipelago/pull/446), untested
build provenance is informational, not an unconditional refusal or an additional
candidate checkbox. Checks that protect changed files and the active seed/process
remain part of the operation that needs them. A successful build or protocol
handshake is not gameplay acceptance.

- Generic services: `modules/ModService.*` and `EmulatorService.*`.
- AP UI and sequencing: `ApPage.*`, `ApCoordinator.*`, `ApBackend.*`.
- Backend: `bb_launcher/integrated/` in this repository.
- Tests: `tests_cpp/` in the fork and `tests/test_integrated*.py` here.
- Local bundle build and test instructions: [BUNDLE-LAYOUT.md](BUNDLE-LAYOUT.md).
- Distribution inventory: [LICENSE-INVENTORY.md](LICENSE-INVENTORY.md).

The local Windows toolchain uses Qt 6.10.0, clang-cl with MSVC libraries and Ninja.
Configure with `BB_AP_FORK=ON`, `BB_AP_BUILD_TESTS=ON`, `FORCE_UAC=OFF`
and `USE_WEBENGINE=OFF`. A shared-Qt Debug build is available locally;
a public signed release and live game acceptance are separate work.

