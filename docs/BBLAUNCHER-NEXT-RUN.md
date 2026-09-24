# BBLauncher next-run candidate

Tracking: [BBLauncher-AP #3](https://github.com/4laric/BB_Launcher-AP/issues/3).

The Qt fork shares the current backend, native writers and curated enemy data.
It carries the launcher overhaul into one page: choose a mode, set its inputs,
Randomize to prepare an inactive mod, then Launch to verify and activate it.
Changing generation inputs invalidates the prepared selection. Advanced enemy
tuning stays out of the ordinary flow.

Archipelago mode uses a seed file and the AP client. Standalone mode generates
local item rewards from a seed string and needs no AP room or client. Its enemy
choice covers the ordinary curated pool; experimental releases and boss shuffle
are not standalone features in this candidate. Existing packages and generated
seeds remain pinned to the rules used to create them.

## Short acceptance pass during the next run

Question: does the packaged fork prepare, activate and launch the selected run,
then preserve that run's state across a normal restart?

Budget: at most ten minutes beyond normal play, one planned restart, no required
travel or boss fight. Use the next convenient eligible pickup rather than a
special trip. This checks launcher integration; it does not certify every item
award or boss pairing. No save editing or recovery grants are part of this test.

1. With the game stopped, select the intended game installation in the fork.
   Choose Archipelago and the intended seed/player, or Standalone and a seed.
2. Press **Randomize**. Control: it reports a prepared result without launching
   the emulator or activating a mod. Launch should reuse this prepared selection.
   Standalone Randomize deliberately rebuilds and revalidates its native output;
   repeat preparation is not a warm-cache performance claim. If preparation
   fails, stop here and retain diagnostics.
3. Press **Launch**. Control: exactly one emulator starts. AP mode should connect
   the intended player; standalone must not ask for an AP server or start a client.
4. At the next convenient eligible pickup, compare the result with the prepared
   seed's output. In AP, observe the corresponding check/delivery status. Do not
   consume a vial or bullet merely to make delivery start. If readiness or delivery
   stalls, capture its displayed state and stop this acceptance pass.
5. Save and quit normally, then launch the same run again. Verify the saved state
   remains and the already-completed pickup is not re-granted.

| Result | Interpretation and next action |
| --- | --- |
| Preparation, correct activation, reward/check and restart all succeed | The tested mode and exact package pass this integration slice. Continue ordinary play. |
| Preparation or verification reports an error | Packaging/input/ownership failure before gameplay. Keep the diagnostic output; fix offline. |
| Wrong seed/player, extra emulator/client, or standalone asks for AP | Mode/launch sequencing defect. Stop; do not retry a reward. |
| Correct launch but no reward/check, or an unexpected reward | Keep the prepared identity and client status. Determine whether this is delivery or award coverage offline; do not extend the run with a distant test. |
| Restart duplicates a reward or loses session state | Persistence defect. Stop and preserve the ledger and diagnostics without editing them. |
| Timeout, crash or unclassified result | Stop within the budget; preserve evidence and redesign the next test offline. |

Regular-play restoration and third-party-mod conflicts have fixture coverage but
need their own controlled installation acceptance before a public release. They
must preserve unrelated mods and restore only files with established ownership.
Public distribution also requires the outstanding license, signing and
update/rollback checks in the integration spec; this local candidate does not
claim those are complete.
