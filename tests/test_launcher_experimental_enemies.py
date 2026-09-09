"""Experimental modes must compose, survive cache reuse, and roll back cleanly."""
import json
import unittest
from pathlib import Path

from bb_launcher.core import BOSS_EVENT_PATH, SUPPRESSION_PATH, SeedCache, ValidationError, sha256_file
from bb_launcher.workflow import EnemizerBuild, EnemizerOptions, LauncherWorkflow
import test_launcher_ui as fixtures


class ExperimentalToolchain(fixtures.FakeToolchain):
    def build_experimental(self, *, options, install, input_binder, **values):
        planned = self.build(**values)
        root = values['output_root'] / 'experimental-overlay'
        maps = root / 'dvdroot_ps4/map/MapStudio'
        maps.mkdir(parents=True)
        for source in planned.map_studio.iterdir():
            (maps / source.name).write_bytes(source.read_bytes())
        binder = root / SUPPRESSION_PATH
        binder.parent.mkdir(parents=True)
        binder.write_bytes(input_binder.read_bytes() + b'-normalized')
        scripts = root / 'dvdroot_ps4/script'
        scripts.mkdir()
        ai_file = scripts / 'm24_01_00_00.luabnd.dcx'
        ai_file.write_bytes(b'experimental-ai')
        plan = dict(planned.manifest)
        plan['scaling'] = {'enabled': True, 'applied': True}
        path = root / 'bb-enemizer-plan.json'
        path.write_text(json.dumps(plan))
        def save(name, value):
            (root / name).write_text(json.dumps(value))
        save('scaling-report.json', {'applied': True, 'output_plan_sha256': sha256_file(path),
             'output_gameparam_sha256': sha256_file(binder)})
        save('dvdroot_ps4/script.json', {'applied': True, 'plan_sha256': sha256_file(path),
             'maps': [{'map': ai_file.name, 'output_sha256': sha256_file(ai_file), 'missing_goals_after': 0}]})
        if options.boss_canary:
            event = root / BOSS_EVENT_PATH
            event.parent.mkdir()
            event.write_bytes(b'bsb-encounter')
            files = [p for p in root.rglob('*') if p.is_file()]
            save('boss-adapter-report.json', {'adapter': 'bsb-at-cleric-v1', 'applied': True,
                 'completion_event': 12411700, 'output_event_sha256': sha256_file(event),
                 'files': [{'path': p.relative_to(root).as_posix(), 'sha256': sha256_file(p)} for p in files]})
        return EnemizerBuild(maps, plan, sha256_file(path), path, root)


class ExperimentalLauncherTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LauncherUiWorkflowTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        event = self.fixture.install.patch / BOSS_EVENT_PATH
        event.write_bytes(b'original-cleric')
        self.tools = ExperimentalToolchain()
        self.workflow = LauncherWorkflow(self.fixture.repo, toolchain=self.tools,
                                         process_launcher=lambda _: [fixtures.Process(10), fixtures.Process(11)])

    def launch(self, **options):
        return self.workflow.randomize_and_launch(self.fixture.settings(), EnemizerOptions(**options),
                                                  process_is_running=lambda: False)

    def test_switching_boss_scaling_and_normal_modes_changes_cache_and_restores_event(self):
        boss = self.launch(boss_canary=True)
        self.assertEqual(b'bsb-encounter', (self.fixture.install.mods / BOSS_EVENT_PATH).read_bytes())
        self.assertTrue((self.fixture.install.mods / SUPPRESSION_PATH).read_bytes().endswith(b'-normalized'))
        reused = self.launch(boss_canary=True)
        self.assertEqual(boss.cache_key, reused.cache_key)
        self.assertTrue(reused.reused)
        scaled = self.launch(normalize_scaling=True)
        self.assertFalse((self.fixture.install.mods / BOSS_EVENT_PATH).exists())
        normal = self.launch()
        self.assertFalse((self.fixture.install.mods / SUPPRESSION_PATH).read_bytes().endswith(b'-normalized'))
        self.assertEqual(3, len({boss.cache_key, scaled.cache_key, normal.cache_key}))
        self.assertEqual(b'original-cleric', (self.fixture.install.patch / BOSS_EVENT_PATH).read_bytes())

    def test_cache_rejects_missing_boss_receipt_and_mixed_scaling_plan(self):
        result = self.launch(boss_canary=True)
        path = result.build_path / 'seed-manifest.json'
        original = json.loads(path.read_text())
        modified = json.loads(path.read_text())
        modified['enemizer']['boss'] = None
        path.write_text(json.dumps(modified))
        with self.assertRaisesRegex(ValidationError, 'boss option, event and receipt'):
            SeedCache(result.build_path.parent).verify(result.build_path)
        original['enemizer']['scaling']['output_plan_sha256'] = '0' * 64
        path.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValidationError, 'normalization receipt mismatch'):
            SeedCache(result.build_path.parent).verify(result.build_path)


if __name__ == '__main__':
    unittest.main()
