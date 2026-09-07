# SPEC: Bloodborne on peliarch.ca

Status: draft for review, 2026-09-07. Nothing here is implemented.

peliarch.ca is the Flask site in `4laric/Archipelago` `webgui/` (fork branch `main`). Today it is
"Elden Ring for Archipelago": a static landing page, yaml builder, check browser and bug-report
form copied from `4laric/er-archipelago` at a channel-pinned tag, plus Flask routes for downloads
(GitHub releases) and room hosting (yaml in, MultiServer out). This spec adds Bloodborne as a
second game without forking the site. Three repos are touched:

| Repo | Role | Change |
|---|---|---|
| `4laric/Archipelago` (webgui) | the site | generalize single-game code to a game table; mount `/bb/` |
| `4laric/bb-archipelago` | the world + launcher | grow a `site/` tree (wizard, checks, report, landing, latest.json) and a channel ledger, built by CI |
| `4laric/from-software-archipelago-clients` | the client | nothing required; optional `latest.json` consumer later |

## 1. What the player gets

Mirror the six ER surfaces, one game root each. ER URLs do not move.

| Surface | ER today | Bloodborne | Source |
|---|---|---|---|
| Landing | `/` | `/bb/` (serves `landing.html`) | bb-archipelago `site/landing.html` |
| Yaml builder | `/er/` | `/bb/wizard.html` | `site/wizard.html`, generated from options metadata |
| Check browser | `/er/checks.html` | `/bb/checks.html` | generated from `location_names.tsv` + `fixed_locations.tsv` |
| Bug report | `/er/report.html` | `/bb/report.html` | `site/report.html` |
| Downloads | `/downloads` | `/downloads` gains a Bloodborne section; `/downloads/bb` deep link | GitHub releases of bb-archipelago |
| Hosting | `/hosting` | unchanged, cards become game-list driven | already game-agnostic |
| Update feed | `/er/latest.json` | `/bb/latest.json` | `release/latest.json` in bb-archipelago |

Beta pages follow the ER convention: a `beta/` subdirectory inside the same static tree
(`/bb/beta/wizard.html`), never a second env var.

Not in scope: Nexus (Bloodborne runs under shadPS4, there is no Nexus page), a questlines tab
(Bloodborne has no questline DAG), a Bloodborne-specific room tier.

## 2. Site changes (`4laric/Archipelago` webgui)

### 2.1 A game table replaces the ER singletons

Add `webgui/games.py`:

```python
@dataclass(frozen=True)
class Game:
    key: str              # "er" | "bb"  -- the URL root and the static-dir key
    name: str             # "Elden Ring" | "Bloodborne"
    static_dir: str|None  # from env ER_STATIC_DIR / BB_STATIC_DIR
    downloads_repo: str   # "4laric/er-archipelago" | "4laric/bb-archipelago"
    channels_raw_url: str # raw CHANNELS.tsv on main
    wanted: tuple[tuple[str, Callable[[str], bool]], ...]   # asset matchers
    github_url: str
    nexus_url: str|None   # None for Bloodborne
    extra_tabs: tuple[Tab, ...]   # ER: Questlines; BB: none
GAMES: dict[str, Game]
```

Bloodborne asset matchers, from the live release `v0.1.0-beta.5`:

```python
("bundle",  lambda n: n == "BloodborneAPLauncher-win-x64.zip"),
("apworld", lambda n: n == "bloodborne.apworld"),
```

Both assets ship in one bb-archipelago release, so the existing "one release carries every asset"
rule in `releases._resolve` holds for Bloodborne unchanged. Do not add cross-repo pairing.

`ER_STATIC_DIR` stays as the env name for ER (compose and the host deploy script depend on it);
`BB_STATIC_DIR` is added. `app.py` context processor exposes `games` (those with a static dir
present) and `game` (the current one, from the route) instead of `er_tooling` / `questline_dag`.

### 2.2 Routes

| Route | Change |
|---|---|
| `/<game>/`, `/<game>/<path:filename>` | one handler, `send_from_directory(GAMES[game].static_dir, …)`; default file `landing.html` for `bb`, `wizard.html` for `er` (keeps `/er/` meaning the builder). Unknown game or unset dir: 404 with the existing wording, game-substituted |
| `/` | unchanged this phase: ER landing from `ER_STATIC_DIR`. See §6 open question 1 |
| `/downloads` | renders every game in `GAMES` that resolved a release; `/downloads/<game>` anchors/filters to one. Template loop over `games`, per-game `rel` / `dev` |
| `/hosting` | template cards iterate `games`: "Build a `{{ game.name }}` seed", "Report a `{{ game.name }}` bug". Health probe still hits `/hosting`; the route must never become game-conditional |
| `/generate`, `/rooms`, `/room/*` | no change. `validate_yamls` already accepts any `game:` key; the Bloodborne apworld only has to be installed in `AP_ROOT` (§4) |

### 2.3 Tab strip

The strip is defined twice today: Jinja in `base.html` and `tabs.js` in the ER static tree, pinned
by `TestTabStrip` and er-archipelago `tools/check_tabs.py`. With two games it becomes per-game:

```
Peliarch  [ER ▾ | BB]   Builder  Downloads  Hosting  (Questlines)  Checks  Report a bug
```

- `base.html` renders the strip for `game` (default `er` on shared pages so ER visitors see no
  change). Shared tabs (`Downloads`, `Hosting`) link to the shared pages; game tabs link under the
  game root.
- A brand-adjacent game switcher lists every game with a static dir. It is the only new element
  on ER pages.
- bb-archipelago ships its own `site/tabs.js` rendering the same strip for `bb`. The
  `TestTabStrip` contract is extended to assert both trees render the same links as Jinja
  (read the deployed `tabs.js` text and regex it, the way `test_limits.py` reads deploy files).

### 2.4 `releases.py`

- Module globals become per-game fields on `Game`. `_cache` / `_dev_cache` become one dict keyed
  by `(game.key, channel)`; `reset_cache()` clears all keys.
- **Prerelease rule change.** Bloodborne releases are all GitHub prereleases (`v0.1.0-beta.N`).
  `_resolve` currently filters prereleases out before matching the ledger pointer. Change: when a
  ledger row names a tag, that tag is accepted regardless of the prerelease flag. The ledger is the
  pointer; the flag is GitHub UI. Draft releases stay excluded. ER behaviour is unchanged because
  its stable rows never point at prereleases.
- Development channel: `get_dev_release` requires `beta == main` and a release tagged exactly
  `dev`. Bloodborne has no rolling `dev` release. Phase 1 ships Bloodborne stable only; the
  template hides the development block when `dev` is `None` (it already does for `dev.ok`).
- `TAG_PATTERN` in `.github/scripts/check_er_channels.py` must also accept `v\d+\.\d+\.\d+-beta\.\d+`
  when parameterized for Bloodborne (§4.3).

### 2.5 Templates

- `downloads.html`: wrap the body in `{% for game in games %}`; move the hash-matched-pair warning
  and the asset-name prose into per-game copy blocks. Bloodborne copy: "one zip, one apworld, both
  from the same release; the launcher refuses a seed generated by a different apworld version."
  "Where the project lives" lists `4laric/bb-archipelago` and the clients repo; no Nexus row.
- `index.html`: the three ER cards loop over `games`.
- `room.html`: no change.

## 3. Bloodborne site assets (`4laric/bb-archipelago`)

New directory `site/`, generated where possible, checked in like er-archipelago's `wizard/`.

### 3.1 `site/options-metadata.json` and `site/wizard.html`

- `tools/dump_options_metadata.py` (port of er-archipelago's) walks `BloodborneOptions`
  (`worlds/bloodborne/__init__.py:507-687`) and emits the ER schema: `schema`, `game`,
  `apworld_version` (from `archipelago.json` `world_version`), `source_sha256`, `field_order`,
  `groups`, `options[]` with `key`, `class`, `display_name`, `description` (the docstrings, verbatim),
  `kind` (toggle / choice / range), `default`, `choices` or `range`, and `presets`.
- 16 options today. Groups for the wizard:
  - Goal: `goal`
  - Seed size: `include_dlc`, `include_dlc_gear`, `one_time_enemy_checks`, `randomize_enemy_drops`,
    `randomize_shops`
  - Items: `full_item_pool`, `uncanny_weapons`, `randomize_armor`, `randomize_starting_weapons`,
    `remove_weapon_requirements`
  - Routing: `alternate_hypogean_gaol_routes`
  - Client: `auto_upgrade`, `auto_equip`, `death_link`, `death_link_amnesty`
- Presets: `Defaults`, `Central Yharnam variety` and `Playtest 35` from `examples/*.yaml`.
- The wizard page is the ER `wizard.html` with the ER-specific census panels replaced by a
  Bloodborne "How big is this seed?" panel computed from `fixed_locations.tsv` counts: 517 base,
  668 with DLC, per-region rows, `one_time_enemy_checks` and `randomize_enemy_drops: dropsanity`
  adding their counts. The header names the apworld version, and the emitted yaml carries the ER
  `description:` stamp ("generated by the Bloodborne options wizard <date> for apworld v0.1.0").
- Same CI guards as ER, ported: renders, yaml import round-trip, every option key present, kind
  controls match metadata, metadata is current with the dataclass.

### 3.2 `site/checks.html`

`tools/build_check_browser.py` joins `location_names.tsv` (687 rows, the naming contract,
includes events and bosses) with `fixed_locations.tsv` (625 treasure rows) on `location_flag`,
and `ids.tsv` for AP ids. Columns:

| Column | Source |
|---|---|
| Region | `location_names.region` |
| Check | `location_names.name` |
| Kind | `fixed_locations.source_kind` or `basis` for non-treasure rows (event, boss, shop, drop) |
| Classification | `fixed_locations.classification` (filler, useful, optional, key_or_badge) |
| Vanilla | item name via `item_id` + `item_category`, with `vanilla_award_suppressed` |
| DLC | region in `data.DLC_REGIONS` |
| Flag | `location_flag` |
| AP id | `ids.tsv` |
| Landmark | `docs/location_landmark_evidence.tsv` where resolved (the "nearest grace" analogue) |

Same controls as ER: filters, permalink, CSV export, diff against another build. The page carries
an `inputs_hash` stamp, so it is a coupled page (§3.5).

### 3.3 `site/report.html`

Fields, adapted from the ER form to what a Bloodborne diagnosis actually needs (the jcc stall was
solved from exactly these files):

1. Release tag (from the launcher title or `client.log` line 3)
2. What happened, what you expected
3. Reproducible?
4. Your yaml
5. **Session folder zip**: `%LOCALAPPDATA%\BloodborneArchipelago\sessions\<id>\` containing
   `client.log`, `delivery-diagnostics.jsonl`, `ledger.json`, `rescue-diagnostics.json`; the form
   says to zip the folder and attach it to the GitHub issue, not paste it
6. Launcher Doctor output
7. shadPS4 version and whether it runs elevated
8. DLC in play? (`include_dlc`)
9. Other mods: rainmakerv3 BB_Launcher active, `CUSA03173-mods-user` non-empty
10. Optional spoiler log

Same three outputs: copy for Discord, prefilled GitHub issue on `4laric/bb-archipelago` using the
existing `.github/ISSUE_TEMPLATE/playtest-report.md` fields, preview.

### 3.4 `site/landing.html`

Same skeleton as the ER landing. Sections: what a run is (Hunter Chief Emblem chokepoint,
lamps, DLC gate), how big the seed is (counts from §3.1), the two channels, what is on the site,
setup in five minutes (condensed `docs/PLAYTESTING.md`, linking the full guide, `LAUNCHER.md`,
`KNOWN-LIMITATIONS.md`), contact and the FromSoftware / Sony disclaimer. Also fill the WebHost gap:
add `worlds/bloodborne/docs/setup_en.md` and link it, so the same text serves the apworld's own
setup page.

### 3.5 `release/CHANNELS.tsv`, `release/latest.json`, coupled vs free pages

- `release/CHANNELS.tsv`: append-only ledger, ER format (`channel<TAB>tag`), rows `stable` and
  `beta`. Initial rows: `stable v0.1.0-beta.5`, `beta main`. Promotion is a commit.
- `release/latest.json`, produced by `tools/gen_latest_json.py` from the stable row:
  `{"version": "0.1.0-beta.5", "contract": "<8+ hex>", "url": "https://github.com/4laric/bb-archipelago/releases/tag/v0.1.0-beta.5"}`.
  `contract` is the SHA-256 prefix of `crates/bb-archipelago/contract/bb-native-grant-contract.v5.json`
  as built into that release; the ER verdict logic (`Current`, `SafeUpdate`, `ContractMoved`)
  transfers directly when a Bloodborne client consumer is written.
- Coupled pages (carry an option surface or `inputs_hash`): `wizard.html`, `checks.html`,
  `options-metadata.json`, `latest.json`. Deployed from the stable tag only. Free pages:
  `landing.html`, `report.html`, `tabs.js`. Deployable from `main`. Assert the split in a test the
  way er-archipelago's `test_gf_publish_channels` does.

### 3.6 Deploy script

`tools/deploy_site.sh`, a copy of er-archipelago `tools/deploy_wizard.sh` with `REPO`,
`RAW`, `DEST=${BB_STATIC_DIR:-/srv/bb}` and the file map:

```
site/wizard.html            -> wizard.html          (stable, beta/)
site/checks.html            -> checks.html          (stable, beta/)
site/options-metadata.json  -> options-metadata.json
site/report.html            -> report.html
site/landing.html           -> landing.html
site/tabs.js                -> tabs.js
release/latest.json         -> latest.json
```

Atomic install (`mktemp` + `mv`) is kept.

### 3.7 CI

`release.yaml` gains a step that runs the dump and the build tools and fails if `site/` is stale
against the tag. A `site-checks.yaml` runs the wizard guards on every PR touching `worlds/bloodborne`
or `site/`.

## 4. Deploy (`4laric/Archipelago` `deploy/docker`)

### 4.1 Dockerfile

Add a `bbtools` stage mirroring `ertools`: build args `BB_REPO=4laric/bb-archipelago`,
`BB_REF` (required), `BB_API`; `ADD ${BB_API}/commits/${BB_REF}` cache-bust; clone at the ref;
install the apworld into `/apworld/worlds/bloodborne` (bb-archipelago `build.ps1 -Apworld` has no
Linux entry point, so add `tools/install_apworld.py --ap-dir` to bb-archipelago, the equivalent of
er-archipelago `tools/gf_test.py --install-only`); copy `site/` to `/bb-static`. Stage 2:
`COPY --from=bbtools /apworld/worlds/bloodborne /app/worlds/bloodborne`, `/bb-static`, `.bb-rev`.

`validate-er-ref.sh` is game-neutral in content: rename to `validate-ref.sh` and call it for both refs.

### 4.2 Compose and env

- `BB_REF` build arg (required), `BB_HOST_STATIC_DIR:-/srv/bb` bind mount to `/bb-static:ro`,
  `BB_STATIC_DIR=/bb-static`.
- `.env.example` documents both refs and both host dirs.
- The `/generate` Caddy rate limit stays a single bucket shared by both games. The port range caps
  rooms that exist (200); a second game roughly doubles the creation rate against that budget. Note
  it in the deploy README; no change in this spec.

### 4.3 Channel parity CI

Parameterize `.github/scripts/check_er_channels.py` into `check_channels.py --game bb`
(repo, static paths, bundle name, tag pattern from the game table) and add
`bb-channel-parity.yml` on the same hourly cron, with a `live` job against `https://peliarch.ca/bb/`.

## 5. Tests to add (webgui)

| Test | Prevents |
|---|---|
| `TestGameTable::test_every_game_root_serves_its_landing_and_404s_when_unset` | a missing `BB_STATIC_DIR` taking down `/er/` |
| `TestTabStrip` extension: `test_bb_strip_matches_jinja` | tabs drifting between Jinja and `site/tabs.js` |
| `TestBloodborneDownloads::test_stable_pointer_accepts_a_prerelease_tag` | the prerelease filter hiding every Bloodborne release |
| `TestBloodborneDownloads::test_dev_block_hidden_without_a_dev_release` | an empty Development card |
| `TestPerGameReleaseCache::test_er_failure_returns_er_stale_not_bb` | cache cross-talk between games |
| `TestBbStaticDeploymentMount` (reads compose text) | compose losing the `/bb-static` mount or `BB_REF` |
| `TestHostingCardsPerGame` | the hosting page naming only one game |
| `test_generate_accepts_a_bloodborne_yaml` (generator, fake ap_root with `worlds/bloodborne`) | `/generate` rejecting the second game |

## 6. Open questions

1. **Front door.** Keep `/` as the ER landing with a game switcher (this spec), or make `/` a
   two-card chooser and move the ER landing to `/er/landing.html`? The chooser is one template and
   one route, but it changes what every existing ER visitor sees first.
2. **Bloodborne stable.** Every release is a GitHub prerelease. Either accept the ledger-pointer
   rule in §2.4, or start cutting a non-prerelease tag once the beta stabilizes. The spec works
   either way; the first is needed to ship anything now.
3. **Contact.** One Discord handle for both games, or a Bloodborne-specific one in the contact card?
4. **Client update check.** `/bb/latest.json` is cheap to publish. The consumer in
   `crates/bb-archipelago` is a separate clients-repo change; the launcher today fetches nothing.

## 7. Rollout

1. Site refactor with no Bloodborne content: game table, keyed cache, per-game templates, tests.
   ER pages byte-identical apart from the switcher. Deploy.
2. bb-archipelago: `site/` generators and pages, `release/CHANNELS.tsv`, `latest.json`,
   `install_apworld.py`, `deploy_site.sh`, CI guards. Tag a release that carries them.
3. Deploy: `bbtools` stage, compose mount, `BB_REF` pinned to that tag, parity CI. `/bb/` goes live.
4. Decide the front door (open question 1) and ship it as its own change.
