# Playtesting Bloodborne Archipelago

This guide is for playtesters, not developers. It takes you from a zip file to
a running randomized seed, and tells you exactly what to report back.

## What you need

1. **A Windows PC.**
2. **Your own Bloodborne game files** — a PS4 dump of `CUSA03173`
   (Bloodborne: Game of the Year Edition) at update **01.09**. We cannot
   provide game files. Three things that trip people up:
   - **The exact title ID matters.** Other releases — the US standard edition
     `CUSA00900`, the EU standard edition `CUSA00207`, and the rest — are
     **not** supported, even at the same 01.09 update. The randomizer's game
     data is built against `CUSA03173` and the launcher will refuse anything
     else. Watch out for pre-modded repacks too (anything with "Mods" in the
     release name): their executables are often already patched and will not
     match what the client expects.
   - **Either install layout works.** A merged dump where `CUSA03173` is
     already at 01.09 on its own is fine; so is a vanilla base with the 01.09
     update in a separate `CUSA03173-patch` (or `CUSA03173-UPDATE`) directory
     next to it. What never works is hand-assembling folders to satisfy the
     Doctor — the launcher reads each directory's real `param.sfo` and hashes
     real game files, so empty or renamed directories are caught immediately.
   - **"shadPS4 game folder" means the game's install directory** — the folder
     *containing* `CUSA03173` — not the folder shadPS4 itself lives in.
3. **shadPS4 0.18.0** — the emulator the mod runs under.
4. **Cheat Engine** — installed from its official site. This is **required**:
   without it your pickups still reach the server, but no items can be
   delivered into your game. You never operate it yourself — the launcher
   opens it with the correct grant table, which is bundled in the package (do
   not go looking for a `.CT` file or load one by hand). Cheat Engine may ask
   to run as administrator; let it.
5. **The launcher package** — `BloodborneAPLauncher-win-x64.zip`, from the
   release page or sent to you directly. Unzip it anywhere.
6. **Two things from your session host** (the person running the seed):
   - your **AP seed request file** (`....bbseed.json`; older seeds:
     `....bbenemizer.json`), generated with the seed;
   - the **server address** (looks like `example.com:38281`) and your **player name**.

## Setup (about five minutes)

1. Double-click **BloodborneAPLauncher.exe**.
2. Fill in the four fields the launcher cannot guess:
   - **shadPS4.exe** — pick the emulator executable. The game folder fills in
     automatically if your game is installed in the usual place.
   - **AP seed request** — the `.bbseed.json` your host sent you. In a
     multiworld with more than one Bloodborne player, make sure it is **yours**:
     the file name ends with your player name, and the Doctor checks it.
   - **Archipelago server** — the address your host sent you.
   - **Your AP player name** — exactly the slot name your host gave you. The
     Doctor refuses to launch if the seed request belongs to a different slot.
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

### What normal delivery looks like

- **Consumables** (vials, bullets, Molotovs, pebbles) arrive **instantly** and
  stack onto piles you already have — if you were full, they overflow into
  storage. Nothing appearing on screen does not mean nothing arrived.
- **Key items and weapons can take up to ~30 seconds each.** They are inserted
  natively and verified one at a time, so a burst of deliveries arrives as a
  queue, not all at once. A key item taking half a minute is normal.
- The launcher's **Session status** panel shows the truth: `Ledger: N
  acknowledged` counts everything the server sent that you have actually
  received. Trust the ledger count over your memory of the inventory.

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

## Playing with other mods

**Where your mods go: `CUSA03173-mods-user`.** Make that folder next to
`CUSA03173` and `CUSA03173-patch` and put your mods inside it, laid out the way
they ship (`dvdroot_ps4\chr\...`, `dvdroot_ps4\parts\...`). The launcher
merges it into the randomizer overlay every time you launch, and never touches
the folder itself.

Do **not** put mods into `CUSA03173-mods`. That folder belongs to the launcher
and is rebuilt from scratch on every launch; anything you add there is moved
aside into a `.CUSA03173-mods.bb-ap-previous-...` folder. If you have done this
already, your files are still in those folders — move them into
`CUSA03173-mods-user` and they will come back.

Two rules on top of that:

- The randomizer's own files win. If your mod ships
  `param\gameparam\gameparam.parambnd.dcx`, or a `map\mapstudio` MSB that a
  seed's enemy randomizer also uses, that one file is left out and the
  randomizer's version is used. Nothing is silently merged and nothing is
  silently dropped.
- Click **Open Diagnostics** / run the Doctor before a session: the `user mods`
  line says how many of your files merged and names anything left out. If a mod
  seems not to be working, that line is the first place to look.

The randomizer changes exactly one game file: `gameparam.parambnd.dcx` (the
suppression binder that stops chests and corpses from also handing you their
vanilla item). It ships **no** map, model, or script files, so most cosmetic
and quality-of-life mods coexist with it fine.

How to check a mod yourself: look at the folders inside it.

- **Safe** — anything that only ships `chr`, `parts`, `mtd`, `sfx`, `msg`,
  or `action\script` (`.hks`). Models, textures, physics, and gameplay scripts
  do not touch pickups or item grants.
- **Safe, with one assumption** — mods that ship `map\mapstudio` MSB files
  (performance mods often do). Those files are where pickups live, so the mod
  is compatible only if it keeps the vanilla treasure placements. A full run
  with checks firing normally is the practical proof.
- **Not compatible** — anything that ships `param\gameparam`. A gameplay or
  item-rebalance mod will either trip the Doctor's `already modified` check
  (if installed on disk) or quietly override the suppression binder at
  runtime (if loaded through ModEngine), which means chests hand you their
  vanilla item *and* send an AP check. Restore a clean 01.09 gameparam
  before playing.

Verified compatible in playtesting (full slice completed, checks and
deliveries normal):

| Mod | What it ships |
| --- | --- |
| Boczekek's FPS boost Lite | `map\mapstudio` MSBs (keeps vanilla pickups) |
| Half Cloth Physics with Blood | `chr`, `mtd`, `parts` |
| Jump on L3 - Modern (Enhanced) | `action\script\c0000.hks` only |
| Vertex Explosion fix - modloader friendly | `parts` only |

If your favorite mod is not on this list, apply the folder check above — and
tell your host what you're running when you report back.

## Troubleshooting

| Symptom | What it means |
| --- | --- |
| Doctor says `FAIL: AP server: nothing is listening` | The host's server is not up, or the port is wrong. Check with your host. |
| Client says `a full error is available elsewhere` | Almost always a wrong server address or port. Check the server field against what your host sent. |
| `shadPS4.exe is not running or cannot be opened` | Something started shadPS4 as administrator (for example the third-party "BBLauncher" tool). Close it, then run BloodborneAPLauncher as administrator too. |
| A `PARKED AP item` line in the client console | An item delivery failed safely; later items keep arriving. Send the console text to your host — there is a tool to confirm or redeliver it. |
| Doctor says the installed gameparam was `already modified` | Your game files were changed by something else. Restore a clean 01.09 patch before playing. |
| Geometry stretches into huge spikes across the screen | A known shadPS4 emulator bug ("vertex explosions", shadPS4 issue #1232), not the randomizer. Enabling **readbacks** in the shadPS4 settings usually fixes it (small performance cost); tell your host if you see it. |

## Known limits of this build

- Checks and deliveries require the three rules above; real save-file
  identification is still being built.
- Three pickups are **inert** in this slice: two in the Iosefka's Clinic
  back yard (Madman's Knowledge, Blood Gem) and the White Messenger Ribbon
  (a quest that can only finish after Rom's blood moon). Reaching them needs
  progress far past the goal, so they are not AP checks yet and their
  vanilla items stay suppressed. They become real checks when the world
  grows. Everything else you can reach through Gascoigne is a live check,
  including the Red Jeweled Brooch and the Blood Gem Workshop Tool.
- Enemy randomization is on by default. If you want vanilla enemies for a
  cleaner comparison run, untick **Randomize Enemies** before launching.
- Deaths, chat, and multiworld sync of anything beyond items are not in this
  build.

## For the host: cutting a release

Playtesters download prereleases; they need no GitHub login. To cut one:

```powershell
git checkout main; git pull
git tag -a v0.1.0-playtest.N -m "what changed"
git push origin v0.1.0-playtest.N
```

Pushing the tag runs the `release` workflow (~3 minutes), which builds the
Windows launcher package — launcher, native tools, CE table, and the
`bb-ap-client` built from the client repo's current `main` — and attaches
`BloodborneAPLauncher-win-x64.zip` plus `bloodborne.apworld` to a GitHub
prerelease. Verify the two assets appeared before posting the link.

**The suppression binder is NOT in that zip** — it is licensed-game-derived
and never built in CI. Send playtesters `gameparam.parambnd.dcx` and
`build-manifest.json` from your local `work\vanilla-suppression-build\`
alongside the release link (or ship a full local `build.ps1 -Package` zip,
which bundles them). The launcher Doctor checks both halves either way.
