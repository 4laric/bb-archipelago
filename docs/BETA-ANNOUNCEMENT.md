# Bloodborne Archipelago: beta 1

Draft announcement for the `v0.1.0-beta.1` prerelease. Post the body below
to the release page and the Archipelago Discord thread; keep this file as the
source so later betas edit one place.

---

**Bloodborne is playable in Archipelago, and we want you to break it.**

This is the first beta of Bloodborne support for Archipelago: a full-base-game
apworld, a Windows launcher, and a native client that reads checks out of the
running game and delivers items into it, under shadPS4. It needs your own dump
of `CUSA03173` (Game of the Year edition) at update 01.09, plus DarkScript3
version 3.6.3, which the launcher uses to build two event-script overlays
from your own files. No Cheat Engine, no manual item entry.

**What it does**

- 491 locations across the whole base game, from Central Yharnam to Mergo's
  Loft, including bosses, scripted interactions, and every fixed pickup. 642
  with the DLC option on.
- Items are delivered natively as you receive them. Weapons, attire, goods,
  keys, upgrade materials, and (new in this beta) Caryll runes and blood gems.
- Vanilla pickups are suppressed so a randomized location does not also give
  you its original item.
- Three goals: submit to Gehrman, refuse Gehrman, or the Moon Presence.
- Optional: enemy randomization, one-time enemy checks, alternate Hypogean
  Gaol routes, enemy drop randomization, and receive-only DeathLink.
- A tracker page with landmark names for the checks we have mapped so far.

**What has never been tested**

We would rather tell you now than have you find out at hour twenty. The
complete list is in `docs/KNOWN-LIMITATIONS.md`. The three that matter most:

1. **The Old Hunters DLC.** Generated and in logic behind `include_dlc`, and
   no one has set foot in it during a randomized game. Off by default.
2. **Endings.** Goal detection for Gehrman and the Moon Presence has never
   fired in a live session. If you finish and AP does not agree, the client
   has a `rescue goal CONFIRM` command that sends it.
3. **Laurence's Skull.** Its check and the Forbidden Woods password shuffle
   depend on a patched event file that ships in the launcher for the first
   time in this beta. In every earlier playtest it was missing, the check
   never sent, and the game handed out the password anyway. If that happens
   to you, your seed is still completable and `rescue laurence-skull CONFIRM`
   sends the stranded check.

More broadly: the furthest live playtest so far is defeating Mergo's Wet
Nurse. Everything up to there has been played with the client running;
Gehrman, the Moon Presence, and the DLC have not.

Also expect: a placeholder Blood Vial on every suppressed pickup, an
occasional delivery landing in the storage box, and location names that still
say "Blood Gem #4" instead of where it is.

**Getting stuck is a bug report, not a dead end.** The client window is a
rescue console. `help` lists the commands. Everything that changes the save
needs the word `CONFIRM`, is limited to your seed's own flags and items, and
is audited. Your host can repair a stranded check or a missing key item in
place without restarting the seed.

**What we need from you**

- The `client.log` and `rescue-diagnostics.json` from any session where
  something did not match what AP said. `docs/PLAYTESTING.md` says where they
  are and what else to include.
- If you go into the DLC, or reach an ending, tell us even when it worked.
  Those are the first data points.
- Throwaway saves. This is beta software that writes to your save file.

**Download:** the `BloodborneAPLauncher-win-x64.zip` and
`bloodborne.apworld` attached to the release. Setup takes about five minutes;
`docs/PLAYTESTING.md` walks through it.

Thanks for testing. Tell us what breaks.
