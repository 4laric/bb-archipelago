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
  -ForkSourceRoot C:/source/BB_Launcher-AP `
  -OutputRoot ./build/fork-candidate
```

Use `-DebugBuild` only for a local Debug build with the matching compiler
runtime installed. Use `-PythonExecutable` to select the build environment
with PyInstaller installed. The player does not need Python. A separate
`-ClientPath` can override the client executable in the tools directory.

The backend also bundles the standalone item award catalog. The script runs
`smoke_fork_bundle.py` against the actual packaged Qt executable,
frozen backend and enemy planner from a temporary working directory. It checks
startup, seed inspection, and increased coverage with the shipped expansion data.
Qt widget/coordinator tests and the repository gate remain separate checks;
none of these replaces the live game test. The manifest records source and
client provenance, executable/tool/catalog hashes, optional fork source revision,
and that gameplay has not been tested. The frozen standalone enemy planner must
produce the same default curated swaps as the packaged AP planner.

Open the candidate from its own folder. Keep the working original launcher
available. Select the existing game and emulator through the fork's settings,
then open the randomizer page and choose Archipelago or Standalone. In AP mode,
choose a seed file and player; in standalone, enter a seed string and select
base-game or DLC content. **Randomize** prepares an inactive mod; **Launch**
verifies and activates it before starting the game. Standalone starts no AP
client. Unknown fork provenance
is an informational warning, not a build-approval gate or an extra checkbox.
The game and AP client must stop before switching seeds or removing AP mods.

The enemy choice is reviewed randomization, expanded experimental coverage, or
vanilla. Expanded coverage and boss shuffle belong to AP mode; standalone offers
the default ordinary-enemy pool. Advanced tuning stays collapsed. AP's enemy
seed is editable; leaving it blank uses the seed file. Changing build inputs
invalidates the prepared selection. Preparation reports the generated result.

The short next-run acceptance procedure is in
[BBLAUNCHER-NEXT-RUN.md](../docs/BBLAUNCHER-NEXT-RUN.md). Fixture tests and offline
exports do not substitute for that live acceptance.

For the reviewed Central Yharnam sleep routine, randomized replacements start
awake with their own AI. The fallback removes only that placement's sleep-routine
invocation; it leaves spawn triggers, quest logic and unrandomized actors intact.
This behavior is checked statically and in native writer fixtures, not yet in game.

The Qt backend protocol passes opaque play/arm IDs. The backend retains the
prepared launch plan behind those IDs and starts only the AP client; Qt owns
the emulator. Neither the player nor the UI needs to select receipt files.

For development, backend discovery checks the adjacent frozen bundle first,
then `BB_AP_BACKEND`, then `BB_AP_SOURCE_ROOT` with `BB_AP_PYTHON` or Python
discovered on PATH. Remove the adjacent development backend copy if testing
source changes; otherwise it takes precedence.
