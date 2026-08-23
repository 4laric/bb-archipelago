# Playtesting Bloodborne Archipelago

This guide is for playtesters, not developers. It takes you from a zip file to
a running randomized seed, and tells you exactly what to report back.

## What you need

1. **A Windows PC.**
2. **Your own Bloodborne game files** — a PS4 dump of `CUSA03173` at update
   **01.09**, installed into shadPS4. We cannot provide game files.
3. **shadPS4 0.18.0** — the emulator the mod runs under.
4. **Cheat Engine** — installed from its official site. The launcher uses it to
   deliver Archipelago items into the game. You never have to operate it
   yourself; the launcher opens it with the right table.
5. **The launcher package** — `BloodborneAPLauncher-win-x64.zip`, from the
   release page or sent to you directly. Unzip it anywhere.
6. **Two things from your session host** (the person running the seed):
   - your **AP seed request file** (`....bbenemizer.json`), generated with the seed;
   - the **server address** (looks like `example.com:38281`) and your **player name**.

## Setup (about five minutes)

1. Double-click **BloodborneAPLauncher.exe**.
2. Fill in the three fields the launcher cannot guess:
   - **shadPS4.exe** — pick the emulator executable. The game folder fills in
     automatically if your game is installed in the usual place.
   - **AP seed request** — the `.bbenemizer.json` your host sent you.
   - **Archipelago server** — the address your host sent you.
   Everything else (seed cache, state folder, launch plan, suppressed gameparam)
   fills itself in. Click **Save Setup**.
3. Click **Generate Launch Plan** once.
4. Click **Doctor**. Every line should say `PASS`.
   - If any line says `FAIL`, it prints a `->` remedy under it. Follow it, or
     copy the whole Doctor output to your host — it names the exact problem.
   - `WARN` lines are usually fine to proceed with; read them.

## Playing

1. Click **Randomize & Launch**. The launcher builds the seed overlay, swaps it
   in, and starts shadPS4, Cheat Engine, and the AP client for you.
2. **Start a brand-new character** for the seed, unless your host tells you
   otherwise.
3. Play. Pickups you collect are sent to Archipelago automatically, and items
   other players find for you arrive in your inventory automatically. The
   client's console window says what arrived.

### The three rules (this is early test software)

- **One character per session.** The client cannot yet tell which character is
  loaded — it trusts you. Never switch characters while connected. Checks sent
  from the wrong character are irreversible.
- **If you want to stop**, quit to the title screen first, then close things.
- **If something looks wrong** — an item that did not arrive, a pickup that
  gave the wrong thing, a crash — stop playing and report it (below). Do not
  try to fix it by reloading a save.

## What to play (the slice-1 checklist)

The current test seed covers Central Yharnam through Father Gascoigne. A full
playtest is:

1. Wake up in Iosefka's Clinic; pick up everything in the clinic and courtyard.
2. Clear Central Yharnam's pickups — every glinting corpse and item you can
   reach, including the ones behind the gate and up the ladders.
3. Note anything unusual: an item whose name looks wrong, a pickup that gave
   nothing, a pickup that gave its normal vanilla item (Blood Vials etc.)
   when it should have been randomized.
4. Optional but valuable: defeat Cleric Beast and Father Gascoigne.
5. **The restart test**: quit to title, close everything, relaunch through the
   launcher, reload your character. No item should arrive twice and no pickup
   should re-send. This is the single most valuable thing you can verify.

## What to send back after a session

In the launcher, click **Open Diagnostics** — it opens the folder with your
session files. Send your host:

1. **`ledger.json`** from the current session folder (`sessions\<long-hash>\`).
2. The **AP client console text** — select all, copy, paste into a text file.
3. A plain-English list: what you picked up, where, and anything odd.

Screenshots of anything weird help. There is no wrong way to report — "I picked
up the thing by the troll and nothing happened" is a useful report.

## Troubleshooting

| Symptom | What it means |
| --- | --- |
| Doctor says `FAIL: AP server: nothing is listening` | The host's server is not up, or the port is wrong. Check with your host. |
| Client says `a full error is available elsewhere` | Almost always a wrong server address or port. Check the server field against what your host sent. |
| `shadPS4.exe is not running or cannot be opened` | Something started shadPS4 as administrator (for example the third-party "BBLauncher" tool). Close it, then run BloodborneAPLauncher as administrator too. |
| A `PARKED AP item` line in the client console | An item delivery failed safely; later items keep arriving. Send the console text to your host — there is a tool to confirm or redeliver it. |
| Doctor says the installed gameparam was `already modified` | Your game files were changed by something else. Restore a clean 01.09 patch before playing. |

## Known limits of this build

- Checks and deliveries require the three rules above; real save-file
  identification is still being built.
- Enemy randomization is on by default. If you want vanilla enemies for a
  cleaner comparison run, untick **Randomize Enemies** before launching.
- Deaths, chat, and multiworld sync of anything beyond items are not in this
  build.
