# Launcher experience: play, create, resume

The launcher should answer three questions: Which run am I playing? What is
ready? What do I do next? Technical paths and build controls should support
those answers rather than be the primary navigation.

## Implemented first slice

- **Play** accepts an existing seed and server address. The current build/launch
  action remains available, with **Connect to running game** beside it. Connect
  starts only the AP client against the verified, previously installed seed;
  changing seed requires returning to the stopped-game build/launch flow.
- **Create & host** wraps the installed Archipelago generator and local server.
  Solo players enter their name and DLC choice; experienced hosts can use a
  player YAML folder. Generated output becomes the selected seed automatically.
  Local hosting is loopback-only, with an editable port and explicit stop action.
  It does not require a user to compose terminal commands.
- Local generation requires Archipelago and the matching Bloodborne world to
  be installed. Their setup is still a first-run prerequisite, not a claim that
  the launcher now bundles the entire Archipelago distribution.
- Existing enemy options, recovery controls, and detailed diagnostics remain
  accessible. Creation has a scrolling body so it works on a short window.

## Next priorities

### 1. A run card and one context-sensitive primary action

Show player, seed, server, last played time, and save identity together. Below
that, show **Game / AP connection / Item delivery / Local server** as separate
states. A started process is not a connected client; a connected client is not
proof that delivery is ready.

Primary action follows the verified state: **Finish setup**, **Build & play**,
**Connect**, or **Resume**. Keep alternate actions visible, but do not rebuild
merely because the client disconnected. If a running game needs a different
overlay, say "Close Bloodborne to switch this seed" and preserve the selection.

### 2. Guided first-run setup

Discover candidate game/emulator/AP installations, show the selected paths and
versions, and explain ambiguous choices. Remember a successful setup. Offer an
explicit **Install matching Bloodborne world** action from the release package,
with version/hash verification and backup of an existing world, rather than a
manual hunt for an apworld file. This installer is future work.

Hide Python/source checkout settings under Advanced for ordinary packaged AP
users. Keep internal binder, manifest, cache and writer paths under diagnostics.
Offer a concise repair action for a missing prerequisite instead of a stack
trace or a generic "REFUSED" label.

### 3. Seed creation as a short wizard

First choose **Solo** or **Multiworld**. Solo: name, DLC availability, goal, then
optional game settings. Multiworld: add player YAMLs, show names/games and
validation errors before running Generate. Summarize changed options and retain
the exact input snapshot with the resulting seed.

Keep advanced options faithful to the apworld schema; do not hand-maintain a
second option catalog. Future presets should be versioned selections, with
"View all changes" so they are explainable. Recreating a seed should be an
explicit operation that never overwrites the previous run.

### 4. Hosting and joining as different flows

**Join a room** needs an address and player selection. **Host on this PC** needs
a seed and server status; fill the local address automatically only after the
host starts. Retain server logs and saves per seed. A local port already in use
should name the problem and offer another port, never connect silently to the
unrelated listener.

Later add **Host for friends** with explicit network binding, password settings,
and clear reachability diagnostics. Do not label a localhost server shareable.
Cloud/web hosting can be a separately documented route; do not upload a seed or
credentials automatically. Offer copy-address and copy-player-name actions.

### 5. Recent runs and recovery

Keep recent seeds with source ZIP, selected player, connection, generated
outputs, and diagnostic paths. Resume reuses the seed's ledger and server save.
Selecting an old run checks compatibility and installed-overlay identity before
anything starts. Expose **Open run folder**, **Back up diagnostics**, and
**Remove cached build** separately; cache deletion must not delete the receipt
ledger, AP server save, or game save.

If the game crashes, preserve the run card and offer **Reconnect after restart**
with the latest error. Save-restore reconciliation must remain explicit; never
present wiping the delivery ledger as a routine troubleshooting step.

### 6. Progress and failures with a useful next action

Use coarse stages: validating inputs, generating, building game files, starting
server, starting game, connecting, ready. Give duration and last progress, with
cancellation only where safe. Never invent completion percentages for unknown
external work. Keep raw logs a click away, automatically reveal them for errors,
and retain a concise failure summary with the affected component and remedy.

### 7. BBLauncher integration as a launch mode

Issue #192 specifies an exported seed mod with a separate companion connection.
Its file ownership and verification need implementation before calling that
mode supported. The new reconnect action is useful for a previously prepared
standalone overlay; it is not permission to adopt any third-party mods folder.

Once external activation is supported, keep the same run card: the launcher
choice changes how the game starts, not how players choose a seed or see health.
"Without Archipelago" and "unmodified vanilla" must be separate concepts when
other mods such as Intel SFX fixes remain enabled.

## Acceptance for further UI changes

Test first-time solo creation, existing online room, reconnect, multi-player ZIP
selection, source vs packaged AP installations, wrong seed, missing world,
generation cancellation, occupied local port, host exit, and saved-run resume.
Check keyboard navigation and a small window/high-DPI layout. Keep all long
operations off the UI thread, take UI variable snapshots before workers start,
and never let the hosting process disappear silently on launcher close.

Prioritize first-run setup and the run card after this slice. A broad visual
redesign should follow those state/ownership improvements, not precede them.
