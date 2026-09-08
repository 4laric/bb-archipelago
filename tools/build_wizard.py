#!/usr/bin/env python3
"""
build_wizard.py -- render site/wizard.html from site/options-metadata.json.

er-archipelago's wizard.html is a hand-maintained page with the metadata blob INJECTED into it;
that works there because the page has grown a decade of ER-specific panels around the generic
control renderer. Here the page is GENERATED whole, which buys the property the spec actually
wants: `--check` can prove the deployed page and the apworld's option surface agree byte for
byte, with no hand-edit able to drift between them.

WHAT IS BLOODBORNE-SPECIFIC. The ER census panels (region census, pool composition) are replaced
by ONE panel, "How big is this seed?", computed from the world itself rather than from a TSV row
count: `ALL_NETWORK_LOCATIONS` filtered exactly the way `BloodborneWorld._active_locations` filters
it. That is the only definition of a seed's check count that cannot be wrong, and it means the
panel moves when the data moves. Importing `worlds.bloodborne` costs no Archipelago: the model and
the location key sets live outside the `try: from Options import ...` guard.

  ⚠️  `randomize_enemy_drops` DOES NOT ADD CHECKS, whatever a reading of the spec suggests. Its
      docstring is explicit -- "Enemy kills never become Archipelago checks" -- it rewrites local
      loot tables only. The panel says so rather than showing a number, because a "+N checks" row
      for an option that adds none is the kind of quiet wrong answer this repo gates against.

Usage:
    python tools/build_wizard.py            # write site/wizard.html
    python tools/build_wizard.py --check    # exit 1 if it is stale
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

META = os.path.join(ROOT, "site", "options-metadata.json")
OUT = os.path.join(ROOT, "site", "wizard.html")


def seed_size():
    """Per-region check counts, split exactly the way `_active_locations` splits them."""
    from worlds.bloodborne import ALL_NETWORK_LOCATIONS
    from worlds.bloodborne.data import (
        ALTERNATE_GAOL_LOCATION_KEYS,
        DLC_LOCATION_KEYS,
        DLC_REGIONS,
        ONE_TIME_ENEMY_LOCATION_KEYS,
    )

    # FOUR BUCKETS PER REGION, not a per-region DLC flag. The obvious shortcut -- "a region is
    # DLC, so all its checks are" -- is false in the shipped data: `pickup_eye_of_blood_drunk_hunter`
    # is a DLC-gated location sitting in Hunter's Dream, a base-game region. Bucketing each
    # location by the key sets the generator itself filters on is the only version that adds up.
    rows = {}
    for location in ALL_NETWORK_LOCATIONS:
        row = rows.setdefault(location.region, {
            "region": location.region,
            "dlc_region": location.region in DLC_REGIONS,
            "base": 0, "dlc": 0, "gaol": 0, "one_time": 0,
        })
        if location.key in ONE_TIME_ENEMY_LOCATION_KEYS:
            row["one_time"] += 1
        elif location.key in ALTERNATE_GAOL_LOCATION_KEYS:
            row["gaol"] += 1
        elif location.key in DLC_LOCATION_KEYS:
            row["dlc"] += 1
        else:
            row["base"] += 1

    ordered = sorted(rows.values(), key=lambda r: (r["dlc_region"], r["region"]))
    totals = {key: sum(r[key] for r in ordered) for key in ("base", "dlc", "gaol", "one_time")}
    if sum(totals.values()) != len(ALL_NETWORK_LOCATIONS):
        sys.exit("[FAIL] seed-size buckets do not add up to the published location count")
    return {"regions": ordered, "totals": totals, "published": len(ALL_NETWORK_LOCATIONS)}


def blob(name, payload):
    text = json.dumps(payload, indent=1, ensure_ascii=False).replace("</", "<\\/")
    return '<script id="%s" type="application/json">\n%s\n</script>' % (name, text)


CSS = """
:root{--bg:#14110f;--bg2:#1c1917;--panel:#232019;--text:#e8e0cf;--dim:#9a8f78;
 --gold:#c8a95a;--gold-dim:#8a7440;--blood:#8c2b25;--ok:#6f9f5c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
 font:15px/1.55 Georgia,'Times New Roman',serif}
a{color:var(--gold)}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 80px}
header.hero{border-bottom:1px solid var(--gold-dim);background:var(--bg2);padding:26px 0 20px}
header.hero h1{margin:0 0 6px;font-size:27px;letter-spacing:.04em;color:var(--gold)}
header.hero p{margin:0;color:var(--dim);font-size:14px}
.stamp{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim)}
h2{font-size:19px;color:var(--gold);letter-spacing:.03em;margin:34px 0 10px}
.panel{background:var(--panel);border:1px solid #3a332a;border-radius:6px;padding:16px 18px;margin:14px 0}
.presets{display:flex;flex-wrap:wrap;gap:10px}
.presets button{flex:1 1 240px;text-align:left;background:var(--bg2);color:var(--text);
 border:1px solid var(--gold-dim);border-radius:6px;padding:11px 13px;cursor:pointer;font:inherit}
.presets button:hover,.presets button:focus-visible{border-color:var(--gold);outline:none}
.presets b{display:block;color:var(--gold);font-size:15px}
.presets span{display:block;color:var(--dim);font-size:13px;margin-top:3px}
.opt{padding:12px 0;border-top:1px solid #302a22}
.opt:first-child{border-top:none}
.opt .row{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.opt label.name{font-weight:bold;color:var(--text)}
.opt .key{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim)}
.opt .desc{color:var(--dim);font-size:13.5px;margin:5px 0 0;white-space:pre-wrap}
.opt select,.opt input[type=number]{background:var(--bg2);color:var(--text);
 border:1px solid var(--gold-dim);border-radius:4px;padding:5px 8px;font:inherit;min-width:170px}
.opt input[type=checkbox]{width:17px;height:17px;accent-color:var(--gold)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:5px 9px;border-bottom:1px solid #302a22}
th{color:var(--gold);font-weight:normal;letter-spacing:.04em}
td.n{text-align:right;font-family:ui-monospace,Consolas,monospace}
tr.off td{color:#5f584c}
.big{font-size:30px;color:var(--gold);font-family:ui-monospace,Consolas,monospace}
textarea{width:100%;min-height:280px;background:#100e0c;color:var(--text);
 border:1px solid var(--gold-dim);border-radius:5px;padding:11px;
 font:13px/1.5 ui-monospace,Consolas,monospace;resize:vertical}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.btns button{background:var(--gold-dim);color:#fff;border:1px solid var(--gold);
 border-radius:5px;padding:8px 16px;font:inherit;cursor:pointer}
.btns button:hover{background:var(--gold)}
.btns button.ghost{background:transparent;color:var(--gold)}
.note{color:var(--dim);font-size:13px}
.warn{border-left:3px solid var(--blood);padding-left:12px}
#msg{min-height:20px;font-size:13px;color:var(--ok)}
#msg.bad{color:#e08b7a}
footer{border-top:1px solid #302a22;margin-top:50px;padding:20px 0;color:var(--dim);font-size:13px}
"""


def render(meta, sizes):
    parts = [
        "<!-- GENERATED by tools/build_wizard.py from site/options-metadata.json. Do not hand-edit:",
        "     tools/build_wizard.py --check fails on any diff, and site-checks.yaml runs it. -->",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Bloodborne Archipelago - yaml builder</title>",
        "<style>%s</style>" % CSS,
        '<div id="er-tabs" data-tab="builder"></div>',
        '<script src="/bb/tabs.js" defer></script>',
        "<header class='hero'><div class='wrap'>",
        "<h1>Bloodborne Archipelago &mdash; yaml builder</h1>",
        "<p>Pick your options, copy the yaml, hand it to the host. "
        "<span class='stamp'>apworld v%s &middot; option surface %s</span></p>"
        % (meta["apworld_version"], meta["source_sha256"][:12]),
        "</div></header>",
        "<div class='wrap'>",
        "<p class='note warn'>This page describes <b>apworld v%s</b>. If the host generates with a "
        "different apworld, an option it has never heard of is dropped with one buried log line "
        "and the seed is built without it &mdash; so the version above rides into the yaml's "
        "<code>description</code>, where Archipelago prints it in the generation log."
        % meta["apworld_version"],
        "<h2>Start from a preset</h2><div class='panel presets'>",
    ]
    for preset in meta["presets"]:
        parts.append(
            "<button type='button' data-preset='%s' title='%s'><b>%s</b><span>%s</span></button>"
            % (preset["id"], preset["description"].replace("'", "&#39;"),
               preset["title"], preset["tagline"]))
    parts.append("</div>")

    by_key = {o["key"]: o for o in meta["options"]}
    for group in meta["groups"]:
        parts.append("<h2>%s</h2><div class='panel'>" % group["name"])
        for key in group["options"]:
            parts.append(control(by_key[key]))
        parts.append("</div>")
        if group["name"] == "Seed size":
            parts.append(SEED_PANEL)

    parts += [
        "<h2>Your yaml</h2>",
        "<div class='panel'>",
        "<div class='row' style='display:flex;gap:12px;flex-wrap:wrap;align-items:baseline'>",
        "<label class='name' for='slot'>Player name</label>",
        "<input id='slot' value='Player' "
        "style='background:#1c1917;color:#e8e0cf;border:1px solid #8a7440;"
        "border-radius:4px;padding:5px 8px;font:inherit'>",
        "</div>",
        "<textarea id='yaml' spellcheck='false' aria-label='Generated yaml'></textarea>",
        "<div class='btns'>",
        "<button type='button' id='copy'>Copy</button>",
        "<button type='button' id='download'>Download .yaml</button>",
        "<button type='button' class='ghost' id='import'>Import a yaml</button>",
        "<button type='button' class='ghost' id='reset'>Back to defaults</button>",
        "</div><div id='msg' role='status'></div>",
        "<p class='note'>Import reads a yaml this page wrote (or any yaml with a flat "
        "<code>Bloodborne:</code> block) and puts the controls back where it found them. "
        "Keys this apworld does not have are reported, not silently dropped.</p>",
        "</div>",
        "<footer>Bloodborne Archipelago is a fan project. Bloodborne is a trademark of Sony "
        "Interactive Entertainment; FromSoftware developed the game. Neither is involved in, "
        "endorses, or supports this project.</footer>",
        "</div>",
        blob("bb-options-metadata", meta),
        blob("bb-seed-size", sizes),
        "<script>%s</script>" % JS,
    ]
    return "\n".join(parts) + "\n"


def control(option):
    key, kind = option["key"], option["kind"]
    head = ("<div class='opt' data-key='%s' data-kind='%s'><div class='row'>" % (key, kind))
    label = "<label class='name' for='o-%s'>%s</label><span class='key'>%s</span>" % (
        key, esc(option["display_name"]), key)
    if kind == "toggle":
        field = "<input type='checkbox' id='o-%s'%s>" % (
            key, " checked" if option["default"] else "")
        body = field + " " + label
    elif kind == "choice":
        opts = "".join(
            "<option value='%s'%s>%s</option>"
            % (c["name"], " selected" if c["name"] == option["default"] else "", esc(c["label"]))
            for c in option["choices"])
        body = label + "<select id='o-%s'>%s</select>" % (key, opts)
    else:
        body = label + (
            "<input type='number' id='o-%s' min='%d' max='%d' value='%d' step='1'>"
            % (key, option["range"]["start"], option["range"]["end"], option["default"]))
    return (head + body + "</div><p class='desc'>%s</p></div>"
            % esc(option["description"].strip()))


def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("'", "&#39;"))


SEED_PANEL = """<div class='panel'>
<h3 style='margin:0 0 4px;color:#c8a95a;font-size:16px'>How big is this seed?</h3>
<p class='note' id='seed-summary'></p>
<p class='big'><span id='seed-total'>0</span> <span style='font-size:14px;color:#9a8f78'>checks</span></p>
<table><thead><tr><th>Region</th><th class='n'>Checks</th></tr></thead>
<tbody id='seed-rows'></tbody></table>
<p class='note'>Counted from the world's own location table the way the generator counts it, not
from a spreadsheet. <b>Randomize Enemy Consumable Drops does not appear here on purpose</b>: it
shuffles local loot tables and adds no Archipelago checks.</p>
</div>"""


JS = r"""
(function(){
"use strict";
/* The yaml's date stamp is taken at PAGE LOAD, not baked in at build time. Baking it would make
   this generated file differ from a fresh build every day, and the staleness gate in
   site-checks.yaml would fail on the calendar rather than on a real drift. The date a player
   generated their yaml is also the more useful of the two. */
var STAMP = new Date().toISOString().slice(0, 10);
var META = JSON.parse(document.getElementById("bb-options-metadata").textContent);
var SIZE = JSON.parse(document.getElementById("bb-seed-size").textContent);
var BY = {}; META.options.forEach(function(o){ BY[o.key] = o; });

function el(key){ return document.getElementById("o-" + key); }

function get(key){
  var o = BY[key], node = el(key);
  if (o.kind === "toggle") { return node.checked; }
  if (o.kind === "range")  { return Math.max(o.range.start, Math.min(o.range.end, parseInt(node.value, 10) || 0)); }
  return node.value;
}

function set(key, value){
  var o = BY[key], node = el(key);
  if (!o || !node) { return false; }
  if (o.kind === "toggle") { node.checked = !!value; return true; }
  if (o.kind === "range")  { node.value = value; return true; }
  var ok = o.choices.some(function(c){ return c.name === value; });
  if (ok) { node.value = value; }
  return ok;
}

function reset(){ META.field_order.forEach(function(k){ set(k, BY[k].default); }); }

function applyPreset(id){
  var p = META.presets.filter(function(x){ return x.id === id; })[0];
  if (!p) { return; }
  reset();
  Object.keys(p.values).forEach(function(k){ set(k, p.values[k]); });
  render();
  say("Preset applied: " + p.title, false);
}

/* ---- seed size -------------------------------------------------------- */
function renderSize(){
  var dlc = get("include_dlc"), gaol = get("alternate_hypogean_gaol_routes"),
      one = get("one_time_enemy_checks"), total = 0, html = [];
  SIZE.regions.forEach(function(r){
    var n = r.base + (dlc ? r.dlc : 0) + (gaol ? r.gaol : 0) + (one ? r.one_time : 0);
    total += n;
    html.push("<tr" + (n ? "" : " class='off'") + "><td>" + r.region +
      (r.dlc_region ? " <span class='key'>DLC</span>" : "") + "</td><td class='n'>" +
      (n ? n : "&mdash;") + "</td></tr>");
  });
  document.getElementById("seed-rows").innerHTML = html.join("");
  document.getElementById("seed-total").textContent = total;
  var bits = [dlc ? "The Old Hunters is in play." : "Base game only."];
  if (gaol) { bits.push("Alternate Hypogean Gaol routes add their checks."); }
  if (one)  { bits.push("One-time hunter and unique-enemy checks are on."); }
  bits.push(SIZE.published + " checks exist in the datapackage; a seed places the subset above.");
  document.getElementById("seed-summary").textContent = bits.join(" ");
}

/* ---- yaml ------------------------------------------------------------- */
function scalar(v){
  if (typeof v === "boolean") { return v ? "true" : "false"; }
  if (typeof v === "number")  { return String(v); }
  /* Quoted on purpose: the unquoted on/off/yes/no yaml-bool footgun would turn
     randomize_enemy_drops: off into a boolean. */
  return '"' + String(v).replace(/"/g, '\\"') + '"';
}

function buildYaml(){
  var name = (document.getElementById("slot").value || "Player").trim();
  var lines = [
    "# Bloodborne Archipelago options",
    "# Generated by the Bloodborne options wizard " + STAMP +
      " for apworld v" + META.apworld_version,
    "",
    "name: " + name,
    "description: generated by the Bloodborne options wizard " + STAMP +
      " for apworld v" + META.apworld_version,
    "game: " + META.game,
    "",
    META.game + ":"
  ];
  META.field_order.forEach(function(k){
    lines.push("  " + k + ": " + scalar(get(k)));
  });
  return lines.join("\n") + "\n";
}

function render(){ renderSize(); document.getElementById("yaml").value = buildYaml(); }

/* ---- import ----------------------------------------------------------- */
function importYaml(text){
  var inside = false, applied = 0, unknown = [], bad = [];
  text.split(/\r?\n/).forEach(function(line){
    var body = line.replace(/\s+#.*$/, "");
    if (!body.trim()) { return; }
    if (!/^\s/.test(body)) {
      var m = /^([A-Za-z][^:]*):\s*(.*)$/.exec(body);
      if (m && m[1] === "name" && m[2]) {
        document.getElementById("slot").value = m[2].replace(/^["']|["']$/g, "");
      }
      inside = body.trim() === META.game + ":";
      return;
    }
    if (!inside) { return; }
    var kv = /^\s{2}([A-Za-z_][A-Za-z0-9_]*):\s*(\S.*)$/.exec(body);
    if (!kv) { return; }   /* nested blocks (start_inventory) are not our surface */
    var key = kv[1], raw = kv[2].trim().replace(/^["']|["']$/g, "");
    var o = BY[key];
    if (!o) {
      /* progression_balancing and accessibility are Archipelago core, not this world's surface;
         reporting them as unknown would cry wolf on every yaml a real host uses. */
      if (key !== "progression_balancing" && key !== "accessibility") { unknown.push(key); }
      return;
    }
    var value = raw;
    if (o.kind === "toggle") {
      if (raw !== "true" && raw !== "false") { bad.push(key); return; }
      value = raw === "true";
    } else if (o.kind === "range") {
      value = parseInt(raw, 10);
      if (isNaN(value) || value < o.range.start || value > o.range.end) { bad.push(key); return; }
    }
    if (set(key, value)) { applied++; } else { bad.push(key); }
  });
  render();
  var notes = ["Imported " + applied + " option" + (applied === 1 ? "" : "s") + "."];
  if (unknown.length) { notes.push("Not options of this apworld: " + unknown.join(", ") + "."); }
  if (bad.length)     { notes.push("Values out of range or unrecognised: " + bad.join(", ") + "."); }
  say(notes.join(" "), unknown.length > 0 || bad.length > 0);
}

/* ---- wiring ----------------------------------------------------------- */
function say(text, isBad){
  var m = document.getElementById("msg");
  m.textContent = text;
  m.className = isBad ? "bad" : "";
}

document.querySelectorAll("[data-preset]").forEach(function(b){
  b.addEventListener("click", function(){ applyPreset(b.getAttribute("data-preset")); });
});
META.field_order.forEach(function(k){
  var node = el(k);
  node.addEventListener("change", render);
  node.addEventListener("input", render);
});
document.getElementById("slot").addEventListener("input", render);
document.getElementById("reset").addEventListener("click", function(){
  reset(); render(); say("Back to the apworld defaults.", false);
});
document.getElementById("copy").addEventListener("click", function(){
  var ta = document.getElementById("yaml");
  ta.select();
  if (navigator.clipboard) {
    navigator.clipboard.writeText(ta.value).then(
      function(){ say("Copied.", false); },
      function(){ say("Copy failed; select the box and copy by hand.", true); });
  } else { say("Select the box and copy by hand.", true); }
});
document.getElementById("download").addEventListener("click", function(){
  var name = (document.getElementById("slot").value || "Player").replace(/[^A-Za-z0-9._-]/g, "_");
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([buildYaml()], {type: "text/yaml"}));
  a.download = name + ".yaml";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
  say("Downloaded " + a.download + ".", false);
});
document.getElementById("import").addEventListener("click", function(){
  var text = window.prompt("Paste a Bloodborne yaml:");
  if (text) { importYaml(text); }
});

window.bbWizard = {get: get, set: set, buildYaml: buildYaml, importYaml: importYaml, reset: reset};
render();
})();
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render site/wizard.html from the metadata.")
    parser.add_argument("--check", action="store_true", help="exit 1 if site/wizard.html is stale")
    args = parser.parse_args(argv)

    if not os.path.isfile(META):
        sys.exit("[FAIL] %s is missing; run tools/dump_options_metadata.py first"
                 % os.path.relpath(META, ROOT))
    meta = json.load(open(META, encoding="utf-8"))
    html = render(meta, seed_size())

    if args.check:
        if not os.path.isfile(OUT):
            print("[STALE] site/wizard.html is missing")
            return 1
        current = open(OUT, encoding="utf-8", newline="").read().replace("\r\n", "\n")
        if current != html:
            print("[STALE] site/wizard.html differs from a fresh build")
            print("        fix: python tools/build_wizard.py")
            return 1
        print("[ok] site/wizard.html is current (%d options)" % len(meta["options"]))
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("[ok] wrote site/wizard.html (%d options)" % len(meta["options"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
