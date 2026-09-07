#!/usr/bin/env bash
# deploy_site.sh -- put the right Bloodborne pages at /bb/ and /bb/beta/ on the host box.
#
# A copy of er-archipelago's tools/deploy_wizard.sh with this repo's file map. Everything that
# looks like paranoia below is load-bearing there and is kept here deliberately; the comments say
# which failure each piece is for.
#
# THE PROBLEM THIS CLOSES. The wizard is a static page, and if it is deployed by copying it
# whenever somebody copies it, it drifts ahead of the apworld players actually installed. That
# does not fail: Archipelago prints ONE line for an option the installed world has never heard of
# and generates the seed WITHOUT it. So every coupled page is fetched from a REF, not from
# whatever was lying around.
#
#     /bb/wizard.html            <- site/wizard.html            at the STABLE tag
#     /bb/beta/wizard.html       <- site/wizard.html            at the current beta ref
#     /bb/checks.html            <- site/checks.html            at the STABLE tag
#     /bb/beta/checks.html       <- site/checks.html            at the current beta ref
#     /bb/options-metadata.json  <- site/options-metadata.json   at the STABLE tag
#     /bb/report.html            <- site/report.html            at the STABLE tag (or main, --site)
#     /bb/landing.html           <- site/landing.html           at the STABLE tag (or main, --site)
#     /bb/tabs.js                <- site/tabs.js                at the STABLE tag (or main, --site)
#     /bb/latest.json            <- release/latest.json         from main, checked against stable
#
# THE LANDING PAGE GOES IN BB_STATIC_DIR, NOT AT THE FILESYSTEM ROOT. peliarch serves `/bb/` from
# a Flask route backed by that directory; a file written to the web root would never be served and
# nobody would find out until the front page failed to change.
#
# ---- --site : ship a page fix WITHOUT cutting a release ----------------------------------------
#
#   ./tools/deploy_site.sh --site        # landing.html + report.html + tabs.js, from MAIN
#
# !! IT IS DELIBERATELY NOT "all the static pages". THE SPLIT IS DERIVED, NOT A LIST SOMEONE
# MAINTAINS: a page is COUPLED if it carries an option surface (`bb-options-metadata`) or a data
# stamp (`inputs_hash`), and FREE if it carries neither. tests/test_site_assets.py asserts
# SITE_PAGES below is EXACTLY the free set, in BOTH directions -- so a page that gains a stamp
# stops being shippable this way on the commit that gives it one, and a new page with no stamp
# cannot be silently left out.
#
# It FETCHES, it does not build: the box needs no checkout and no python.
#
#   BB_STATIC_DIR=/srv/bb ./tools/deploy_site.sh
#   BB_STATIC_DIR=/srv/bb ./tools/deploy_site.sh --dry-run
#   ./tools/deploy_site.sh --stable-only          # promote stable, leave beta alone
#   ./tools/deploy_site.sh --beta-only            # baked stable: update only the mounted beta/
#
# Cron it if you like -- `beta` tracks the moving ref in CHANNELS.tsv:
#   */15 * * * *  BB_STATIC_DIR=/srv/bb /opt/bb/deploy_site.sh >>/var/log/bb-deploy.log 2>&1
#
# !! THE INSTALL IS ATOMIC (write .tmp, then `mv`). These are single files a browser can be
# mid-GET on; `curl -o` straight onto the served path serves a truncated page for the length of
# the download, and a half-parsed wizard renders as a blank div rather than as an error anybody
# reports.
set -euo pipefail

REPO="${BB_REPO:-4laric/bb-archipelago}"
RAW="https://raw.githubusercontent.com/${REPO}"
DEST="${BB_STATIC_DIR:-/srv/bb}"
DRY=0
STABLE_ONLY=0
NO_CHECKS=0
SITE_ONLY=0
BETA_ONLY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --stable-only) STABLE_ONLY=1 ;;
    --no-checks) NO_CHECKS=1 ;;
    --site) SITE_ONLY=1 ;;
    --beta-only) BETA_ONLY=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done
[ "$BETA_ONLY" = "0" ] || [ "$STABLE_ONLY" = "0" ] \
  || { echo "--beta-only and --stable-only are mutually exclusive" >&2; exit 2; }
[ "$BETA_ONLY" = "0" ] || [ "$SITE_ONLY" = "0" ] \
  || { echo "--beta-only and --site are mutually exclusive" >&2; exit 2; }

say() { printf '%s\n' "$*"; }
# Rule 4: a filter with no tally is a lie. Skips are counted and reported at the end.
SKIPPED_ARTIFACTS=0
# !! `die` exits the SHELL, so install_one's RETURN trap does not run and its .tmp survives -- in
# the directory the web server is serving. A stale `wizard.html.ab12cd.tmp` is fetchable and is a
# half-written page under a name nothing will ever clean up. Track the in-flight temp file
# globally and clear it on EXIT as well, so an abort leaves the directory as it found it.
CURRENT_TMP=""
trap 'rm -f "$CURRENT_TMP"' EXIT
die() { printf 'deploy_site: %s\n' "$*" >&2; exit 1; }

# ---- which tag is stable? Read it from the ledger AT MAIN, so the answer comes from the same
# place the repo records it and a promotion is a commit rather than an argument typed on a box.
stable_tag=""
beta_ref=""
ledger="$(curl -fsSL "${RAW}/main/release/CHANNELS.tsv")" \
  || die "could not fetch release/CHANNELS.tsv"
beta_ref="$(printf '%s\n' "$ledger" | awk -F'\t' '!/^#/ && $1=="beta" { t=$2 } END { print t }')"
[ -n "$beta_ref" ] || die "no beta row in release/CHANNELS.tsv"
if [ "$BETA_ONLY" = "1" ]; then
  say "channels: stable -> baked image (UNTOUCHED) | beta -> ${beta_ref}"
else
  stable_tag="$(printf '%s\n' "$ledger" | awk -F'\t' '!/^#/ && $1=="stable" { t=$2 } END { print t }')"
  [ -n "$stable_tag" ] || die "no stable row in release/CHANNELS.tsv"
  say "channels: stable -> ${stable_tag} | beta -> ${beta_ref}"
fi

# ---- fetch + install one file, atomically, and only if it looks like the thing we asked for.
# !! THE SENTINEL CHECK IS NOT PARANOIA. raw.githubusercontent answers 404 with an HTML page and
# `curl -f` catches that, but a ref that exists and has no wizard, or a proxy that helpfully
# returns a login page, both arrive as 200 with a body. "Did I just install a login page as the
# wizard" is not a question you want answered by a player.
install_one() {  # ref, source path in repo, destination path, sentinel, label
  local ref="$1" src="$2" dst="$3" sentinel="$4" label="$5" tmp
  # mkdir BEFORE mktemp: the temp file has to be a sibling of the destination (mv across
  # filesystems is a copy, which is not atomic), and `beta/` does not exist on a first run.
  mkdir -p "$(dirname "$dst")"
  tmp="$(mktemp "${dst}.XXXXXX.tmp")"
  CURRENT_TMP="$tmp"
  # shellcheck disable=SC2064
  trap "rm -f '$tmp'; CURRENT_TMP=" RETURN
  # !! A 404 AT THE STABLE TAG IS NOT THE SAME FAILURE AS A 404 AT MAIN, and collapsing them
  # aborts a routine deploy every time a NEW page is added. main always carries the current set by
  # construction -- it is this repo -- so a missing file there is a real bug and stays fatal. A
  # stable TAG legitimately predates an artifact added after it was cut, and the honest answer is
  # "not in this release yet", not "the deploy is broken" and not a silently older copy.
  local http
  http="$(curl -sSL -w '%{http_code}' -o "$tmp" "${RAW}/${ref}/${src}")" || http="000"
  if [ "$http" = "404" ]; then
    if [ "$ref" = "main" ] || [ "$ref" = "$beta_ref" ]; then
      die "${src} is MISSING at ${ref} -- that is a moving channel, so this is a bug, not a release gap"
    fi
    say "  SKIP ${label}: ${src} is not in ${ref} yet (added after that tag was cut)"
    SKIPPED_ARTIFACTS=$((SKIPPED_ARTIFACTS + 1))
    return 0
  fi
  [ "$http" = "200" ] || die "fetch failed: ${label} (${ref}) -- HTTP ${http}"
  grep -q "$sentinel" "$tmp" \
    || die "fetched ${label} does not contain ${sentinel} -- refusing to install it"
  local bytes ver
  bytes="$(wc -c < "$tmp" | tr -d ' ')"
  ver="$(sed -n 's/.*"apworld_version": *"\([^"]*\)".*/\1/p' "$tmp" | head -1)"
  [ -n "$ver" ] || ver="(no apworld stamp -- free page)"
  if [ "$DRY" = "1" ]; then
    say "  DRY-RUN ${label}: would install ${bytes} bytes, apworld ${ver} -> ${dst}"
    return 0
  fi
  chmod 0644 "$tmp"
  mv -f "$tmp" "$dst"
  say "  ${label}: ${bytes} bytes, apworld ${ver} -> ${dst}"
}

[ "$DRY" = "1" ] || [ -d "$DEST" ] || die "BB_STATIC_DIR does not exist: ${DEST}"

WIZ_SRC="site/wizard.html"
WIZ_SENTINEL='id="bb-options-metadata"'
CHK_SRC="site/checks.html"
# The check browser's own payload container -- structural, and nothing a 200-with-a-login-page has.
CHK_SENTINEL='id="bb-checks"'
META_SRC="site/options-metadata.json"
# The metadata's own schema key. A login page has no such string, and neither does a truncated
# download that stopped before the field.
META_SENTINEL='"apworld_version"'
RPT_SRC="site/report.html"
RPT_SENTINEL='id="preview"'
LND_SRC="site/landing.html"
LND_SENTINEL='Bloodborne Archipelago'
TABS_SRC="site/tabs.js"
# The strip's own <nav>, which the script builds.
TABS_SENTINEL='id="er-tabs-strip"'

# !! THE FREE SET: src:name, space-separated (the sentinel is looked up by name below). Pages
# carrying NEITHER an option surface
# NOR a data stamp, so they cannot skew against a released apworld and may ship from main at any
# time. Asserted against the files themselves by tests/test_site_assets.py -- do not edit without
# reading that test.
SITE_PAGES="site/landing.html:landing.html site/report.html:report.html site/tabs.js:tabs.js"

sentinel_for() {
  case "$1" in
    landing.html) printf '%s' "$LND_SENTINEL" ;;
    report.html)  printf '%s' "$RPT_SENTINEL" ;;
    tabs.js)      printf '%s' "$TABS_SENTINEL" ;;
    *) die "no sentinel for $1" ;;
  esac
}

# ---- --site: the free pages only, from main, then stop. ----------------------------------------
if [ "$SITE_ONLY" = "1" ]; then
  say "site-only: the pages that carry no option surface and no data stamp, from main"
  for entry in $SITE_PAGES; do
    src="${entry%%:*}"; name="${entry##*:}"
    install_one "main" "$src" "${DEST}/${name}" "$(sentinel_for "$name")" "site    ${name} (main)"
  done
  say ""
  say "The wizard, the check browser and options-metadata.json were NOT touched: they are pinned"
  say "to the stable tag on purpose, and a copy ahead of the released apworld is the failure this"
  say "whole script exists to prevent. Run without --site to move those."
  exit 0
fi

# The peliarch Compose layout can bake stable pages and mount ONLY DEST/beta. Writing
# DEST/wizard.html there succeeds and prints a plausible version while changing no live page.
# This explicit mode updates only the directory that layout serves.
if [ "$BETA_ONLY" = "1" ]; then
  install_one "$beta_ref" "$WIZ_SRC" "${DEST}/beta/wizard.html" "$WIZ_SENTINEL" "wizard  beta (${beta_ref})"
  [ "$NO_CHECKS" = "1" ] || \
    install_one "$beta_ref" "$CHK_SRC" "${DEST}/beta/checks.html" "$CHK_SENTINEL" "checks  beta (${beta_ref})"
  say ""
  say "Stable was NOT written: this mode is for hosts whose stable pages are baked into the image."
  exit 0
fi

install_one "$stable_tag" "$TABS_SRC" "${DEST}/tabs.js" "$TABS_SENTINEL" "tabs    stable (${stable_tag})"
install_one "$stable_tag" "$LND_SRC" "${DEST}/landing.html" "$LND_SENTINEL" "landing stable (${stable_tag})"
install_one "$stable_tag" "$RPT_SRC" "${DEST}/report.html" "$RPT_SENTINEL" "report  stable (${stable_tag})"
install_one "$stable_tag" "$WIZ_SRC" "${DEST}/wizard.html" "$WIZ_SENTINEL" "wizard  stable (${stable_tag})"
install_one "$stable_tag" "$META_SRC" "${DEST}/options-metadata.json" "$META_SENTINEL" \
  "meta    stable (${stable_tag})"
[ "$NO_CHECKS" = "1" ] || \
  install_one "$stable_tag" "$CHK_SRC" "${DEST}/checks.html" "$CHK_SENTINEL" "checks  stable (${stable_tag})"

if [ "$STABLE_ONLY" = "0" ]; then
  install_one "$beta_ref" "$WIZ_SRC" "${DEST}/beta/wizard.html" "$WIZ_SENTINEL" "wizard  beta (${beta_ref})"
  [ "$NO_CHECKS" = "1" ] || \
    install_one "$beta_ref" "$CHK_SRC" "${DEST}/beta/checks.html" "$CHK_SENTINEL" "checks  beta (${beta_ref})"
fi

if [ "$SKIPPED_ARTIFACTS" -gt 0 ]; then
  say ""
  say "!! ${SKIPPED_ARTIFACTS} artifact(s) were not in the stable tag and were NOT installed."
  say "   They ship on the next release. Promote stable in release/CHANNELS.tsv and rerun."
fi

# ---- /bb/latest.json : the machine-readable update verdict --------------------------------------
# {version, contract, url}. The verdict a player needs ("safe to update mid-seed" vs "contract
# moved -- finish this seed first") is DERIVED by a client comparing `contract` to the hash it was
# built against, so this file must name the STABLE tag. It is generated and reviewed in the repo
# (tools/gen_latest_json.py); the deploy re-checks the committed projection against the live
# ledger, because a stale projection must fail closed rather than publish a plausible lie.
# Skipped under --beta-only and --site: it describes stable, and those modes do not touch stable.
if [ "$BETA_ONLY" = "0" ] && [ "$SITE_ONLY" = "0" ] && [ -n "$stable_tag" ]; then
  stable_ver="${stable_tag#v}"
  if [ "$DRY" = "1" ]; then
    say "  DRY   latest.json: release/latest.json from main (${stable_ver})"
  else
    mkdir -p "$DEST"
    ljtmp="$(mktemp "${DEST}/latest.json.XXXXXX.tmp")"
    CURRENT_TMP="$ljtmp"
    curl -fsSL "${RAW}/main/release/latest.json" -o "$ljtmp" \
      || die "could not fetch release/latest.json"
    grep -Fq "\"version\": \"${stable_ver}\"" "$ljtmp" \
      || die "release/latest.json version does not match stable ${stable_tag} -- it would lie"
    grep -Fq "releases/tag/${stable_tag}" "$ljtmp" \
      || die "release/latest.json URL does not name stable ${stable_tag} -- it would lie"
    grep -Eq '"contract": "[0-9a-f]{8,}"' "$ljtmp" \
      || die "release/latest.json has no contract hash -- it would lie"
    mv "$ljtmp" "${DEST}/latest.json"; CURRENT_TMP=""
    say "  OK    latest.json: ${stable_ver}"
  fi
fi

cat <<'NOTE'

Live at:
  /bb/                          stable   the landing page (served by the app from BB_STATIC_DIR)
  /bb/tabs.js                   stable   the tab strip, shared by all four static pages
  /bb/wizard.html               stable   the options wizard
  /bb/options-metadata.json     stable   the option surface the wizard renders from
  /bb/report.html               stable   the bug report builder
  /bb/checks.html               stable   the check browser
  /bb/beta/wizard.html          beta
  /bb/beta/checks.html          beta
  /bb/latest.json               stable   the update verdict (version + contract)

Note the trailing slash: `/bb/` maps to landing.html, but `/bb/beta/` does NOT -- the Flask route
is `/bb/<path:filename>` and "beta/" is not a file. Link the full path, or add a route for it.
NOTE
