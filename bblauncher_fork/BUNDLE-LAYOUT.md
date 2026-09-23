# BBLauncher-AP local test bundle

The bundle builder is `packaging/build_fork_bundle.ps1`. It freezes this
checkout's backend, deploys Qt dependencies for the compiled fork and copies
the explicitly supplied native tools, client and suppression inputs. It creates
a new directory under `build/`; it does not replace an installed launcher,
change a game directory, publish a release or claim gameplay acceptance.

```text
BBLauncher-AP/
  BBLauncher-AP.exe
  Qt*.dll, platforms/, ...
  candidate-manifest.json
  ap_backend/
    bb-ap-backend.exe
    _internal/                 # Python runtime, world tables and research
    tools/                     # packaged native writers and planners
    ap-client/bb-ap-client.exe
    suppression/
      gameparam.parambnd.dcx
      build-manifest.json
```

Example from the AP checkout (replace input paths with your actual builds):

```powershell
./packaging/build_fork_bundle.ps1 `
  -ForkExecutable C:/build/BB_Launcher.exe `
  -QtBin C:/Qt/6.10.0/msvc2022_64/bin `
  -ToolsDirectory C:/build/BloodborneAPLauncher/tools `
  -SuppressionDirectory C:/build/BloodborneAPLauncher/work/vanilla-suppression-build `
  -ClientRef <client-source-commit> `
  -OutputRoot ./build/fork-candidate
```

Use `-DebugBuild` only for a local Debug build with the matching compiler
runtime installed. Use `-PythonExecutable` to select the build environment
with PyInstaller installed. The player does not need Python. A separate
`-ClientPath` can override the client executable in the tools directory.

The script runs `smoke_fork_bundle.py` against the actual frozen backend from
a temporary working directory. It checks the protocol and seed inspection.
Qt widget/coordinator tests and the repository gate remain separate checks;
none of these replaces the live game test. The manifest records source and
client provenance, executable hashes, and that gameplay has not been tested.

Open the candidate from its own folder. Keep the working original launcher
available. Select the existing game and emulator through the fork's settings,
then open Archipelago, choose a seed and press Play. Unknown fork provenance
is an informational warning, not a build-approval gate or an extra checkbox.
The game and AP client must stop before switching seeds or removing AP mods.

The Qt backend protocol passes opaque play/arm IDs. The backend retains the
prepared launch plan behind those IDs and starts only the AP client; Qt owns
the emulator. Neither the player nor the UI needs to select receipt files.

For development, backend discovery checks the adjacent frozen bundle first,
then `BB_AP_BACKEND`, then `BB_AP_SOURCE_ROOT` with `BB_AP_PYTHON` or Python
discovered on PATH. Remove the adjacent development backend copy if testing
source changes; otherwise it takes precedence.

