# Changelog

## Unreleased

- **A native goods grant left undetermined by a prior attempt is never
  re-armed silently.** `bb_native_delivery`'s reused-tag guard used to let
  `--expected-before` bypass its check entirely, so a tag left at `armed` or
  `interrupted` -- meaning the prior attempt's outcome was never confirmed --
  could be re-issued as long as a baseline was supplied, even though that
  baseline is sampled from the same undetermined state. This is the same
  failure shape reported in #342 for category-8 delivery tokens: "not
  currently where a fresh read expects it" is not evidence a grant failed,
  it may just be routed somewhere the read did not check (the Hunter's Dream
  storage box). The guard now refuses those tags outright regardless of
  `--expected-before`; only `--force` or a fresh `--tag` gets past it. A
  timed-out grant also now prints a hint pointing at the storage box, since a
  `?GoodsName?` item there is the most likely explanation for a category-8
  token stuck pending. The bridge event itself (`common.emevd`) already
  waits on the storage box and drains duplicate copies of a token before
  awarding, landed in #344.

- **Report a Bad Enemy.** The launcher keeps the exact enemy plan each seed
  was built from, and a new recovery action (or `python -m bb_launcher
  enemy-report`) turns it into a paste-ready report: seed, slot, cache key,
  every swap in the area you name, and, if you saw an echo reward, the
  enemies whose reward is nearest first. Builds from before this need one
  Rebuild. (bb-archipelago#321)
- **Stress-test enemy seeds.** An enemy seed such as `stress:size-up:m24_01`
  or `stress:family=c4060:m24_01` pushes every swap in one area to the limit
  of a single compatibility rule so playtests can falsify it directly.
  Ordinary seeds are unchanged.

- **Fixed: Full Item Pool off could not generate.** With the option turned off
  the reduced pool left out the keys that gate Castle Cainhurst, Lecture
  Building 1F, Nightmare Frontier and Upper Cathedral Ward, while the seed
  still placed the 105 checks behind them. Generation aborted with a FillError
  at the default accessibility, and on `accessibility: minimal` it produced a
  seed with 105 checks nobody could ever send. The reduced pool now carries
  every gate the seeded regions need. (review finding W4)

- **Fixed: sixteen checks that could never be sent.** Sixteen New Game Plus
  "replacement" item lots shipped as ordinary checks sitting on a corpse that
  already had a check on it, in Hemwick, the Forbidden Woods, Yahar'gul,
  Nightmare of Mensis and the Nightmare Frontier. On a first playthrough the
  corpse gives the other item, so the check never fired, and in a multiworld
  another player's progression item could land there and be lost. Those
  sixteen are no longer checks; every corpse keeps the check it always had.
  (review finding W5)

- **Fixed: a rune-and-gem-only seed delivered nothing.** A seed whose only
  param edit was the category-8 award table got a freshly composed binder but
  was handed the bundled build manifest, which names the un-composed one. The
  client's hash check failed and nothing was ever delivered, behind a
  successful launch dialog. Both the binder and its witness now follow one
  predicate. (review W2)

- **Fixed: Launch Vanilla always refused.** Every generated plan pins the AP
  client with the client runtime placeholders, and a vanilla launch has none
  of those files, so the button refused on every packaged setup and left the
  overlay active. A vanilla launch now drops the Archipelago components and
  starts the game. (review W3)

- **Fixed: Check Setup warned that item delivery was impossible.** Generated
  plans never carry a Cheat Engine bridge by design, so "no Cheat Engine
  bridge in the launch plan" fired on every healthy setup with a remedy that
  could not change it. Check Setup now reports the native lane: it passes when
  the plan pins the AP client. (review W8)

- **Fixed: DLC blood gems in a non-DLC seed.** Eleven Research Hall and
  Fishing Hamlet category-8 blood gems escaped the DLC gate, so a seed
  generated with `include_dlc: false` still placed them on base-game checks
  and still built their Old Hunters award lots. A category-8 item's DLC
  membership is now derived from the region of the fixed location it was
  generated from, so future generated rows are gated automatically.
  (review W13)
- **Fixed: DLC weapons in a base-game-only starting gift.** The randomized
  Hunter's Dream gift lineup sampled every weapon and never read Include The
  Old Hunters Gear, so a run that had disabled DLC equipment could still
  start with the Boom Hammer or the Piercing Rifle. The gift now honours the
  same rule the item pool applies to weapons. (review W11)
- **Fixed: a phantom attire item.** The expanded catalog listed "Surgical Long
  Gloves (White)" (protector 292000), which does not exist in the game; the
  White Church set wears the black gloves. It no longer enters any pool.
  Its network id is kept so other attire ids stay stable.

- **Fixed: one rune or gem delivery handed out several.** The AP award lots
  were numbered consecutively, and Bloodborne awards consecutive lot ids as
  one group (the way a vanilla armour set drops from one corpse), so a
  single delivery could give five runes and gems. Award lots now step by
  ten like every vanilla lot. Seeds generated before this carry the old
  numbering and need regenerating.
- **Randomized starting gifts are always visibly randomized.** A seed could
  draw exactly the vanilla Hunter Pistol and Blunderbuss (one seed did), which
  looked like the option had turned itself off. A hand now never reproduces
  its vanilla set, and the Dream's firearm rows draw only from firearms, not
  the torch or the shields the expanded pool added.
- **The client is pinned by commit.** `packaging/client-ref.txt` names the
  `from-software-archipelago-clients` commit every release and playtest
  bundle builds, the built client's version stamp is checked against it, and
  the package manifest records it. Beta 2 shipped an apworld and a client
  that had never been built together; a pin bump is now a reviewed change
  the packaging smoke runs against first.
- **The launcher's Troubleshooting tab scrolls** instead of clipping its
  lower rows on a short display.
- **Packaging smoke checks in CI.** After every release and main-branch
  package build, the frozen launcher runs `--self-check` (imports every
  apworld table, builds the widest seed contract, and confirms each native
  tool is beside it) and the built client runs `--check-contract` against
  the contract the built apworld emits. Beta 2 shipped with both of those
  broken; neither can now reach a tag.

- **Fixed: the launcher refused every seed with a missing `attire_additions.tsv`.**
  The packaged launcher bundled a hand-maintained list of apworld tables and
  the newest one was not on it. The build now bundles every table in the
  apworld directory, and a test checks that each file the apworld opens
  exists.

- **Rune and gem deliveries no longer stall when their token lands in the
  storage box.** The bridge event now waits for the token including the box,
  consumes every copy of it before awarding once, and only then raises its
  acknowledgement. A duplicate token can no longer become a duplicate rune,
  and a boxed token is consumed without the player withdrawing it, provided
  the game's removal reaches the box; if it does not, the event waits for the
  withdrawal instead of awarding twice (#342).

- **Caryll rune and blood gem chests no longer hand out their vanilla item.**
  With rune and gem delivery through the event-award lane confirmed live, all
  58 category-8 pickups are suppressed like every other check, and the 22
  fixed Caryll rune locations join the seeded pool. Base-game seeds grow from
  495 to 517 locations, full seeds from 646 to 668. The suppression plan and
  the CI-reproduced binder hash move with it; players get the rebuilt binder
  from the launcher package as usual.

- **The per-check bonus item is now seed-owned.** Slot data publishes
  `sustain_item` (Quicksilver Bullets, goods 900) from the apworld's runtime
  bindings, so the client no longer hardcodes it. The beta 1 client hardcoded
  goods 1100, the Antidote, which is why players received an Antidote after
  every check; the client fix is in the client repository.

- **DarkScript3 is no longer required.** The launcher now writes the two
  event overlays (the Laurence's Skull / Hunter Chief Emblem edits in
  `m24_00_00_00.emevd.dcx` and the rune and gem award bridge in
  `common.emevd.dcx`) with a bundled native tool, `BBEventWriter`, that edits
  the licensed files instruction by instruction. Players no longer download a
  compiler or the .NET 6 runtime. Every untouched event is now byte-identical
  to the player's original file; the compiler path re-encoded dozens of
  unrelated vanilla events on every build. The DarkScript3 field is gone from
  the launcher and the `darkscript` setting is ignored.

- **Named rescue recipes in the client console.** `rescue` lists them;
  `rescue laurence-skull CONFIRM` sends a stranded Grand Cathedral altar
  check, `rescue forbidden-woods-password CONFIRM` rewrites the shuffled
  password flag, and `rescue goal CONFIRM` sends goal completion after an
  ending the client did not detect. Each reuses the existing audited
  `setflag` and `give` primitives, validates every step against the seed
  contract before writing anything, and never moves the AP receive cursor.

- **A player-facing known-limitations page**, `docs/KNOWN-LIMITATIONS.md`,
  states plainly what has never been verified live: the Old Hunters DLC, all
  three endings' goal detection, and the Laurence's Skull check and password
  suppression. It also records the playtest frontier (Mergo's Wet Nurse).

- Seed generation now emits an inert, collision-checked plan for truthful
  in-game names on useful and progression pickups. A packaged build tool can
  clone the non-modal Blood Vial goods shape, repoint the corresponding lots,
  and add bounded `Item (player)` FMG names. The writer is deliberately double
  gated and the plans remain disabled until a live test proves that Bloodborne
  reads the replacement `item.msgbnd` and uses the non-blocking popup path.

- Replace seven broad Cathedral Ward tracker labels with wiki-backed landmarks
  joined to their exact item-lot flags and MSB treasure placements.

- Completed the Bath Messenger gate audit for shop randomization: all ten
  `qwcId` groups now have badge/goods/stock witnesses and an executable
  fail-closed readiness check. The check confirms the feature is not yet safe
  to expose because eight required badges are absent from the AP world model.

* Add the independent `death_link_amnesty` YAML option. It is seed-owned,
  defaults to zero, and tells future outbound DeathLink clients how many local
  deaths to forgive per cycle without changing incoming DeathLinks.

Player-visible changes to Bloodborne Archipelago are recorded here. The project
uses semantic versioning for the apworld contract; unreleased changes accumulate
under `Unreleased` and move into a dated version section when released.

## Unreleased

- **All ten ordinary Bath Messenger badges now exist as randomized items.**
  Eileen, Djura, Alfred, and Annalise's badge awards are checks, every reviewed
  natural badge lot is suppressed, and the shop-randomization pool-safety gate
  is green. The actual shop permutation remains hidden until the launcher can
  compose it into the seed-owned binder and cache identity atomically.

- **Upper Cathedral Ward's ordinary pickups are now randomized.** Nineteen
  weapons, attire pieces, consumables, and upgrade-material pickups join its
  existing boss and scripted checks. Its natural Blood Gem remains intact
  while also reporting an AP check.

- **Enemy transplant scaling now has a deterministic offline plan, still off
  by default.** An explicit experimental flag derives Bloodborne's 13-rung
  native area curve from bundled params, emits collision-checked NpcParam and
  echo-neutral SpEffect clone requests, clamps multipliers, and records every
  unknown-tier or full-effect-slot skip. The game-file writer is intentionally
  not enabled yet; this is reviewable scaffolding for the construction canary.

- **The tracker now has a complete Locations reference page and its first
  wiki-backed landmark upgrades.** Central Yharnam's Saw Spear, Saw Hunter
  Badge, Torch, Hunter Set, and the tightly clustered Plaza-gate pickups now
  name recognizable places instead of the broad `bridge side` / `sewer side`
  halves. Old Yharnam's first Coldblood Dew (2) now points to the bell-tower
  ladder off the right path from the lamp. Exact flags, lots, map parts,
  coordinates, sources, and confidence are retained in a reviewable evidence
  ledger.

- **Hypogean Gaol and Darkbeast Paarl can join the progression graph.** The
  new `alternate_hypogean_gaol_routes` YAML option is off by default. When on,
  it models post-BSB Snatcher abduction, the independent Blood Moon entrance,
  Paarl's check, and the rear Old Yharnam gate. The enemizer explicitly
  preserves a Cathedral Ward Snatcher so early access never rests on chance.

### Changed

- Cleric Beast's Sword Hunter Badge, Gehrman's Old Hunter Badge, and Vicar
  Amelia's Gold Pendant are now shuffled category-4 items. Their reviewed
  natural award rows are suppressed, so shop unlocks and Pendant conversion
  follow AP receipt. Pthumeru, Ailing Loran, and Isz chalices remain vanilla
  while Chalice Dungeons are out of scope.

- **DeathLink now has an opt-in receive-only YAML option.** Seeds can enable
  `death_link`; the native client then joins the DeathLink channel and accepts
  incoming linked deaths. Sending remains off until the live player-death
  signal is validated, so ordinary deaths cannot produce false links.

- **The YAML wizard now names each ending's actual completion trigger.** Goal
  choices display as `Submit to Gehrman (Mergo's Wet Nurse)`, `Refuse Gehrman
  (Gehrman)`, and `Moon Presence (Three Umbilical Cords)`. Existing YAML keys
  are unchanged.
- **Extracting a new playtest build no longer leaves the launcher pointing at
  yesterday's deleted suppression manifest.** When either saved suppression
  path has vanished, startup now replaces the binder and manifest together
  with the verified pair shipped under the current package's `work` directory.
  A valid operator-selected pair is still preserved.
- **Bosses no longer leak duplicate vanilla payouts alongside their AP checks.**
  Twenty reviewed award lots are now suppressed, including every natural source
  of the shuffled boss badges and Gold Pendant plus the weapon, material, and
  Insight rewards attached to later bosses. The three out-of-scope chalices
  remain vanilla.
- **Advanced enemy controls now say what is experimental about them.** Tier
  mixing warns that enemy scaling is not normalized, while locomotion
  preservation warns that its roster tags are incomplete. Offline regression
  fixtures now pin both modes and verify deterministic plans independently of
  the default 308-placement policy.
- **The Lunarium Key is now a real progression gate.** Its Byrgenwerth attic
  pickup is randomized, the vanilla award is suppressed, and Rom's Moonside
  Lake arena requires receiving the shuffled key. This closes the missing
  vanilla gate that previously made Rom free immediately after Shadows.
- **Overlay caching now follows the bytes it builds.** Different AP players
  reuse an identical verified overlay when their suppression and enemizer
  inputs match, while changing the suppression binder necessarily creates a
  new cache entry. Seed/slot identity remains attached to the active overlay
  and its isolated delivery ledger; it no longer causes duplicate builds or
  hides a replaced binder behind a stale cache hit.
- **The Old Hunters is selectable per seed.** Set `include_dlc: true` in the
  player YAML to add its regions, bosses, fixed pickups, and five DLC-only
  progression items. It defaults off so players without the DLC receive a
  complete base-game seed with no checks or required items in DLC content.
- **Seeds can select any of Bloodborne's three endings.** The `goal` YAML
  option accepts `submit_to_gehrman` (Mergo's Wet Nurse), `refuse_gehrman`
  (defeat Gehrman), or the default `moon_presence` (receive any three of four
  shuffled Third Umbilical Cords, then defeat Gehrman and Moon Presence).
- **The launcher now keeps its plumbing out of the normal setup flow.** The
  Setup tab contains the seed, game, shadPS4, server, and player identity;
  cache, state, log, suppression, MapStudio, and operator paths live on their
  relevant Enemy randomization or Troubleshooting tabs. The launcher generates
  its hash-pinned process plan automatically before launch, saves setup as part
  of every action, and groups recovery controls under Troubleshooting. The old
  Save Setup and Generate Launch Plan chores are gone.
  Player identity is now a read-only choice populated from the seed rather
  than a free-text trap: single-player seeds select themselves, and archives
  with several Bloodborne slots present only those valid names. A compact
  seed/player/runtime summary and automatic readiness refresh make a wrong
  selection visible before launch. Single-slot seeds now hide the redundant
  player selector, uncommon enemy controls are collapsed by default, and the
  launch button names any missing setup pieces instead of failing later.
- **One check that no first playthrough could ever complete is gone.** Central
  Yharnam's `Bold Hunter's Mark` was a corpse that only spawns on NG+ — the
  param names it "treasure corpse 19, second playthrough onward", and it is the
  NG+ substitute for the Saw Hunter Badge corpse at the same spot. Seeds placed
  a check on it anyway, and the tracker called it in logic, so a completionist
  run had one unreachable filler item. Seeds are now 166 locations instead of
  167. If you are playing on NG+, the pickup still exists and still hands out a
  placeholder rather than a vanilla Bold Hunter's Mark, so it cannot hand you
  anything the multiworld does not know about. Existing seeds are unaffected in
  the sense that nothing was renumbered: the location's network id is retired in
  place and will never be reused.
- **Location names now point at a landmark, not just a region and an item.**
  Two playtesters in one day could not locate their checks: one hunted
  `Central Yharnam - Blood Stone Shard x2` with a video guide open and still
  needed operator support, and the other asked outright for names that say
  where the item is. 182 of the 678 tabled names carry a parenthetical hint, among
  them `Central Yharnam - Blood Stone Shard x2 (sewer channel beam)`,
  `Central Yharnam - Coldblood Dew (1) #1 (clinic backstreets)` and
  `Central Yharnam - Blood Stone Shard #8 (bridge side)`. Hints come from the
  developers' own per-map area tags, translated through a committed and
  calibrated vocabulary, from MSB chest and placement data, or -- for a
  handful of spots -- by hand with the evidence recorded in the row's
  `basis`. Existing `#N` disambiguators are unchanged on purpose, so tracker
  packs and spoiler logs keep working; the datapackage is regenerated per
  seed, so seeds already in flight are unaffected. The remaining 496 names
  carry no hint yet, which is honest rather than unfinished. See
  docs/LOCATION-NAMING.md.

- **Native delivery now constructs armor with the game's category-1 allocator.**
  A live Charred Hunter Garb canary arrived as a proper instance, appeared in
  the inventory, and equipped successfully. Unsupported armor remains blocked
  behind the exact-row research allowlist until its catalog binding is added.
  Category-8 blood gems remain refused: live tests proved that an ItemLot gem
  row is a generation recipe, not a finished runtime descriptor, and both a
  bare gem allocation and direct insertion produced invisible records.

- **Client-delivered weapons are now real, fully repaired weapon instances.**
  The native category-0 path now allocates a weapon through the game's equipment
  registry instead of inserting its catalog descriptor directly, then initializes
  the new instance from `EquipParamWeapon.durabilityMax` before granting it. Live
  playtesting confirmed a delivered Beast Claw at 180/180 durability while the
  save's existing weapons remained intact.
- **Weapon stat requirements can now be removed.** The default-on
  `remove_weapon_requirements` YAML option clears Strength, Skill, Bloodtinge,
  and Arcane requirements across all eleven reinforcement rows for every
  base-game player weapon. Uncanny families are included when their option is
  enabled. Attribute scaling, bonuses, damage, and durability are untouched.

- **Starting weapons can now be randomized by seed.** The default-on
  `randomize_starting_weapons` YAML option deterministically replaces the
  Hunter's Dream gifts with three unique base-game trick weapons and two
  unique base-game firearms. These gifts are independent of the shuffled item
  pool. The launcher writes the choices into native `ShopLineupParam` rows
  2000–2002 and 2010–2011, preserving Bloodborne's previews, one-choice event
  flags, inventory insertion, and full durability. Turning the option off
  leaves the vanilla Saw Cleaver/Hunter Axe/Threaded Cane and firearm choices
  untouched.

- **The pool is a real Bloodborne pool now: every base-game weapon, and filler
  with variety in it (#207 wave 1).** All fifteen base-game trick weapons (Saw
  Cleaver, Saw Spear, Hunter Axe, Threaded Cane, Kirkhammer, Ludwig's Holy
  Blade, Rifle Spear, Stake Driver, Beast Claw, Blade of Mercy, Burial Blade,
  Chikage, Reiterpallasch, Tonitrus, Logarius' Wheel) and the five base-game
  firearms (Hunter Pistol, Hunter Blunderbuss, Repeating Pistol, Ludwig's
  Rifle, Cannon) are now `useful` items in the default pool — no option, no
  YAML change. The Old Hunters weapons stay out until the DLC is modelled, and
  the Torch stays out because it is a standing negative canary. On the goods
  side, ten more consumables (Antidote, Sedatives, Beast Blood Pellet, Blue
  Elixir, Poison Knife, Throwing Knife, Fire Paper, Bolt Paper, Bone Marrow
  Ash, Lead Elixir) join the filler set, and the filler top-up is now a
  weighted mix seeded by the multiworld seed instead of one cycled list — the
  same seed gives the same pool, a different seed gives a different
  arrangement, and Blood Vial is still the heaviest share. Seed size is
  unchanged: the pool still holds exactly as many items as the seed has
  locations, and a seed too small for its one-each items sheds Uncanny
  variants first, then the useful tail, never a progression key.

  Weapon ids are `EquipParamWeapon` rows agreed on by two independent
  community corpora and carry `param_id_inferred` until a live delivery is
  witnessed. The goods ids are read out of the repo's own bundled
  `params/EquipParamGoods.csv`, which is the authoritative category-4 source.

- **Uncanny weapon variants can now join the pool (#205).** A new opt-in YAML
  option, **Uncanny Weapon Variants** (`uncanny_weapons`, off by default), adds
  the Uncanny version of every weapon your pool already places — with #207
  wave 1 that is one variant per base-game trick weapon (firearms have no
  Uncanny rows in the game's params, so they get none). Uncanny weapons
  are normally Chalice-dungeon-only and differ from their base weapon in their
  blood-gem slot layout, so a second find is a build choice rather than a
  duplicate. They displace filler, never checks: the seed keeps exactly as many
  items as it has locations, and a pool with no filler left to displace simply
  places fewer of them. Their runtime ids are derived from community
  `EquipParamWeapon` documentation (Uncanny = base weapon id + 10000) and are
  marked `param_id_inferred` until a first live delivery is witnessed.

- **Where a delivered item lands is now a question with an experiment behind it
  (#202, clients#445).** On the native stack some items arrive in held inventory and
  some in the Hunter's Dream storage box, and a progression key quietly placed in
  storage leaves a player stuck in practice even though delivery worked. The
  developer tool grows a guided `probe-storage` session that forces each case
  deliberately — a normal add, a deliberate at-cap overflow, a unique item
  delivered idle, a unique item right after an overflow, and deliveries in the
  post-boss and menu states — and renders a verdict the operator pastes into the
  issue. No player-facing behaviour changes yet: this is the measurement the
  console wording and any pacing fix have to be built on.

- **The release bundle's suppression binder finally matches real installs (#200).**
  The inputs bundle's `parambnd/gameparam.parambnd.dcx` was byte-different from
  the patch layer installed games carry, so every zip-shipped binder failed the
  installed-gameparam check and manually built binders had to be sent alongside
  releases. The bundle now carries the installed patch-layer bytes exactly, and
  the binder CI check pins the whole lineage: bundle source, manifest source,
  and the binder output CI reproduces under the pinned toolchain (the hand-built binder differed only by SoulsFormatsNEXT version; one live run on a CI binder is owed). Drift in any of the
  three reds the PR that introduces it.

### Fixed

- **The launcher's tabs are legible again.** The notebook added with the tabbed
  layout inherited ttk's stock light theming, so on the dark launcher the
  selected tab drew as an empty dashed rectangle and the unselected one as a
  grey ghost. `TNotebook` and `TNotebook.Tab` now use the same palette as every
  other widget, with a gold selected label and no dashed focus ring.

### Changed

- **The Doctor names the usual cause of a modified gameparam.** Both
  installed-gameparam failures now say that a pre-modded repack (installs named
  like "Bloodborne (feat. shadPS4)") ships an already-modified patch gameparam,
  point at restoring a clean 01.09 patch layer, and note that the operator
  `--allow-suppression-mismatch` override reverts whatever the repack's param
  edits did.

- **Activation no longer refuses over the spelling of `MapStudio`.** A managed
  overlay could be refused with the same map file listed as both `missing`
  (spelled `dvdroot_ps4/map/mapstudio/...`) and `unowned` (spelled
  `dvdroot_ps4/map/MapStudio/...`) -- one file, two spellings. Windows folds
  the two into one directory; ownership verification compared the manifest's
  relative paths against the disk case-sensitively, so whichever spelling the
  manifest held showed up as gone and the disk's spelling showed up as an
  intruder. Overlay paths are now recorded in one canonical spelling
  (`dvdroot_ps4/map/MapStudio/`, `dvdroot_ps4/param/gameparam/...`) whatever
  case the source directory or the player's mods tree used, *and* verification
  compares case-insensitively -- the same rule the user-merge conflict check
  already used -- so an overlay activated before this fix verifies against its
  own disk tree without being re-activated. Two files that really do differ
  only by case are still refused, and a genuinely missing or genuinely unowned
  file is refused exactly as before.

### Added

- **The launcher takes the Archipelago multiworld zip your host sent you.**
  Generation emits one `AP_<seed>.zip` for the whole multiworld and hosts hand
  players that zip; the launcher used to accept only the per-slot
  `.bbseed.json` extracted from it, an unzip-and-pick step no other
  Archipelago game asks for. The field is now **AP seed file (.zip or
  .bbseed.json)** and takes either. Given a zip, the launcher reads each
  Bloodborne request inside it and picks yours by the `player_name` in the
  request itself, not by filename: a zip with exactly one Bloodborne slot is
  used straight away and fills in your AP player name for you, a zip with
  several requires the player-name field and refuses to guess between them,
  and a zip with none says so by name. The chosen member is extracted once,
  under `seed-requests` in the launcher state folder and keyed by content, so
  re-selecting the same zip reuses the same file. The Doctor takes the zip
  too, and its seed-file line names both the zip and the member it chose
  (#194).

- **An explicit operator override for suppression binder hash mismatches.**
  Host-side iteration constantly puts the seed, the suppression binder and the
  installed gameparam one step out of step with each other, and every skew cost
  a full refusal. **Allow suppression binder mismatch** in the launcher, and
  `--allow-suppression-mismatch` on `python -m bb_launcher doctor`, downgrade
  exactly two comparisons — binder plan versus the seed's plan hash, and binder
  source versus the installed gameparam — from refusals to loud warnings, each
  printing what was expected, what was found, and the knob that bypassed it.
  Doctor reports them as `WARN` naming the override instead of failing, and the
  activated overlay records the bypass in its ownership manifest so a later bug
  report is attributable. The override is per-invocation and is never saved
  with the setup; without it every refusal is exactly what it was before. It is
  for hosts running playtests, not for players: a mismatched binder suppresses
  the wrong grants and the run diverges from the seed silently (#183).

- **The client's console window shows live output again, and still leaves a
  log behind.** Capturing the client's output into `client.log` (#171) had
  blanked the console window you watch to see what arrived. The client now
  keeps that console *itself* and writes the log *itself*: the launcher hands
  it `--log-file` pointing at this session's `client.log` and then stays
  entirely out of its output path — no redirect, no relay. Every line goes to
  both places at once, flushed as it is printed, so a crash cannot swallow the
  last thing it said. Nothing about sending diagnostics changes: `client.log`
  is still the file to send, still one `=== SESSION START ... ===` block per
  launch, and the early-exit dialog still quotes this session's tail. shadPS4's
  output is captured by the launcher exactly as before (#175). Requires the
  matching client build, which a generated plan pins by SHA-256, so the plan
  and the executable always travel together (#181, with
  fromsoftware-archipelago-clients#425).

- **shadPS4 is now launched by path, so your game folder is what decides which
  game boots.** The launch plan used to invoke `shadPS4.exe CUSA03173` — a bare
  game ID the emulator can only resolve against its *own* library config. On an
  emulator copy that had never been opened and pointed at a game directory,
  that config is empty, so the launcher's "shadPS4 game folder" field was
  cosmetic and shadPS4 exited immediately with `Game ID or file path not found:
  CUSA03173`, even for a player whose setup was completely correct. Generated
  plans now carry a `{game_path}` placeholder that resolves at launch to the
  `CUSA03173` directory inside your configured game root, so a freshly unzipped
  shadPS4 works with no in-emulator setup at all. Update and mods overlays are
  unaffected — shadPS4 derives those from the booted game folder, not from its
  library config (#177).

- **A launch plan generated before that change is caught and named.** Existing
  plans are never silently rewritten, so the Doctor reports a `launch plan game
  argument` FAIL with the fix ("Generate Launch Plan" again), and every launch
  path refuses the stale plan up front rather than spending a build and dying
  inside the emulator (#177).

- **The Doctor now checks the selected shadPS4's version.** It used to accept
  any file named `shadPS4.exe`; a playtester passed every gate with the 0.16.0
  copy bundled inside the third-party BBLauncher tool and only found out at
  runtime. The version resource is read from the executable and anything other
  than the supported build fails, with a remedy that names 0.18.0 and warns
  about that bundled copy specifically. On a build with no readable version
  resource the check reports SKIP rather than guessing (#177).

- **An early-exit dialog now names the component that actually stopped, and
  shadPS4's output is captured too.** When shadPS4 quit immediately after
  launch, the dialog was still titled "Bloodborne AP client stopped" and had no
  log to show, because output capture was attached to the AP client alone. The
  title and body now come from the process that exited ("shadPS4 stopped" /
  "shadPS4 exited with exit code 1 immediately after launch."), and shadPS4's
  stdout and stderr are appended to `shadps4.log` beside `client.log` in the
  session folder, using the same per-launch `=== SESSION START ... ===` header
  and bounded tail. An emulator boot crash -- for example a user mod that
  shadPS4 refuses -- now carries its own evidence (#175).

- **Mods that could never load are no longer reported as merged.** Mods
  normally download as one folder per mod with `dvdroot_ps4` inside; dropping
  those folders straight into `CUSA03173-mods-user` produced overlay paths
  shadPS4 never reads, and the launcher counted them as merged, so the mods
  silently did nothing. Any user file whose path does not start with
  `dvdroot_ps4/` is now left out (reason `dead-path`), and both the Doctor's
  `user mods` line and the launch progress log name each wrapper folder, how
  many files it lost, and the fix: move the contents of that folder up one
  level (#173).

- **Slice-3 flag claims are now traced instruction by instruction, and two
  citations were wrong.** Cathedral Ward and Old Yharnam shipped with no live
  witness, so every detection flag there was a static claim. All 121 of them --
  115 pickups plus the six scripted checks -- are audited against the committed
  game corpus in `research/validation/slice3_witness_audit.tsv`, and the answer
  matters for what a player can trust: 116 are complete from named sources, and
  the five boss/interaction flags share one gap that no corpus can close (the
  game never writes them with an instruction; the engine sets them when the
  event ends), which the two flags slice 1 already shipped with have too. No
  slice-3 flag can be cleared by any of the 279 resolved OFF ranges, and each
  one has exactly one placed item lot, so no two checks collapse onto one flag.
  Two binding source references pointed at code that *reads* the flag rather
  than the event that owns it and are corrected. `docs/SLICE3-WITNESS-PASS.md`
  carries the verdicts and the owner checklist for the live session that is
  still owed.
- **The launcher no longer starts Cheat Engine, and Cheat Engine is no longer
  required.** Item delivery is the client's native path, and that is now the
  client's default; a generated launch plan has exactly two children, shadPS4
  and the AP client. Cheat Engine is only involved if your host explicitly
  tells you to restart the client with `--delivery=ce-bridge` and walks you
  through opening it by hand -- worth avoiding, because the bridge can report a
  whole backlog of items as delivered when none of them actually arrived, and
  those items are lost for the run (#163). If the client stops with a message
  about an unrecognized or unvalidated game build, nothing was written: send
  the exact console text to your host rather than switching lanes yourself
  (#153).
- **A client that stops at startup now says why.** The AP client's output is
  appended to `client.log` in the session folder, beside `ledger.json`, with a
  dated `=== SESSION START ===` header per launch, and the launcher watches the
  components it started for ten seconds. If one stops in that window, you get
  an error dialog with its exit code and what it printed, instead of the
  success popup -- previously the client's console closed with it and the
  message was lost (#171). **Open Diagnostics** now finds `client.log` too.

- **The `enemizer` YAML option is gone.** Enemization never affected
  generation -- no logic, pool, or region read it -- and the launcher's
  Randomize Enemies toggle has always been the authority at launch time. The
  option's last real function, gating the seed request file, was removed with
  the seed-request separation, so the seed contract no longer carries it: slot
  data and `.bbseed.json` requests omit the key, and the planner CLI no longer
  refuses a request that carried `enemizer: false`. Old YAMLs that still set
  `enemizer` keep generating (Archipelago ignores unknown options with a
  warning).
- **Every slot now gets a seed request file, enemizer on or off.** Generation
  drops `<seed>_P<n>_<name>.bbseed.json` beside the seed zip for every
  Bloodborne slot. Previously the file was only written when the `enemizer`
  option was on, and it is the launcher's seed identity document -- a seed
  generated with `enemizer: false` could not use Randomize & Launch at all
  (#149). Whether enemies are actually randomized remains a launch-time
  choice in the launcher. Requests from older seeds (`.bbenemizer.json`,
  `bb-enemizer-request-v1`) are still accepted everywhere.

- **The Cheat-Engine-free installer commits its detours atomically (developer
  tooling, not player-facing).** The native-delivery prototype installs by
  overwriting seven live instruction bytes at each of two hook sites with an
  `E9` detour. The heartbeat hook runs every frame, so a guest thread could be
  mid-instruction inside the window at the moment of the write and resume into a
  half-written detour -- a native crash no readback can catch. The installer now
  suspends every guest thread, checks each thread's instruction pointer against
  both seven-byte windows, writes both detours under a single suspend only when
  every pointer is clear, and resumes; if a bounded retry budget is exhausted it
  aborts having written no detour (the caves alone are harmless). The live
  suspend/RIP-read primitive is isolated behind an injectable seam and was
  validated against the game on 2026-08-24 (owner validation checklist item 5a):
  both detours went in under one live suspend and the game kept running. The
  protocol, ordering, nudge loop, fail-closed abort, and no-leaked-suspend
  invariant are unit tested against a fake thread controller. Cheat Engine
  remains the shipping delivery path. See `docs/INSTALL-ATOMICITY.md`.

- **The launcher refuses to start when Cheat Engine is already open (#137).**
  A playtester found that the launch plan's Cheat Engine step did not arm the
  grant table -- he had to start the script by hand, and until he did, his
  checks reached the server while nothing he was owed came back. When Cheat
  Engine is already running, Windows hands the grant table to that window
  instead of the one the launcher starts, and that window never arms the
  bridge. The launcher now stops before it starts anything, names the Cheat
  Engine window it found, and tells you to close it and press Launch again;
  the Doctor reports the same condition as a failure instead of a warning, its
  "item grants" line now says whether the grant table has actually reported,
  and the post-launch warning that grants never armed is written into the
  launcher log as well as its popup, so the remedy survives dismissing it. A
  launch plan without a Cheat Engine step is unaffected. The underlying cause
  of the original report is still unconfirmed; this closes the degraded path
  either way.

- **Your own mods can run alongside the randomizer, in `CUSA03173-mods-user`
  (#134).** The launcher owns `CUSA03173-mods` outright and rebuilds it on every
  launch, so mods put there kept vanishing into `.CUSA03173-mods.bb-ap-previous-...`
  folders — the transaction working as designed, and indistinguishable from data
  loss. There is now a supported folder for your content: make
  `CUSA03173-mods-user` next to `CUSA03173`, lay your mods out inside it the way
  they ship, and the launcher merges them into the overlay on every launch. It
  only ever reads that folder: nothing in it is renamed, moved, or deleted by
  launching, restoring, or Launch Vanilla. The randomizer's own files always
  win — a mod's `gameparam.parambnd.dcx`, or a MapStudio map an enemy-randomized
  seed also uses, is left out rather than allowed to break your checks — and
  every left-out file is named, with its reason, on the Doctor's new `user mods`
  line. Nothing is merged silently and nothing is dropped silently. If your mods
  are already sitting in a quarantine folder, move them into
  `CUSA03173-mods-user` and they come back.

- **The Oedon Tomb Key is shuffled, so a seed no longer opens in go-mode.**
  Vanilla hands you the key on Father Gascoigne's corpse, and the door out of
  the Tomb of Oedon is the only way into Cathedral Ward — which meant every one
  of a slice-3 seed's 167 checks was reachable from the start and nothing you
  found ever opened anything. The key is now an Archipelago progression item,
  placed like any other and guaranteed to be in every pool. **Central Yharnam
  is a real sphere 0**: 48 checks are open when you wake up, and the other 119
  — all of Cathedral Ward, Old Yharnam, the Grand Cathedral, and the
  Blood-starved Beast goal — wait behind the key. Gascoigne is still a check
  and still opens his own door; he just no longer hands you the key through it.

- **Save-restore and character-switch reconciliation is documented as shipped (#77).** The native client keys each delivery receipt to a `seed_name:slot` ledger that now carries a per-slot save watermark: a save restored to an earlier state re-issues exactly the erased deliveries, a lost ledger adopts the save's cursor without re-granting, and switching to another character is refused rather than mixing two inventories -- every shape has one defined outcome and no outcome can duplicate or silently drop an acknowledged item. Automatic restore detection still waits on the live watermark address (#56); until then an operator confirms a restore with the `bb-restored` command. `docs/SAVE-RECONCILIATION.md` now records the implemented status, its evidence label (mock-tested, not live-validated), and the owner game-session checklist for the remaining live facts.

- **Slice 3 — Cathedral Ward, Old Yharnam, and the Blood-starved Beast.** The
  playable area is no longer Central Yharnam alone. A seed now covers Central
  Yharnam, Cathedral Ward, Old Yharnam and the Grand Cathedral: **168 checks**
  (up from 51), of which 113 are new Cathedral Ward and Old Yharnam pickups
  taken from the mined location catalog. The **Blood-starved Beast is the new
  goal**; Vicar Amelia, the Laurence's-skull altar prompt, and the Radiant
  Sword Hunter Badge join the seeded checks. Every new check keeps the
  acquisition flag from its own ItemLotParam row, and every new network id was
  appended to `ids.tsv` — no already-published id moved, so seeds generated
  before this change keep their meaning.

- **The Hunter Chief Emblem now actually gates something.** The Grand Cathedral
  used to be modelled as "emblem OR Blood-starved Beast", which meant the
  emblem decided nothing: the Beast is free to reach. The two routes are now
  two separate edges, as they are in the game — the emblem opens the plaza gate
  directly, and the Healing Church Workshop reaches the same plaza the long way
  round. Slice 3 does not include the workshop, so in a slice-3 seed the emblem
  is the only way to the Grand Cathedral's checks, and it is guaranteed to be
  placed in every pool.

### Changed

- **Rebuild the suppression binder again.** The canonical plan grew from 178
  edits to **179** — the new one replaces the key Gascoigne drops with the Blood
  Vial placeholder, so the vanilla key cannot satisfy its own randomized
  placement — and the plan's SHA-256 changed with it. A binder built for any
  earlier plan no longer matches the seed and the native client will stay
  disarmed until you rebuild. Note that `build.ps1` keeps
  `work\vanilla-suppression-build` when it already exists: **delete that
  directory first**, or the rebuild reinstalls the stale binder. Row ids and
  acquisition flags are preserved exactly, as before — including this row's
  absence of one.

- **Playtesters must rebuild and reinstall the suppression binder.** The
  canonical suppression plan grew from 54 edits to **178** to cover the new
  pickups, so its SHA-256 changed. A binder built for a slice-1 seed no longer
  matches the installation witness and the native client will stay disarmed
  until you rebuild it. Row ids and acquisition flags are preserved exactly, as
  before.

- Four planned suppression rows are no-ops: those pickups already award exactly
  one Blood Vial. The writer records them as such, so "unchanged" no longer
  looks like a failed write.

### Fixed

- **The enemy-randomization panel could vanish on short displays; the launcher
  is now tabbed.** Everything used to sit in one tall column, so on a 1080p-class
  screen the fixed-height panels outgrew the window and Tk shrank the only
  stretchable one — the enemy-randomization panel — to nothing, taking the
  **Randomize Enemies** toggle and the progress log with it, with no message and
  no scrollbar to reveal them. Setup and enemy randomization are now two tabs,
  the progress log has moved out to its own always-visible panel beneath them
  (it reports launch and build progress, not enemizer progress), and both
  stretchable areas carry a minimum height so neither can be squeezed away
  again. Nothing about what the fields do, what is saved, or what is validated
  changed — only where they sit (#190).


### Known limitations

- Nothing in Cathedral Ward or Old Yharnam has been seen live. Every new flag
  is static evidence from the committed catalogs: no pickup in either region
  has a pre-pickup/post-pickup/restart canary, and neither the Blood-starved
  Beast nor Vicar Amelia flag has been observed firing. Slice 1's Central
  Yharnam evidence does not carry over to them.
- The Rifle Spear, Hunter's Torch and Charred Hunter Garb that Old Yharnam
  holds in vanilla are suppressed, not shuffled: admitting a weapon or attire
  item to the pool still needs its own live grant canary.

### Added

- **Doctor**: a one-shot preflight of the whole player chain, available as a
  launcher button, as `python -m bb_launcher doctor --settings ...`, and as
  `build.ps1 -Doctor`. It validates the game install, AP seed request, launch
  plan, runtime-build agreement, suppression chain, installed gameparam
  (naming the two tamper cases separately), MapStudio source, AP server
  reachability, and blocking processes, printing one PASS/WARN/FAIL list with
  a remedy per failure instead of failing one item per run.

- `docs/PLAYTESTING.md`: a player-facing five-minute setup guide with the
  session rules, the slice-1 checklist, what to send back, and a
  troubleshooting table. The package now ships it beside the launcher, along
  with the suppression binder and its build manifest, so the launcher
  auto-fills the suppression pair for a packaged player.

- Tag-triggered prereleases: pushing a `v*` tag (or running the release
  workflow manually) builds the full Windows launcher package -- launcher,
  native tools, CE table, and the bb-ap-client built from the client repo --
  and attaches the zip to a GitHub prerelease, so a playtester needs no
  GitHub account to download it. The suppression binder is licensed-game-
  derived and stays out of CI builds; ship it via a local
  `build.ps1 -Package` zip or send binder + manifest alongside.

### Changed

- `build.ps1 -Package` builds the suppression binder from the installed
  patch-layer gameparam (`-GameRoot`, or the auto-discovered install tree), so
  a fresh package's binder passes the launcher's source-hash check without a
  manual hand-build. `-ClientRepo` auto-discovers the sibling er-archipelago
  checkout. The launcher's source-hash error now names the file it hashed and
  the fix.

### Fixed

- **The Cheat Engine grant bridge no longer acknowledges an item it cannot
  witness being granted.** The harness had one path that reported success
  without executing anything: when a retained command's stack already held
  `expected_before + quantity`, it declared the grant "already applied". After
  a crash or relaunch that equality is usually a coincidence -- the save
  reloaded at a different count, or the player picked the same item up -- and
  every item acknowledged that way was recorded as delivered and lost for good
  (#163, seen as a 13-item backlog drained and acknowledged with nothing in
  inventory). The shortcut now requires a durable state from this same harness
  that recorded a *verified* write (`completed` / `recovered_complete`); the
  statuses written before a write (`queued`, `executing`, `verify_pending`,
  `recovery_pending`) may still reconstruct the expected count, which is what
  keeps a genuinely-applied grant from being applied twice, but may no longer
  acknowledge one. Without that witness the harness reports
  `recovery_ambiguous` and keeps the command file, so the client's staleness
  check blocks the delivery out loud instead of the ledger silently banking it.
- Item grants no longer fail verification against the wrong inventory stack:
  the grant harness now verifies a native insert against the result slot the
  game itself reported (id matches, quantity covers the grant) instead of only
  re-scanning the whole inventory for an exact total, which latched a false
  `failed` state (and blocked all later deliveries) whenever the game merged
  the grant into a stack the scan could not see at queue time. Grants for
  absent stacks also wait out incremental inventory hydration before
  native-inserting, so a duplicate stack is not created next to one that has
  not become visible yet.

- The world now imports correctly from the zipped `.apworld` players actually
  install: every data table (`archipelago.json`, `ids.tsv`,
  `fixed_locations.tsv`, `location_names.tsv`) is read through
  `importlib.resources` instead of filesystem paths, which do not exist under
  zipimport. CI now generates from the zipped apworld on every run, so a
  zip-only import failure cannot reach a player again.

### Added

- A **Full Item Pool** world option (default on): the seed now places every
  validated item — Saw Spear, Augur of Ebrietas, and the ten progression keys
  (Hunter Chief Emblem, Cainhurst Summons, Tonsil Stone, Upper Cathedral Key,
  Orphanage Key, Eye of a Blood-drunk Hunter, Eye Pendant, Astral Clocktower
  Key, Celestial Dial, Laurence's Skull) — across the same 53 Central Yharnam
  locations, with filler cycling over the rest. The playable area is
  unchanged; the progression keys are forward unlocks whose vanilla homes sit
  outside the slice, so no new suppression is needed. Turning the option off
  restores the original six-item slice pool exactly. The client slot data now
  carries `full_item_pool` and only ever lists bindings for items the seed
  can grant.
- A DeathLink send-signal session kit now narrows the hunt from the committed
  corpus before any live gameplay minutes are spent: tests pin that no event
  flag fires on every player death (all three `CharacterDead(10000)` sites are
  quest-specific), seven player death-state SpEffect rows and the validated HP
  path are the live leads, and a death-vs-lamp-warp capture harness intersects
  trials, subtracts the no-death control so "changed" is not mistaken for
  "death", and classifies survivors as reload-persistent counters or transient
  edges. A write-breakpoint skeleton attributes the writer. No candidate is
  claimed as the signal until the live session validates it.
- The location-name table now covers the full fixed-treasure catalog: all 651
  rows of `research/catalog/fixed_location_catalog.tsv` are named in
  `worlds/bloodborne/location_names.tsv`, and tests enforce full-catalog
  completeness, so a new catalog row fails CI until it is named. Names past the
  MVP set rest on the committed map, event-tag, coordinate, and item-category
  data; spots the catalog cannot distinguish carry `#N` ordinals marked
  `unestablished`, and 60 rows whose items have no committed English name
  (category-8 blood gems and two nameless goods) are named at category level
  with the gap recorded in `basis`. Wiring the table into generation remains
  follow-up scope (#82).
- Location names are now a declared contract ahead of the first numbered
  release that freezes them: `worlds/bloodborne/location_names.tsv` names all
  83 MVP-candidate fixed treasures, `docs/LOCATION-NAMING.md` defines the
  format and rename rules, and tests enforce completeness, uniqueness, and
  agreement with already-published names. Generated seeds still use the
  existing names; replacing the `(Lot NNN)` placeholders awaits the rename
  decision tracked in #75.
- A UI-independent Bloodborne AP launcher core now discovers and validates
  CUSA03173 `01.09`, caches seed overlays by every build/source/options input,
  activates only owned param/map replacements transactionally, recovers an
  interrupted swap, restores the previous seed, bypasses owned overlays for a
  vanilla launch, and preflights coordinated shadPS4/client/CE startup. Fake
  game-tree tests prove conflict refusal and zero base/update mutation. The
  desktop UI, bundled native tools, and real-game overlay canaries remain open.
- The desktop launcher now exposes a real **Randomize Enemies** toggle, enemy
  seed, tier-mixing, and locomotion controls. **Randomize & Launch** invokes the
  deterministic planner and guarded MSBB writer, verifies the suppression
  witness and generated maps, composes the seed cache, activates it through the
  transactional core, and starts the pinned launch components. Tool output and
  actionable failures are streamed into the UI; failed build diagnostics are
  preserved. Bundling the native tools remains a packaging follow-up.
- The generated world is now the bounded Central Yharnam vertical slice: 51
  physical pickups, Cleric Beast, and Father Gascoigne. Two later-cycle
  replacement lots are collapsed onto their physical chests, both boss flags
  are carried in slot data, and Gascoigne is the client-reported goal.
- Vanilla-award suppression now covers all 51 pickups across goods, weapons,
  attire, and blood gems. The 54-row plan includes the Hunter Set continuation
  rows, has zero refusals, and builds/reopens successfully through the guarded
  native writer. Installation and in-game canary validation remain pending.
- The live event-flag manager read path is validated on CUSA03173 `01.09`. A
  save-restored pickup replay and a one-shot write breakpoint proved divisor-1000
  grouping with MSB-first bit packing; a manager-relative resolver rediscovers the
  randomized eboot base, gates on the setter signature, fails closed on a
  mismatch, and returns live flag state without Cheat Engine. The apworld's own
  client still reports checks manually. The separate r5 native client now has
  save-identity, gameplay-state and debounce gates, and deliberately leaves
  live check sends disarmed until its backend can supply the first two.
- One runtime build string, `bb-0.1.0-r5`, now spans the apworld, the client, the
  Cheat Engine table and the grant helper. The client prints it on connect and
  refuses a harness reporting a different or missing version; the wire contract is
  `BBGRANT1` and the table identifies itself as `bb-native-grant-v5`.
- A repeatable event-flag playtest kit records hashed session manifests, captures
  four-stage snapshots, intersects candidates across trials, and logs the
  instruction that writes a surviving candidate.
- Nine catalog-backed fixed treasure checks expand the pool to 29 locations.
  Cainhurst Summons, Tonsil Stone, and Orphanage Key now each gate at least one
  multiworld check, and suppression planning covers every added vanilla award.
- Manual `/check` commands now keep a timestamped local journal and suggest close
  location names after a typo.
- The vanilla-award suppression tool can replace nine planned key-item awards
  while preserving their acquisition flags. Its output still requires repacking
  and in-game validation before it is part of the playable install.
- Saw Spear is the first equipment item admitted to the randomized pool. Slot
  data carries its separately validated raw and normalized descriptors, category,
  +0 reinforcement level, right-hand receive policy and evidence class. Torch
  remains explicitly excluded after its inferred descriptor produced no visible
  inventory item.

### Changed

- The 45 shipped `(Lot NNN)` placeholder location names in the Central Yharnam
  slice are renamed to their contract names (#75 ruling: the lot suffix is
  dropped, `x1` is dropped, `xN` for N > 1 is kept). Two checks move region
  name to Iosefka's Clinic on the MSB warp-anchor evidence; keys and network
  IDs are unchanged. `location_names.tsv` now feeds the slice builder, so the
  table is the single source for those names.
- The check published as "Underground Corpse Pile - Underground Jail Blood
  Stone Chunk" is renamed "Research Hall - Blood Stone Chunk (underground
  cell)" and moves to the Research Hall region (#82 ruling): the flag 53500630
  sits in m35_00 and its event tag 地下牢03 is the Research Hall cell block,
  the same 地下牢NN family as the Fist of Gratia row. There is no Blood Stone
  Chunk treasure in the Underground Corpse Pile; the chunk near Ludwig's arena
  is a titanite-lizard drop, a different thing. The Underground Corpse Pile
  region keeps a check through the newly authored Inner Chamber Key treasure
  (50002360, event tag 宝死体_地下牢の鍵), which joins the unpublished model
  pool — the Central Yharnam network slice is unchanged.

### Fixed

- The CE harness is portable across Windows accounts, respects the process
  manually attached in Cheat Engine, rejects stale logged eboot bases, falls
  back to live signature discovery, and reports setup/bootstrap outcomes
  visibly. It no longer treats emulator-specific Intel SFX patch bytes as an
  item-grant prerequisite. Bootstrap also waits for the inventory list to
  hydrate before declaring a Vial absent; this fixes a live second-machine race
  where a valid stack appeared at logical slot 78 after the first scan ended at
  slot 76.
- Absent Blood Vial delivery now fails closed. A second-machine shadPS4 0.18
  test showed native insertion could create an invalid `0xF00003E8`
  `?ItemInfo?` record instead of a Vial. Existing-stack Vial delivery remains
  supported while the absent-stack regression is tracked separately. The
  bootstrap lookup now correctly distinguishes native raw descriptors
  (`0xB...`) from canonical inventory runtime IDs (`0x400...`); live canaries
  proved a 12-to-13 Vial increment and a zero-Vial no-item-created refusal.

- Items the player does not already hold are granted correctly under shadPS4
  v0.18. Category-4 goods use the 24-byte descriptor in the consumable
  function's retiring stack frame; category-0 equipment uses a persistent
  24-byte descriptor. A native Saw Spear grant was verified in inventory while
  the game remained responsive. Absent-stack, existing-stack, equipment, and
  restart-replay recovery paths are validated live.
- Runtime location bindings now distinguish MSB treasures from EMEVD item-lot
  awards and carry source-specific provenance.

## 0.1.0 - 2026-08-18

Initial vertical-slice development release.

### Added

- An Archipelago world with stable network IDs, ten shufflable key items, twenty
  locations, boss-event progression, and deterministic generation.
- A Bloodborne client that connects to Archipelago, reports checks manually, and
  queues received items through the validated Cheat Engine grant bridge.
- A conservative deterministic enemizer planner, guarded MSB writer, packaging
  workflow, and a 25-seed offline release gate.
- Static acquisition-flag mappings for six fixed locations and read-only shadPS4
  hook-site inspection.

### Known limitations

- Location checks are not detected automatically; the live event-flag manager
  accessor has not been validated.
- The enemizer writer and vanilla-award suppression output have not been
  playtested in game.
- The grant bridge still needs live validation of its failed-verify and restart
  recovery paths.

### Validated

- **The CE-free delivery payload encoding is confirmed against Cheat Engine.**
  The two cave blobs in the native-grant contract were read back from a live
  armed shadPS4 process (`tools/compare_ce_payload.py`) and matched Cheat
  Engine's assembled bytes, after switching three register-to-register `mov`s
  to CE's RM-form encoding (semantically identical). The payload's provenance
  moves from `inferred` to `validated`; owner checklist item 1 is complete.
  Cheat Engine remains the shipping delivery path for now.
