# Known limitations of the beta

This is the honest list. It is written for players and hosts, and it is kept
current with each release. If something on this page bites you, the
[rescue console](#if-you-get-stuck-the-rescue-console) at the bottom is how a
host repairs it in place, and [PLAYTESTING.md](PLAYTESTING.md) says what to
send back so the next release can fix the cause.

Supported target: `CUSA03173` at update `01.09` under shadPS4 0.18.0. Nothing
else is, and the launcher refuses other builds.

You also need **DarkScript3 version 3.6.3**, downloaded separately. The
launcher compiles two event-script overlays from your own game files when it
prepares a seed and checks the compiler by hash. See
[PLAYTESTING.md](PLAYTESTING.md) for where to get it.

## Never verified in a live game

These parts of the randomizer are generated, in logic, and packaged, but no
one has played through them yet. They may work. They may not. Treat them as
untested and report what happens either way.

For scale: the furthest a live randomized playtest has reached is defeating
Mergo's Wet Nurse, with the client running and checks sending the whole way.
What lies beyond that (Gehrman, the Moon Presence, and the DLC) has not been
played.

### The Old Hunters DLC

`include_dlc: true` adds all seven DLC regions, their bosses, progression
items, and checks. **No one has entered the DLC in a randomized game.** No DLC
boss flag has been observed firing, no DLC pickup has been observed sending a
check, and the DLC entry sequence (Eye of a Blood-drunk Hunter, then Amygdala's
grasp in Cathedral Ward) has only been exercised up to the Eye check itself.
The option defaults off. If you turn it on, you are the first, and your
client log is the evidence.

### Endings and goal completion

The three goals are detected from the boss completion flags of Mergo's Wet
Nurse, Gehrman, and the Moon Presence. Mergo's Wet Nurse has been defeated in
a live playtest, so that flag is observed. **Gehrman and the Moon Presence
have not been reached with the client running**, so goal reporting for
`refuse_gehrman` and `moon_presence` is inferred from the game's scripts and
nothing more. The `goal` rescue recipe exists for exactly this case.

### Laurence's Skull and the Forbidden Woods password

The Grand Cathedral altar interaction (Laurence's Skull, after Vicar Amelia)
is an AP check, and the Forbidden Woods password "Fear the Old Blood" is a
shuffled item. Making that work requires a patched Cathedral Ward event file.
**In every playtest so far that patch was not installed, so the altar check
never sent and the vanilla password was granted for free.** This beta packages
the patch into the launcher install for the first time. It has never been
verified live. Two outcomes are possible:

- the patch installs and works: the altar sends its check, and the gate opens
  only when you receive the item;
- the patch is missing or fails: the altar sends nothing, and the gate opens
  anyway after the cutscene. Your seed is still completable, one location is
  stranded, and a host can send it with the `laurence-skull` rescue recipe.

Check the launcher's install report for the Cathedral event overlay before
you start. The client refuses to arm if the overlay hash does not match the
seed, so an unexpected "not armed" at launch is this.

## Rough edges you will notice

- **Every suppressed pickup gives one placeholder Blood Vial** on top of the
  AP check. This is deliberate and slightly distorts the vial economy.
- **A delivered item can land in the Hunter's Dream storage box** instead of
  your inventory. If AP says you received a key item and you cannot find it,
  check storage before asking for a rescue.
- **Blood Vials cannot be delivered when you hold none.** The client parks
  the delivery safely and retries once you have a stack. Buy or find one.
- **Many location names still lack a landmark.** Roughly seven in ten checks
  are named by region and item only. The tracker's Locations page and the
  spoiler log are the workaround.
- **One character per seed.** The client binds to the first save it verifies
  and refuses a different character afterward. Do not start a new character
  mid-seed.
- **DeathLink is receive-only.** Your deaths are not sent to others yet.
- **Enemy randomization writes have not been playtested at scale.** A bad
  transplant can crash a map load. Untick Randomize Enemies for a cleaner run.
- **Shop randomization is hidden.** `randomize_shops` is accepted but the
  permutation is not applied in this beta.
- **Chalice Dungeons are out of scope** entirely.
- **The apworld's Python text client is a manual fallback only.** Automatic
  checks and delivery need the native client the launcher starts.

## Verified in this beta

Worth saying, since the list above is long: Caryll rune and blood gem
delivery through the new event-award lane was confirmed in a live playtest
before release. Delivered runes equip and gems imprint. Report anything
different.

## If you get stuck: the rescue console

The native client window is also a console. Type `help` in it. Every command
that changes anything requires the word `CONFIRM`, works only on flags and
items that belong to your seed, and is written to the audit log and the
ledger so it can never double-award or move your AP receive cursor.

Named repairs for the failures this beta expects:

```
rescue
```

lists them. Then, with the game loaded into gameplay:

| command | when |
| --- | --- |
| `rescue laurence-skull CONFIRM` | you inspected the skull after Amelia, the cutscene played, and no check was sent |
| `rescue forbidden-woods-password CONFIRM` | AP says you received "Fear the Old Blood" but the Forbidden Woods gate still refuses you |
| `rescue goal CONFIRM` | you watched your seed's ending and AP did not mark you finished |

Each prints what it did. `rescue goal` is the one to be careful with: it sends
goal completion to the server, so run it only after the ending actually
played.

The general tools behind those recipes are also available to a host:
`flag FLAG` reads a seed flag, `setflag FLAG CONFIRM` sets one and sends its
check, `blocked` and `retry INDEX CONFIRM` handle parked deliveries, `give
INDEX CONFIRM` re-queues a seed item, and `export` writes
`rescue-diagnostics.json` next to the ledger for a bug report. Anything
outside the seed contract is refused rather than guessed.
