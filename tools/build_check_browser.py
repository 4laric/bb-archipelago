#!/usr/bin/env python3
"""
build_check_browser.py -- render site/checks.html, the Bloodborne check browser.

Port of er-archipelago's tool of the same name. One self-contained page listing every check the
apworld publishes, with the columns a player or a bug reporter actually needs to answer "is this
check real, where is it, and what used to be there".

THE JOIN. `location_names.tsv` is the naming contract and the widest table (every published
check, including bosses and script awards). `fixed_locations.tsv` is the treasure subset and
carries kind, classification, and the vanilla item descriptor. `ids.tsv` carries the permanent AP
ids. They are joined on `location_flag`, except for the ids, which are keyed by location KEY --
so the world model supplies the key for each flag. Rows in `location_names.tsv` with no model
location are reported and dropped rather than shipped as half-rows.

VANILLA ITEM NAMES. There is no (category, id) -> English name table in this repo. What there is
is `runtime_bindings.ITEM_BINDINGS`, whose `normalized_item_id` is `(category << 28) | id` for
every item the world can place -- so a pooled item's vanilla descriptor resolves to its real
Archipelago name. Everything else falls back to the vanilla handle the naming contract already
embeds in the check name (the segment after " - "), which is what a player reads anyway. The
column says which of the two it got, so an unresolved descriptor is visible rather than implied.

`inputs_hash` is a SHA-256 over the exact bytes of every input, stamped into the page. It is what
makes this a COUPLED page in the sense of the spec's 3.5: it describes a build, so it deploys from
the stable tag rather than from main.

Usage:
    python tools/build_check_browser.py            # write site/checks.html
    python tools/build_check_browser.py --check    # exit 1 if it is stale
"""
import argparse
import csv
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORLD = os.path.join(ROOT, "worlds", "bloodborne")
LOCATION_NAMES = os.path.join(WORLD, "location_names.tsv")
FIXED = os.path.join(WORLD, "fixed_locations.tsv")
IDS = os.path.join(WORLD, "ids.tsv")
LANDMARKS = os.path.join(ROOT, "docs", "location_landmark_evidence.tsv")
OUT = os.path.join(ROOT, "site", "checks.html")

INPUTS = [LOCATION_NAMES, FIXED, IDS, LANDMARKS]

COLUMNS = ["Region", "Check", "Kind", "Classification", "Vanilla", "DLC", "Flag",
           "AP id", "Landmark"]

# Non-treasure rows have no `source_kind`; the location key prefix is the world's own naming of
# what the check IS, and it is stable (the key is the datapackage identity).
KEY_KINDS = [
    ("boss_", "boss"),
    ("interaction_", "interaction"),
    ("script_award_", "script award"),
    ("pickup_", "pickup"),
    ("questline_", "questline"),
    ("enemy_", "enemy"),
    ("event_", "event"),
]


def rows_of(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def inputs_hash():
    digest = hashlib.sha256()
    for path in INPUTS:
        digest.update(os.path.basename(path).encode("utf-8"))
        with open(path, "rb") as fh:
            digest.update(fh.read())
    return digest.hexdigest()


def vanilla_names():
    """`(category, id) -> Archipelago item name` for every item the world can place."""
    from worlds.bloodborne.data import ITEMS
    from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS

    by_key = {item.key: item.name for item in ITEMS}
    out = {}
    for key, binding in ITEM_BINDINGS.items():
        name = by_key.get(key)
        if name is None:
            continue
        out[(binding.item_category, binding.normalized_item_id & 0x0FFFFFFF)] = name
    return out


def build():
    from worlds.bloodborne import LOCATION_ID_BY_KEY
    from worlds.bloodborne.data import DLC_LOCATION_KEYS, DLC_REGIONS, MODEL

    by_flag_fixed = {r["location_flag"]: r for r in rows_of(FIXED)}
    landmarks = {r["location_flag"]: r["landmark"] for r in rows_of(LANDMARKS) if r.get("landmark")}
    names = vanilla_names()

    # The model is the identity: flag -> key comes from the fixed table, and everything else is
    # matched by NAME, which the naming contract guarantees is unique per check.
    key_by_name = {location.name: location.key for location in MODEL.locations}
    key_by_flag = {flag: row["key"] for flag, row in by_flag_fixed.items()}

    rows, orphans = [], []
    for row in rows_of(LOCATION_NAMES):
        flag = row["location_flag"]
        fixed = by_flag_fixed.get(flag)
        key = key_by_flag.get(flag) or key_by_name.get(row["name"])
        if key is None or key not in LOCATION_ID_BY_KEY:
            orphans.append(row["name"])
            continue

        if fixed:
            kind = fixed["source_kind"]
            classification = fixed["classification"]
            suppressed = fixed["vanilla_award_suppressed"] == "True"
            resolved = names.get((int(fixed["item_category"]), int(fixed["item_id"])))
            vanilla = resolved or row["name"].split(" - ", 1)[-1]
            vanilla_source = "binding" if resolved else "name"
        else:
            kind = next((label for prefix, label in KEY_KINDS if key.startswith(prefix)), "event")
            classification = ""
            suppressed = False
            vanilla = row["name"].split(" - ", 1)[-1]
            vanilla_source = "name"

        rows.append({
            "region": row["region"],
            "name": row["name"],
            "kind": kind,
            "classification": classification,
            "vanilla": vanilla,
            "vanilla_source": vanilla_source,
            "suppressed": suppressed,
            "dlc": key in DLC_LOCATION_KEYS or row["region"] in DLC_REGIONS,
            "flag": flag,
            "id": LOCATION_ID_BY_KEY[key],
            "key": key,
            "landmark": landmarks.get(flag, ""),
            "basis": row["basis"],
        })

    if orphans:
        # Loud, not fatal: a naming-contract row with no model location is a data question, and
        # this tool's job is to report the surface rather than to rule on it.
        print("  %d location_names row(s) have no model location and were dropped: %s"
              % (len(orphans), ", ".join(sorted(orphans)[:5]) + (" ..." if len(orphans) > 5 else "")))

    rows.sort(key=lambda r: (r["region"], r["name"]))
    return rows, orphans


CSS = """
:root{--bg:#14110f;--bg2:#1c1917;--panel:#232019;--text:#e8e0cf;--dim:#9a8f78;
 --gold:#c8a95a;--gold-dim:#8a7440;--blood:#8c2b25;--ok:#6f9f5c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
 font:15px/1.5 Georgia,'Times New Roman',serif}
a{color:var(--gold)}
.wrap{max-width:1400px;margin:0 auto;padding:0 18px 70px}
header.hero{border-bottom:1px solid var(--gold-dim);background:var(--bg2);padding:22px 0 18px}
header.hero h1{margin:0 0 6px;font-size:25px;letter-spacing:.04em;color:var(--gold)}
header.hero p{margin:0;color:var(--dim);font-size:14px}
.stamp{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim)}
.panel{background:var(--panel);border:1px solid #3a332a;border-radius:6px;padding:13px 15px;margin:14px 0}
.filters{display:flex;gap:11px;flex-wrap:wrap;align-items:center}
.filters input,.filters select{background:var(--bg2);color:var(--text);border:1px solid var(--gold-dim);
 border-radius:4px;padding:6px 9px;font:inherit}
.filters input[type=search]{min-width:270px}
.filters label{font-size:13px;color:var(--dim)}
.btns{display:flex;gap:9px;flex-wrap:wrap}
.btns button{background:var(--gold-dim);color:#fff;border:1px solid var(--gold);border-radius:5px;
 padding:7px 14px;font:inherit;cursor:pointer}
.btns button:hover{background:var(--gold)}
.btns button.ghost{background:transparent;color:var(--gold)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #2c261f;vertical-align:top}
th{position:sticky;top:0;background:var(--bg2);color:var(--gold);font-weight:normal;
 letter-spacing:.04em;cursor:pointer;white-space:nowrap;z-index:1}
td.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim);white-space:nowrap}
tr:hover td{background:#1b1815}
.tag{font-size:11px;border:1px solid var(--gold-dim);border-radius:999px;padding:1px 7px;color:var(--dim)}
.tag.dlc{border-color:var(--blood);color:#d09a90}
.tag.sup{border-color:var(--ok);color:var(--ok)}
.note{color:var(--dim);font-size:13px}
#count{color:var(--gold);font-family:ui-monospace,Consolas,monospace}
#diff td{border-bottom:1px solid #2c261f}
.add{color:var(--ok)}.del{color:#e08b7a}
footer{border-top:1px solid #302a22;margin-top:40px;padding:18px 0;color:var(--dim);font-size:13px}
"""


def render(rows, stamp):
    payload = {"inputs_hash": stamp, "columns": COLUMNS, "rows": rows}
    blob = json.dumps(payload, indent=None, separators=(",", ":"),
                      ensure_ascii=False).replace("</", "<\\/")
    return "\n".join([
        "<!-- GENERATED by tools/build_check_browser.py. Do not hand-edit:",
        "     tools/build_check_browser.py --check fails on any diff. -->",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Bloodborne Archipelago - check browser</title>",
        "<style>%s</style>" % CSS,
        '<div id="er-tabs" data-tab="checks"></div>',
        '<script src="/bb/tabs.js" defer></script>',
        "<header class='hero'><div class='wrap'>",
        "<h1>Bloodborne Archipelago &mdash; check browser</h1>",
        "<p>Every check the apworld publishes. <span class='stamp'>%d rows &middot; "
        "inputs_hash %s</span></p>" % (len(rows), stamp[:16]),
        "</div></header>",
        "<div class='wrap'>",
        "<div class='panel filters'>",
        "<input type='search' id='q' placeholder='Search check, region, vanilla item, flag'>",
        "<label>Region <select id='f-region'></select></label>",
        "<label>Kind <select id='f-kind'></select></label>",
        "<label>Class <select id='f-class'></select></label>",
        "<label>DLC <select id='f-dlc'>"
        "<option value=''>any</option><option value='1'>DLC only</option>"
        "<option value='0'>base game only</option></select></label>",
        "<span id='count'></span>",
        "</div>",
        "<div class='panel btns'>",
        "<button type='button' id='permalink'>Copy permalink</button>",
        "<button type='button' id='csv'>Export CSV</button>",
        "<button type='button' class='ghost' id='diff-open'>Diff against another build</button>",
        "<button type='button' class='ghost' id='clear'>Clear filters</button>",
        "</div>",
        "<div class='panel' id='diff-panel' hidden>",
        "<p class='note'>Paste another build's exported CSV. Rows are compared by AP id, so a "
        "renamed check shows as a change rather than as one added and one removed.</p>",
        "<textarea id='diff-in' rows='6' style='width:100%;background:#100e0c;color:#e8e0cf;"
        "border:1px solid #8a7440;border-radius:5px;padding:9px;"
        "font:12px ui-monospace,Consolas,monospace'></textarea>",
        "<div class='btns' style='margin-top:8px'><button type='button' id='diff-run'>Compare"
        "</button></div><div id='diff'></div></div>",
        "<table><thead><tr>%s</tr></thead><tbody id='rows'></tbody></table>" %
        "".join("<th data-sort='%d'>%s</th>" % (i, c) for i, c in enumerate(COLUMNS)),
        "<footer>Bloodborne Archipelago is a fan project. Bloodborne is a trademark of Sony "
        "Interactive Entertainment; FromSoftware developed the game. Neither is involved in, "
        "endorses, or supports this project.</footer>",
        "</div>",
        '<script id="bb-checks" type="application/json">%s</script>' % blob,
        "<script>%s</script>" % JS,
    ]) + "\n"


JS = r"""
(function(){
"use strict";
var DATA = JSON.parse(document.getElementById("bb-checks").textContent);
var ROWS = DATA.rows, COLS = DATA.columns;
var sortCol = 0, sortDir = 1;

function esc(s){
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function fill(select, values, label){
  var html = ["<option value=''>" + label + "</option>"];
  values.forEach(function(v){ html.push("<option value='" + esc(v) + "'>" + esc(v) + "</option>"); });
  select.innerHTML = html.join("");
}

function uniq(field){
  var seen = {};
  ROWS.forEach(function(r){ if (r[field]) { seen[r[field]] = 1; } });
  return Object.keys(seen).sort();
}

var q = document.getElementById("q"),
    fRegion = document.getElementById("f-region"),
    fKind = document.getElementById("f-kind"),
    fClass = document.getElementById("f-class"),
    fDlc = document.getElementById("f-dlc");

fill(fRegion, uniq("region"), "any");
fill(fKind, uniq("kind"), "any");
fill(fClass, uniq("classification"), "any");

function cellOf(r, i){
  switch (i) {
    case 0: return r.region;
    case 1: return r.name;
    case 2: return r.kind;
    case 3: return r.classification;
    case 4: return r.vanilla;
    case 5: return r.dlc ? "DLC" : "";
    case 6: return r.flag;
    case 7: return String(r.id);
    case 8: return r.landmark;
  }
  return "";
}

function matches(r){
  if (fRegion.value && r.region !== fRegion.value) { return false; }
  if (fKind.value && r.kind !== fKind.value) { return false; }
  if (fClass.value && r.classification !== fClass.value) { return false; }
  if (fDlc.value === "1" && !r.dlc) { return false; }
  if (fDlc.value === "0" && r.dlc) { return false; }
  var needle = q.value.trim().toLowerCase();
  if (!needle) { return true; }
  return [r.region, r.name, r.vanilla, r.flag, r.key, r.kind, r.landmark, String(r.id)]
    .join(" ").toLowerCase().indexOf(needle) !== -1;
}

function visible(){
  var out = ROWS.filter(matches);
  out.sort(function(a, b){
    var x = cellOf(a, sortCol), y = cellOf(b, sortCol);
    if (sortCol === 7) { return (a.id - b.id) * sortDir; }
    return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
  });
  return out;
}

function render(){
  var shown = visible(), html = [];
  shown.forEach(function(r){
    html.push("<tr><td>" + esc(r.region) + "</td><td>" + esc(r.name) +
      (r.landmark ? "" : "") + "</td><td>" + esc(r.kind) + "</td><td>" +
      esc(r.classification) + "</td><td>" + esc(r.vanilla) +
      (r.vanilla_source === "name" ? " <span class='tag' title='Descriptor not resolved to a " +
        "placeable item; this is the vanilla handle from the check name'>from name</span>" : "") +
      (r.suppressed ? " <span class='tag sup' title='The vanilla award is suppressed in a " +
        "randomized seed'>suppressed</span>" : "") +
      "</td><td>" + (r.dlc ? "<span class='tag dlc'>DLC</span>" : "") +
      "</td><td class='mono'>" + esc(r.flag) + "</td><td class='mono'>" + r.id +
      "</td><td>" + esc(r.landmark) + "</td></tr>");
  });
  document.getElementById("rows").innerHTML = html.join("");
  document.getElementById("count").textContent =
    shown.length + " / " + ROWS.length + " checks";
}

/* ---- permalink: filters live in the query string so a link reproduces the view ---- */
function readUrl(){
  var p = new URLSearchParams(location.search);
  q.value = p.get("q") || "";
  fRegion.value = p.get("region") || "";
  fKind.value = p.get("kind") || "";
  fClass.value = p.get("class") || "";
  fDlc.value = p.get("dlc") || "";
  if (p.get("sort")) { sortCol = parseInt(p.get("sort"), 10) || 0; }
  if (p.get("dir") === "-1") { sortDir = -1; }
}

function urlOf(){
  var p = new URLSearchParams();
  if (q.value.trim()) { p.set("q", q.value.trim()); }
  if (fRegion.value) { p.set("region", fRegion.value); }
  if (fKind.value) { p.set("kind", fKind.value); }
  if (fClass.value) { p.set("class", fClass.value); }
  if (fDlc.value) { p.set("dlc", fDlc.value); }
  if (sortCol) { p.set("sort", String(sortCol)); }
  if (sortDir === -1) { p.set("dir", "-1"); }
  var qs = p.toString();
  return location.origin + location.pathname + (qs ? "?" + qs : "");
}

/* ---- CSV ---- */
function csvCell(v){ return '"' + String(v).replace(/"/g, '""') + '"'; }

function csv(){
  var lines = [COLS.map(csvCell).join(",")];
  visible().forEach(function(r){
    lines.push(COLS.map(function(_, i){ return csvCell(cellOf(r, i)); }).join(","));
  });
  return lines.join("\n") + "\n";
}

function parseCsv(text){
  /* Good enough for a CSV this page wrote: quoted fields, doubled quotes, no embedded newlines. */
  return text.split(/\r?\n/).filter(function(l){ return l.trim(); }).map(function(line){
    var out = [], cur = "", inQ = false;
    for (var i = 0; i < line.length; i++) {
      var c = line[i];
      if (inQ) {
        if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (c === '"') { inQ = false; }
        else { cur += c; }
      } else if (c === '"') { inQ = true; }
      else if (c === ",") { out.push(cur); cur = ""; }
      else { cur += c; }
    }
    out.push(cur);
    return out;
  });
}

function runDiff(){
  var parsed = parseCsv(document.getElementById("diff-in").value);
  var out = document.getElementById("diff");
  if (parsed.length < 2) { out.innerHTML = "<p class='note'>Nothing to compare.</p>"; return; }
  var header = parsed[0], idCol = header.indexOf("AP id");
  if (idCol === -1) { out.innerHTML = "<p class='note'>That CSV has no <b>AP id</b> column.</p>"; return; }
  var theirs = {};
  parsed.slice(1).forEach(function(row){ theirs[row[idCol]] = row; });
  var mine = {};
  ROWS.forEach(function(r){ mine[String(r.id)] = COLS.map(function(_, i){ return cellOf(r, i); }); });

  var lines = [], added = 0, removed = 0, changed = 0;
  Object.keys(mine).forEach(function(id){
    if (!theirs[id]) {
      added++;
      lines.push("<tr class='add'><td>+ new</td><td>" + esc(mine[id][1]) + "</td><td>" + id + "</td></tr>");
      return;
    }
    var diffs = [];
    COLS.forEach(function(c, i){
      var j = header.indexOf(c);
      if (j !== -1 && (theirs[id][j] || "") !== (mine[id][i] || "")) {
        diffs.push(c + ": " + esc(theirs[id][j]) + " → " + esc(mine[id][i]));
      }
    });
    if (diffs.length) {
      changed++;
      lines.push("<tr><td>~ changed</td><td>" + esc(mine[id][1]) + "<br><span class='note'>" +
        diffs.join("; ") + "</span></td><td>" + id + "</td></tr>");
    }
  });
  Object.keys(theirs).forEach(function(id){
    if (!mine[id]) {
      removed++;
      lines.push("<tr class='del'><td>- gone</td><td>" + esc(theirs[id][1] || "") + "</td><td>" + id + "</td></tr>");
    }
  });
  out.innerHTML = "<p class='note'>" + added + " added, " + removed + " removed, " + changed +
    " changed.</p>" + (lines.length ? "<table><tbody>" + lines.join("") + "</tbody></table>" : "");
}

/* ---- wiring ---- */
[q, fRegion, fKind, fClass, fDlc].forEach(function(node){
  node.addEventListener("input", render);
  node.addEventListener("change", render);
});
document.querySelectorAll("th[data-sort]").forEach(function(th){
  th.addEventListener("click", function(){
    var col = parseInt(th.getAttribute("data-sort"), 10);
    sortDir = (col === sortCol) ? -sortDir : 1;
    sortCol = col;
    render();
  });
});
document.getElementById("clear").addEventListener("click", function(){
  q.value = ""; fRegion.value = ""; fKind.value = ""; fClass.value = ""; fDlc.value = "";
  sortCol = 0; sortDir = 1; render();
});
document.getElementById("permalink").addEventListener("click", function(){
  var url = urlOf();
  history.replaceState(null, "", url);
  if (navigator.clipboard) { navigator.clipboard.writeText(url); }
});
document.getElementById("csv").addEventListener("click", function(){
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv()], {type: "text/csv"}));
  a.download = "bloodborne-checks.csv";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
});
document.getElementById("diff-open").addEventListener("click", function(){
  var p = document.getElementById("diff-panel");
  p.hidden = !p.hidden;
});
document.getElementById("diff-run").addEventListener("click", runDiff);

window.bbChecks = {rows: ROWS, visible: visible, csv: csv, inputsHash: DATA.inputs_hash};
readUrl();
render();
})();
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render site/checks.html.")
    parser.add_argument("--check", action="store_true", help="exit 1 if site/checks.html is stale")
    args = parser.parse_args(argv)

    rows, _ = build()
    html = render(rows, inputs_hash())

    if args.check:
        if not os.path.isfile(OUT):
            print("[STALE] site/checks.html is missing")
            return 1
        current = open(OUT, encoding="utf-8", newline="").read().replace("\r\n", "\n")
        if current != html:
            print("[STALE] site/checks.html differs from a fresh build")
            print("        fix: python tools/build_check_browser.py")
            return 1
        print("[ok] site/checks.html is current (%d rows)" % len(rows))
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("[ok] wrote site/checks.html (%d rows, inputs_hash %s)" % (len(rows), inputs_hash()[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
