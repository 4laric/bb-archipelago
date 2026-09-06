# Read-only weapon diagnostic

Send `BloodborneWeaponProbe.exe` to the player. It is standalone; no Python,
launcher replacement, restart, or deliberate crash is needed.

1. Load the affected character in the ordinary AP session, with the AP client
   connected and exactly one shadPS4 process running. Keep Tonitrus and another
   weapon already known to work in held inventory. Do not equip, buff, or attack
   just for this capture.
2. Note both weapons' names and displayed reinforcement levels in the inventory
   menu. Close the menu and stand still.
3. Open the probe, enter those names/levels, and click **Capture diagnostic**.
   The default shadPS4 log locates the current game; Browse supports portable
   installs with a different log location.
4. Return the `weapon-probe-*.zip` written to Downloads using **Open output folder**.
   Return incomplete/error bundles too; do not provoke an attack to hydrate a
   missing client inventory cache.

Expected operator time: about one minute, zero restarts. No special comparison
weapon needs to be obtained. Normal process permissions suffice unless shadPS4
is running elevated; in that case the probe needs matching elevation.

## Preregistered control and interpretation

Step zero is the operator-labeled known working weapon. Its captured normalized
row and reinforcement level must agree with the on-screen observation, and its
instance handle must match the registry object. Until reviewed, the bundle says
`operator_confirmation_required`; a successful read is not a validated weapon.
Stop interpretation if this control fails or inventory changes during capture.

Hypothesis: the affected Tonitrus's backing instance has inconsistent identity,
reinforcement, durability, or raw data compared with a working control. Identity
or row mismatches are reported explicitly but may also mean an unstable read.
A coherent matching capture weakens that specific hypothesis; it does not rule
out SFX/emulator issues, transient state, or fields outside the captured window.
Unreadable memory or failed image/control checks mean diagnostic miss, never
proof of corruption or absence.

ZCrashv5 already contains the Tonitrus +1 slot (76) and delivery acknowledgment,
but not the backing object bytes. This probe adds that missing evidence using
the external equivalent of the game's resolver. It performs no remote calls,
installs no hooks, and opens the process with query/read rights only. It does not
collect server credentials, saves, configuration files, or full process dumps.
The result contains inventory rows plus 0x100-byte raw windows beginning at
resolved weapon instances. These windows may include adjacent allocation bytes;
they are not claimed to cover a complete object. Gem offsets remain undecoded.

## Validation and build

The resolver was disassembled from a local title-screen session, PID 24496,
eboot base `0x5720000`; its complete function hash matched in the production
reader. No character was loaded. The recorded ZCrashv5 slot is a positive decoder
fixture; backing traversal tests are synthetic. A local read-only Windows API
self-test passes, and the title-screen negative control correctly returns an
incomplete bundle for an unpopulated AP inventory cache. Live weapon/control
validation is therefore still an operator step, not a claimed completed test.

Run `python -m unittest discover -s tests -p "test_weapon_probe*.py"`.
Build from the repository root:

```powershell
python -m PyInstaller --noconfirm --onefile --windowed --name BloodborneWeaponProbe --hidden-import weapon_probe_core --hidden-import weapon_probe_resolver --paths tools --distpath dist/weapon-probe --workpath build/weapon-probe --specpath build tools/weapon_probe_app.py
```

`BloodborneWeaponProbe.exe --self-test --self-test-result result.json` exercises
the packaged read-only API against its own allocated buffer.
