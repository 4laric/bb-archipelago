"""The launcher must deliver AI together with randomized maps, including on reuse."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from bb_launcher.core import (AI_PREFIX, SEED_MANIFEST_NAME, SeedCache, ValidationError,
                              activate_build, deactivate_overlay, sha256_file)
from bb_launcher.workflow import EnemizerToolchain, enemy_ai_sources
from tests.test_launcher_core import identity, make_install, sample_plan


class EnemyAiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = make_install(self.root / "game")
        self.maps = self.root / "maps"
        self.maps.mkdir()
        for state in ("00", "01"):
            (self.maps / f"m24_01_00_{state}.msb.dcx").write_bytes(b"map" + state.encode())
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.ai_name = "m24_01_00_00.luabnd.dcx"
        (self.scripts / self.ai_name).write_bytes(b"repaired-ai")
        self.binder = self.root / "gameparam"
        self.binder.write_bytes(b"binder")
        self.identity = identity("ai", b"binder", enemizer_seed="ai",
                                 options={"enemy_randomizer": True, "enemy_ai_version": 1})
        self.cache = SeedCache(self.root / "cache")
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps(sample_plan("ai")), encoding="utf-8")

    def build(self):
        return self.cache.build(self.identity, self.binder, self.maps,
                                enemy_scripts=self.scripts, enemizer_plan=self.plan)

    def test_ai_is_cached_activated_and_removed_with_maps(self):
        result = self.build()
        self.assertEqual(result.manifest["enemizer"]["ai_file_count"], 1)
        activate_build(self.install, result.path, process_is_running=lambda: False)
        installed = self.install.mods / AI_PREFIX / self.ai_name
        self.assertEqual(installed.read_bytes(), b"repaired-ai")
        self.assertTrue(self.build().reused)
        deactivate_overlay(self.install, process_is_running=lambda: False)
        self.assertFalse(installed.exists())

    def test_ai_contract_changes_old_cache_identity(self):
        old = replace(self.identity, options={"enemy_randomizer": True})
        self.assertNotEqual(old.cache_key, self.identity.cache_key)

    def test_map_only_build_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "matching enemy AI"):
            self.cache.build(self.identity, self.binder, self.maps, enemizer_plan=self.plan)

    def test_relabeling_or_removing_ai_cannot_pass_cache_verification(self):
        result = self.build()
        manifest_path = result.path / SEED_MANIFEST_NAME
        original = json.loads(manifest_path.read_text())
        for mutation in ("remove", "component"):
            with self.subTest(mutation=mutation):
                manifest = json.loads(json.dumps(original))
                record = next(r for r in manifest["files"] if r["component"] == "enemizer-ai")
                if mutation == "component":
                    record["component"] = "enemizer"
                else:
                    manifest["files"].remove(record)
                    manifest["enemizer"]["ai_file_count"] = 0
                    (result.path / record["path"]).unlink()
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(ValidationError):
                    self.cache.verify(result.path)
                (result.path / record["path"]).write_bytes(b"repaired-ai")

    def test_resolves_update_per_file_and_ignores_active_mods(self):
        for layer, names in ((self.install.base, {self.ai_name: b"base", "aicommon.luabnd.dcx": b"common"}),
                             (self.install.patch, {self.ai_name: b"patch"}),
                             (self.install.mods, {self.ai_name: b"mod"})):
            directory = layer / AI_PREFIX
            directory.mkdir(parents=True)
            for name, data in names.items():
                (directory / name).write_bytes(data)
        sources = enemy_ai_sources(self.install)
        self.assertEqual(sources[AI_PREFIX + self.ai_name].read_bytes(), b"patch")
        self.assertEqual(sources[AI_PREFIX + "aicommon.luabnd.dcx"].read_bytes(), b"common")

    def test_toolchain_checks_ai_report_and_output_hashes(self):
        directory = self.install.base / AI_PREFIX
        directory.mkdir(parents=True)
        for name in (self.ai_name, "aicommon.luabnd.dcx"):
            (directory / name).write_bytes(name.encode())
        for path in ("param/gameparam/gameparam.parambnd.dcx", "paramdef/paramdef.paramdefbnd.dcx"):
            source = self.install.base / "dvdroot_ps4" / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"params")
        commands = []
        def runner(command, cwd, progress):
            commands.append(command)
            index = command.index("--ai")
            plan_path = Path(command[index + 1])
            output = Path(command[index + 5])
            output.mkdir()
            (output / self.ai_name).write_bytes(b"ai")
            report = {"format": "bb-enemizer-ai-v1", "applied": True,
                      "plan_sha256": sha256_file(plan_path), "maps": [{
                          "map": self.ai_name, "missing_goals_after": 0,
                          "output_sha256": sha256_file(output / self.ai_name)}]}
            output.with_suffix(".json").write_text(json.dumps(report))
        output_root = self.root / "build"
        output_root.mkdir()
        tool = EnemizerToolchain(Path(__file__).resolve().parents[1], runner=runner, app_root=self.root)
        output = tool.write_enemy_ai(manifest={"swaps": []}, install=self.install,
                                    output_root=output_root, soulsformats_next=self.root, progress=lambda _: None)
        self.assertEqual((output / self.ai_name).read_bytes(), b"ai")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][-1], "--apply")


if __name__ == "__main__":
    unittest.main()
