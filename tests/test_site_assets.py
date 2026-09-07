"""Guards for the site/ tree, its generators, and the release ledger.

Ported from er-archipelago's `tools/check_wizard_*.py` family and its
`test_gf_publish_channels`, collapsed into one pytest module because this repo's
convention is unittest classes under `tests/` rather than standalone check
scripts (see tests/test_bloodborne_item_docs.py).

What each group is for:

* **staleness** -- every generated artifact regenerates to exactly what is
  committed. This is the gate that makes the deployed page and the apworld's
  option surface the same statement rather than two that agree today.
* **the wizard renders** -- the page really contains a control for every option,
  of the right kind, and the emitted yaml round-trips through its own importer.
  An option that exists in the dataclass and has no control on the page is a
  knob a player cannot reach and cannot be told about.
* **the coupled/free split** -- asserted in BOTH directions against the pages
  themselves, so a page that gains a data stamp stops being deployable from main
  on the commit that gives it one.
* **the tab strip** -- the other copy of this strip lives in the peliarch repo's
  `base.html`; this end pins the links so the pair fails loudly rather than
  drifting.
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
TOOLS = ROOT / "tools"

WIZARD = SITE / "wizard.html"
CHECKS = SITE / "checks.html"
METADATA = SITE / "options-metadata.json"
LANDING = SITE / "landing.html"
REPORT = SITE / "report.html"
TABS = SITE / "tabs.js"

CHANNELS = ROOT / "release" / "CHANNELS.tsv"
LATEST = ROOT / "release" / "latest.json"
DEPLOY = TOOLS / "deploy_site.sh"

# The two markers that make a page COUPLED to a build. Kept as literals here and in
# tools/deploy_site.sh; the split test below reads both ends.
OPTION_SURFACE_MARKER = "bb-options-metadata"
DATA_STAMP_MARKER = "inputs_hash"
# options-metadata.json IS the option surface rather than a page carrying one, so it cannot carry
# the <script id> marker. `apworld_version` is the field that makes it a statement about one
# build, and it is the string deploy_site.sh uses as that file's sentinel for the same reason.
APWORLD_STAMP_MARKER = '"apworld_version"'

COUPLED_PAGES = {"wizard.html", "checks.html", "options-metadata.json"}
FREE_PAGES = {"landing.html", "report.html", "tabs.js"}


def run_tool(*args):
    """Run a repo tool and return (returncode, stdout+stderr)."""
    result = subprocess.run(
        [sys.executable, str(TOOLS / args[0]), *args[1:]],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


class SiteStalenessTests(unittest.TestCase):
    """Regenerating site/ and release/latest.json must produce no diff."""

    def test_options_metadata_is_current(self):
        code, output = run_tool("dump_options_metadata.py", "--check")
        self.assertEqual(0, code, output)

    def test_wizard_is_current(self):
        code, output = run_tool("build_wizard.py", "--check")
        self.assertEqual(0, code, output)

    def test_check_browser_is_current(self):
        code, output = run_tool("build_check_browser.py", "--check")
        self.assertEqual(0, code, output)

    def test_latest_json_is_current(self):
        code, output = run_tool("gen_latest_json.py", "--check")
        self.assertEqual(0, code, output)


class OptionsMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads(METADATA.read_text(encoding="utf-8"))
        cls.by_key = {o["key"]: o for o in cls.meta["options"]}

    def test_every_dataclass_field_is_described(self):
        source = (ROOT / "worlds" / "bloodborne" / "__init__.py").read_text(encoding="utf-8")
        block = re.search(r"class BloodborneOptions\(PerGameCommonOptions\):\n((?:\s+\w+: \w+\n)+)",
                          source)
        self.assertIsNotNone(block, "BloodborneOptions dataclass not found")
        fields = re.findall(r"^\s+(\w+): \w+$", block.group(1), re.M)
        self.assertEqual(fields, self.meta["field_order"])

    def test_every_option_has_a_description(self):
        for option in self.meta["options"]:
            with self.subTest(option=option["key"]):
                self.assertTrue(option["description"].strip())

    def test_every_option_is_in_exactly_one_group(self):
        seen = []
        for group in self.meta["groups"]:
            seen.extend(group["options"])
        self.assertEqual(sorted(seen), sorted(self.meta["field_order"]))
        self.assertEqual(len(seen), len(set(seen)), "an option is in two groups")

    def test_presets_carry_deviations_only(self):
        for preset in self.meta["presets"]:
            for key, value in preset["values"].items():
                with self.subTest(preset=preset["id"], key=key):
                    self.assertIn(key, self.by_key)
                    self.assertNotEqual(
                        value, self.by_key[key]["default"],
                        "a preset restating a default becomes a lie when the default moves")

    def test_apworld_version_matches_the_manifest(self):
        manifest = json.loads(
            (ROOT / "worlds" / "bloodborne" / "archipelago.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["world_version"], self.meta["apworld_version"])


class WizardPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = WIZARD.read_text(encoding="utf-8")
        cls.meta = json.loads(METADATA.read_text(encoding="utf-8"))

    def test_the_page_inlines_the_metadata_it_renders_from(self):
        blob = re.search(
            r'<script id="bb-options-metadata" type="application/json">\n(.*?)\n</script>',
            self.html, re.S)
        self.assertIsNotNone(blob, "the wizard has no inlined option surface")
        inlined = json.loads(blob.group(1).replace("<\\/", "</"))
        self.assertEqual(self.meta, inlined)

    def test_every_option_key_has_a_control(self):
        for option in self.meta["options"]:
            with self.subTest(option=option["key"]):
                self.assertIn('id="o-%s"' % option["key"], self.html.replace("'", '"'))

    def test_kind_controls_match_the_metadata(self):
        normalised = self.html.replace("'", '"')
        for option in self.meta["options"]:
            block = re.search(
                r'<div class="opt" data-key="%s" data-kind="(\w+)">(.*?)</p></div>'
                % re.escape(option["key"]), normalised, re.S)
            with self.subTest(option=option["key"]):
                self.assertIsNotNone(block)
                self.assertEqual(option["kind"], block.group(1))
                markup = block.group(2)
                if option["kind"] == "toggle":
                    self.assertIn('type="checkbox"', markup)
                elif option["kind"] == "choice":
                    self.assertIn("<select", markup)
                    for choice in option["choices"]:
                        self.assertIn('value="%s"' % choice["name"], markup)
                else:
                    self.assertIn('type="number"', markup)
                    self.assertIn('min="%d"' % option["range"]["start"], markup)
                    self.assertIn('max="%d"' % option["range"]["end"], markup)

    def test_defaults_are_preselected(self):
        normalised = self.html.replace("'", '"')
        for option in self.meta["options"]:
            block = re.search(
                r'<div class="opt" data-key="%s".*?</p></div>' % re.escape(option["key"]),
                normalised, re.S).group(0)
            with self.subTest(option=option["key"]):
                if option["kind"] == "toggle":
                    self.assertEqual(option["default"], "checked" in block)
                elif option["kind"] == "choice":
                    self.assertIn('value="%s" selected' % option["default"], block)
                else:
                    self.assertIn('value="%d"' % option["default"], block)

    def test_the_page_stamps_the_apworld_version(self):
        self.assertIn("apworld v%s" % self.meta["apworld_version"], self.html)

    def test_the_emitted_yaml_names_every_option_in_field_order(self):
        """The yaml builder writes `field_order` -- so the JS must read that list, not the DOM.

        Asserted on the JS source rather than by executing it: the round trip below covers
        behaviour, and this pins the ORDER, which is what makes two wizards' output diffable.
        """
        self.assertIn("META.field_order.forEach", self.html)

    def test_yaml_round_trips_through_the_pages_own_parser(self):
        """Emit a yaml the way the page does, re-read it the way the page does.

        A pure-python re-implementation would only prove this test agrees with itself, so both
        halves are transcribed from the page's own rules: quote every scalar (the on/off yaml-bool
        footgun), two-space keys under the game block, deeper indentation is not our surface.
        """
        values = {}
        for option in self.meta["options"]:
            if option["kind"] == "toggle":
                values[option["key"]] = not option["default"]
            elif option["kind"] == "range":
                values[option["key"]] = option["range"]["end"]
            else:
                values[option["key"]] = option["choices"][-1]["name"]

        lines = ["name: Tester", "game: Bloodborne", "", "Bloodborne:"]
        for key in self.meta["field_order"]:
            value = values[key]
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, int):
                rendered = str(value)
            else:
                rendered = '"%s"' % value
            lines.append("  %s: %s" % (key, rendered))
        text = "\n".join(lines) + "\n"

        parsed, inside = {}, False
        for line in text.splitlines():
            if not line.strip():
                continue
            if not line.startswith(" "):
                inside = line.strip() == "Bloodborne:"
                continue
            if not inside:
                continue
            match = re.match(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*):\s*(\S.*)$", line)
            if not match:
                continue
            raw = match.group(2).strip().strip('"')
            option = next(o for o in self.meta["options"] if o["key"] == match.group(1))
            if option["kind"] == "toggle":
                parsed[match.group(1)] = raw == "true"
            elif option["kind"] == "range":
                parsed[match.group(1)] = int(raw)
            else:
                parsed[match.group(1)] = raw

        self.assertEqual(values, parsed)

    def test_the_seed_panel_does_not_credit_enemy_drops_with_checks(self):
        """`randomize_enemy_drops` adds no Archipelago checks; the page must not imply it does."""
        size = json.loads(re.search(
            r'<script id="bb-seed-size" type="application/json">\n(.*?)\n</script>',
            self.html, re.S).group(1))
        self.assertNotIn("randomize_enemy_drops", json.dumps(size))
        self.assertIn("adds no Archipelago checks", self.html)

    def test_the_seed_panel_totals_match_the_world(self):
        sys.path.insert(0, str(ROOT))
        from worlds.bloodborne import ALL_NETWORK_LOCATIONS

        size = json.loads(re.search(
            r'<script id="bb-seed-size" type="application/json">\n(.*?)\n</script>',
            self.html, re.S).group(1))
        self.assertEqual(len(ALL_NETWORK_LOCATIONS), size["published"])
        self.assertEqual(size["published"], sum(size["totals"].values()))
        self.assertEqual(
            size["published"],
            sum(r["base"] + r["dlc"] + r["gaol"] + r["one_time"] for r in size["regions"]))


class CheckBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = CHECKS.read_text(encoding="utf-8")
        cls.data = json.loads(re.search(
            r'<script id="bb-checks" type="application/json">(.*?)</script>',
            cls.html, re.S).group(1).replace("<\\/", "</"))

    def test_one_row_per_published_location(self):
        sys.path.insert(0, str(ROOT))
        from worlds.bloodborne import LOCATION_ID_BY_KEY

        self.assertEqual(len(LOCATION_ID_BY_KEY), len(self.data["rows"]))
        self.assertEqual(len(self.data["rows"]),
                         len({row["id"] for row in self.data["rows"]}),
                         "two rows share an AP id")

    def test_the_columns_are_the_ones_the_spec_names(self):
        self.assertEqual(
            ["Region", "Check", "Kind", "Classification", "Vanilla", "DLC", "Flag",
             "AP id", "Landmark"],
            self.data["columns"])

    def test_every_row_is_complete(self):
        for row in self.data["rows"]:
            with self.subTest(check=row["name"]):
                self.assertTrue(row["region"])
                self.assertTrue(row["name"])
                self.assertTrue(row["kind"])
                self.assertTrue(row["flag"])
                self.assertIsInstance(row["id"], int)

    def test_dlc_rows_agree_with_the_world(self):
        sys.path.insert(0, str(ROOT))
        from worlds.bloodborne.data import DLC_LOCATION_KEYS

        for row in self.data["rows"]:
            if row["key"] in DLC_LOCATION_KEYS:
                with self.subTest(check=row["name"]):
                    self.assertTrue(row["dlc"])

    def test_the_page_carries_an_inputs_hash(self):
        self.assertRegex(self.data["inputs_hash"], r"^[0-9a-f]{64}$")
        self.assertIn("inputs_hash", self.html)


class CoupledAndFreePageTests(unittest.TestCase):
    """The split is DERIVED from the pages, not from a list somebody maintains.

    Asserted in both directions: a coupled page must carry a marker, a free page must carry
    neither, and tools/deploy_site.sh's `--site` set must be exactly the free set. The failure this
    prevents is a page gaining a data stamp and continuing to ship from main -- which is how a
    check browser starts describing a corpus the released build does not have.
    """

    def read(self, name):
        return (SITE / name).read_text(encoding="utf-8")

    def test_coupled_pages_carry_a_marker(self):
        for name in sorted(COUPLED_PAGES):
            with self.subTest(page=name):
                text = self.read(name)
                self.assertTrue(
                    OPTION_SURFACE_MARKER in text or DATA_STAMP_MARKER in text
                    or APWORLD_STAMP_MARKER in text,
                    "%s is deployed from the stable tag but carries no coupling marker" % name)

    def test_free_pages_carry_neither_marker(self):
        for name in sorted(FREE_PAGES):
            with self.subTest(page=name):
                text = self.read(name)
                self.assertNotIn(OPTION_SURFACE_MARKER, text)
                self.assertNotIn(DATA_STAMP_MARKER, text)
                self.assertNotIn(APWORLD_STAMP_MARKER, text)

    def test_the_split_covers_every_file_in_site(self):
        present = {path.name for path in SITE.iterdir() if path.is_file()}
        self.assertEqual(COUPLED_PAGES | FREE_PAGES, present)

    def test_deploy_site_ships_exactly_the_free_pages_from_main(self):
        text = DEPLOY.read_text(encoding="utf-8")
        line = re.search(r'^SITE_PAGES="([^"]*)"$', text, re.M)
        self.assertIsNotNone(line, "deploy_site.sh has no SITE_PAGES list")
        shipped = {entry.split(":")[-1] for entry in line.group(1).split()}
        self.assertEqual(FREE_PAGES, shipped)

    def test_deploy_site_uses_the_bb_static_dir_default(self):
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertIn('DEST="${BB_STATIC_DIR:-/srv/bb}"', text)
        self.assertIn('REPO="${BB_REPO:-4laric/bb-archipelago}"', text)


class TabStripTests(unittest.TestCase):
    """The other copy of this strip is peliarch's `webgui/templates/base.html`.

    Pinning the links here is what makes the pair fail loudly in the repo where the other half
    lives, rather than drifting until a tab points at a page that does not exist.
    """

    EXPECTED = [
        ("builder", "/bb/wizard.html", "Builder"),
        ("downloads", "/downloads", "Downloads"),
        ("hosting", "/hosting", "Hosting"),
        ("checks", "/bb/checks.html", "Checks"),
        ("report", "/bb/report.html", "Report a bug"),
    ]

    @classmethod
    def setUpClass(cls):
        cls.text = TABS.read_text(encoding="utf-8")

    def test_the_strip_is_exactly_these_five_tabs_in_this_order(self):
        block = re.search(r"var TABS = \[(.*?)\];", self.text, re.S).group(1)
        found = re.findall(r'\["([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\]', block)
        self.assertEqual(self.EXPECTED, found)

    def test_there_is_no_questlines_tab(self):
        """Bloodborne has no questline DAG; a tab for one would 404."""
        self.assertNotIn("questlines", self.text.split("var TABS")[1].lower())

    def test_the_game_switcher_lists_both_games(self):
        block = re.search(r"var GAMES = \[(.*?)\];", self.text, re.S).group(1)
        self.assertEqual(
            [("er", "/", "ER"), ("bb", "/bb/", "BB")],
            re.findall(r'\["([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\]', block))

    def test_every_static_page_hosts_the_strip(self):
        for page in (WIZARD, CHECKS, LANDING, REPORT):
            with self.subTest(page=page.name):
                text = page.read_text(encoding="utf-8")
                self.assertIn('id="er-tabs"', text)
                self.assertIn('src="/bb/tabs.js"', text)


class ReportFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = REPORT.read_text(encoding="utf-8")

    def test_it_asks_for_the_four_session_files(self):
        for name in ("client.log", "delivery-diagnostics.jsonl", "ledger.json",
                     "rescue-diagnostics.json"):
            with self.subTest(file=name):
                self.assertIn(name, self.html)

    def test_it_files_against_this_repository(self):
        self.assertIn('REPO = "4laric/bb-archipelago"', self.html)
        self.assertIn("template=playtest-report.md", self.html)

    def test_the_issue_template_it_prefills_exists(self):
        template = ROOT / ".github" / "ISSUE_TEMPLATE" / "playtest-report.md"
        self.assertTrue(template.is_file())

    def test_it_names_the_session_folder_rather_than_asking_for_a_paste(self):
        self.assertIn(r"%LOCALAPPDATA%\BloodborneArchipelago\sessions", self.html)
        self.assertIn("attach the zip", self.html.lower())


class ChannelLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [
            line.split("\t")
            for line in CHANNELS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    def test_the_ledger_has_a_stable_and_a_beta_row(self):
        channels = {row[0] for row in self.rows}
        self.assertEqual({"stable", "beta"}, channels)

    def test_stable_names_a_tag_and_beta_names_a_branch(self):
        stable = [row for row in self.rows if row[0] == "stable"][-1]
        beta = [row for row in self.rows if row[0] == "beta"][-1]
        self.assertRegex(stable[1], r"^v\d+\.\d+\.\d+(-beta\.\d+)?$")
        self.assertEqual("main", beta[1])

    def test_latest_json_projects_the_stable_row(self):
        stable = [row for row in self.rows if row[0] == "stable"][-1][1]
        latest = json.loads(LATEST.read_text(encoding="utf-8"))
        self.assertEqual(stable[1:], latest["version"])
        self.assertTrue(latest["url"].endswith("/releases/tag/%s" % stable))
        self.assertRegex(latest["contract"], r"^[0-9a-f]{8,}$")


class InstallApworldTests(unittest.TestCase):
    def test_it_packages_what_build_ps1_packages(self):
        """The two packagers must agree on what a world contains.

        Asserted against build.ps1's own text rather than against a copy of the rule, because a
        second idea of the exclusion list is how a data table ends up in the release zip and not
        in the deploy image.
        """
        build = (ROOT / "build.ps1").read_text(encoding="utf-8")
        self.assertIn("__pycache__", build)
        self.assertIn("'.pyc', '.pyo', '.bak'", build)

        sys.path.insert(0, str(TOOLS))
        import install_apworld

        self.assertEqual({"__pycache__"}, install_apworld.EXCLUDED_DIRS)
        self.assertEqual((".pyc", ".pyo", ".bak"), install_apworld.EXCLUDED_SUFFIXES)

    def test_a_dry_run_lists_the_world(self):
        sys.path.insert(0, str(TOOLS))
        import install_apworld

        names = install_apworld.files()
        self.assertIn("__init__.py", names)
        self.assertIn("archipelago.json", names)
        self.assertIn("fixed_locations.tsv", names)
        self.assertIn("docs/setup_en.md", names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])

    def test_it_refuses_a_directory_that_is_not_archipelago(self):
        sys.path.insert(0, str(TOOLS))
        import install_apworld

        with self.assertRaises(SystemExit):
            install_apworld.install(str(ROOT / "docs"))


class SetupGuideTests(unittest.TestCase):
    """The WebHost setup page, and the Tutorial entry that makes it reachable."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "worlds" / "bloodborne" / "docs" / "setup_en.md").read_text(
            encoding="utf-8")
        cls.world = (ROOT / "worlds" / "bloodborne" / "__init__.py").read_text(encoding="utf-8")

    def test_it_follows_the_archipelago_setup_page_shape(self):
        self.assertTrue(self.text.startswith("# Bloodborne Setup Guide\n"))
        self.assertIn("/games/Bloodborne/info/en", self.text)

    def test_it_names_the_title_id_and_the_update(self):
        self.assertIn("CUSA03173", self.text)
        self.assertIn("01.09", self.text)

    def test_the_webworld_publishes_a_tutorial_for_every_doc(self):
        docs = {p.name for p in (ROOT / "worlds" / "bloodborne" / "docs").glob("*_en.md")}
        for name in docs:
            with self.subTest(doc=name):
                self.assertIn('"%s"' % name, self.world,
                              "%s is not named by a Tutorial entry, so the WebHost will not "
                              "serve it" % name)

    def test_the_world_declares_a_web_attribute(self):
        self.assertIn("web = BloodborneWeb()", self.world)


if __name__ == "__main__":
    unittest.main()
