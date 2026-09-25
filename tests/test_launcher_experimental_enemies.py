"""Experimental modes must compose, survive cache reuse, and roll back cleanly."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher.core import BOSS_EVENT_PATH, SUPPRESSION_PATH, SeedCache, ValidationError, sha256_file
from bb_launcher.workflow import (
    EnemizerBuild, EnemizerOptions, EnemizerToolchain, LauncherWorkflow,
    chalice_map_sources, encounter_character_sources, encounter_event_sources,
    encounter_sfx_sources,
)
from test_launcher_core import write_boss_encounter_overlay
import test_launcher_ui as fixtures
from tools.bb_enemizer.chalice_recipes import chalice_recipes, source_manifest


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


class ReviewedBossToolchain(fixtures.FakeToolchain):
    """A native-builder boundary fixture: core still verifies its real receipt."""
    def __init__(self, tools: Path):
        super().__init__()
        self.tools = tools
        self.tools.mkdir()
        (self.tools / 'BBBossEncounterBuilder.exe').write_bytes(b'boss-builder')
        (self.tools / 'BBEnemizerWriter.exe').write_bytes(b'boss-writer')
        (self.tools / 'BBEnemizerPlanner.exe').write_bytes(b'boss-planner')
        (self.tools / 'BBEventWriter.exe').write_bytes(b'boss-event-writer')

    @property
    def boss_encounter_builder_executable(self):
        return self.tools / 'BBBossEncounterBuilder.exe'

    @property
    def writer_executable(self):
        return self.tools / 'BBEnemizerWriter.exe'

    def boss_encounter_identity_inputs(self, inventory):
        if inventory is None:
            raise AssertionError('reviewed fixture expects its explicit inventory')
        return {
            'launcher-tools/boss-builder.exe': self.boss_encounter_builder_executable,
            'launcher-tools/boss-writer.exe': self.writer_executable,
            'launcher-tools/boss-planner.exe': self.tools / 'BBEnemizerPlanner.exe',
            'launcher-tools/boss-event-writer.exe': self.tools / 'BBEventWriter.exe',
            'launcher-input/enemy-inventory.tsv': inventory,
            'launcher-tools/boss-inputs.db': Path(__file__).resolve().parents[1] / 'research/bb_inputs.db',
        }

    def build_boss_encounters(self, *, input_binder, **values):
        self.calls.append(values)
        overlay = write_boss_encounter_overlay(
            values['output_root'], source_binder=input_binder, seed=values['seed'],
            cathedral_input=b'verified-cathedral-overlay',
        )
        plan = json.loads((overlay / 'bb-enemizer-plan.json').read_text())
        return EnemizerBuild(
            overlay / 'dvdroot_ps4/map/MapStudio', plan,
            sha256_file(overlay / 'bb-enemizer-plan.json'),
            overlay / 'bb-enemizer-plan.json', overlay,
        )


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

    def seed_good_pool_inputs(self):
        install = self.fixture.install
        donors = {donor for _arena, donor in chalice_recipes()}
        self.assertEqual(9, len(donors))
        for donor in donors:
            source = source_manifest(donor)
            event = Path('dvdroot_ps4/event') / source['event_file']
            map_name = source['source_map']
            map_path = Path('dvdroot_ps4/map/MapStudio') / f'{map_name[:-2]}00' / f'{map_name}.msb.dcx'
            for relative in (event, map_path):
                target = install.base / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f'base {donor} {relative.name}'.encode())
        for relative, content in (
            ('dvdroot_ps4/event/m29.emevd.dcx', b'base chalice constructor'),
            ('dvdroot_ps4/chr/c5010.anibnd.dcx', b'base watchdog character'),
            ('dvdroot_ps4/sfx/frpg_sfxbnd_m29a.ffxbnd.dcx', b'base chalice effects'),
        ):
            target = install.base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return donors

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

    def test_reviewed_pool_uses_one_native_overlay_and_keeps_unaffected_ap_events(self):
        compiler = self.fixture.root / 'DarkScript3.exe'
        compiler.write_bytes(b'pinned compiler')
        tools = ReviewedBossToolchain(self.fixture.root / 'reviewed-tools')
        workflow = LauncherWorkflow(
            self.fixture.repo, toolchain=tools,
            process_launcher=lambda _: [fixtures.Process(10), fixtures.Process(11)],
        )
        from unittest.mock import patch
        with patch('bb_launcher.boss_compiler.ensure_boss_compiler', return_value=compiler):
            result = workflow.randomize_and_launch(
                self.fixture.settings(), EnemizerOptions(boss_pool='reviewed'),
                process_is_running=lambda: False,
            )
        identity = result.build_path.joinpath('seed-manifest.json').read_text()
        self.assertIn('"boss_encounters": true', identity)
        self.assertEqual('reviewed', json.loads(identity)['identity']['options']['boss_pool'])
        self.assertEqual(b'cleric-event', (self.fixture.install.mods / BOSS_EVENT_PATH).read_bytes())
        # The generic receipt binds the original AP Cathedral hash, and the
        # active file is the native-composed replacement rather than a second
        # launcher-side copy of that input.
        from bb_launcher.core import CATHEDRAL_EVENT_PATH, COMMON_EVENT_PATH
        self.assertEqual(b'native-composed-cathedral-plus-boss',
                         (self.fixture.install.mods / CATHEDRAL_EVENT_PATH).read_bytes())
        self.assertEqual(b'verified-common-overlay',
                         (self.fixture.install.mods / COMMON_EVENT_PATH).read_bytes())
        self.assertEqual(1, len(tools.calls))
        self.assertEqual('reviewed', tools.calls[0]['options'].boss_pool)
        effects = self.fixture.install.mods / 'dvdroot_ps4/sfx/frpg_sfxbnd_m34.ffxbnd.dcx'
        self.assertEqual(b'merged-map-effects', effects.read_bytes())
        workflow.randomize_and_launch(self.fixture.settings(), EnemizerOptions(),
                                     process_is_running=lambda: False)
        self.assertFalse(effects.exists())

    def test_reviewed_pool_rejects_legacy_canary_mix(self):
        with self.assertRaisesRegex(ValidationError, 'cannot be combined'):
            self.launch(boss_canary=True, boss_pool='reviewed')

    def test_effect_banks_resolve_per_file_without_active_mod_inputs(self):
        install = self.fixture.install
        names = ['frpg_sfxbnd_m34.ffxbnd.dcx', 'frpg_sfxbnd_m35.ffxbnd.dcx']
        for root, files in ((install.base, names), (install.patch, names[:1]), (install.mods, names)):
            directory = root / 'dvdroot_ps4/sfx'
            directory.mkdir(parents=True, exist_ok=True)
            for name in files:
                (directory / name).write_bytes(str(root).encode())
            (directory / 'frpg_sfxbnd_common.ffxbnd.dcx').write_bytes(b'unrelated')
        self.assertEqual({
            'dvdroot_ps4/sfx/' + names[0]: install.patch / 'dvdroot_ps4/sfx' / names[0],
            'dvdroot_ps4/sfx/' + names[1]: install.base / 'dvdroot_ps4/sfx' / names[1],
        }, encounter_sfx_sources(install))

    def test_reviewed_cache_changes_when_original_effect_bank_changes(self):
        compiler = self.fixture.root / 'DarkScript3.exe'
        compiler.write_bytes(b'pinned compiler')
        bank = self.fixture.install.base / 'dvdroot_ps4/sfx/frpg_sfxbnd_m35.ffxbnd.dcx'
        bank.parent.mkdir(parents=True)
        bank.write_bytes(b'original effects')
        tools = ReviewedBossToolchain(self.fixture.root / 'reviewed-tools')
        workflow = LauncherWorkflow(self.fixture.repo, toolchain=tools,
            process_launcher=lambda _: [fixtures.Process(10), fixtures.Process(11)])
        from unittest.mock import patch
        with patch('bb_launcher.boss_compiler.ensure_boss_compiler', return_value=compiler):
            def launch():
                return workflow.randomize_and_launch(self.fixture.settings(),
                    EnemizerOptions(boss_pool='reviewed'), process_is_running=lambda: False)
            original = launch()
            reused = launch()
            self.assertEqual(original.cache_key, reused.cache_key)
            self.assertTrue(reused.reused)
            bank.write_bytes(b'updated original effects')
            changed = launch()
        self.assertNotEqual(original.cache_key, changed.cache_key)
        self.assertFalse(changed.reused)
        manifest = json.loads((changed.build_path / 'seed-manifest.json').read_text())
        self.assertEqual(sha256_file(bank), manifest['identity']['source_hashes'][
            'dvdroot_ps4/sfx/frpg_sfxbnd_m35.ffxbnd.dcx'])

    def test_good_pool_selects_exact_chalice_sources_and_never_reads_mods(self):
        donors = self.seed_good_pool_inputs()
        install = self.fixture.install
        selected = source_manifest('watchdog-of-the-old-lords')
        event_key = 'dvdroot_ps4/event/' + selected['event_file']
        map_name = selected['source_map']
        map_key = f'dvdroot_ps4/map/MapStudio/{map_name[:-2]}00/{map_name}.msb.dcx'
        for relative in (event_key, map_key, 'dvdroot_ps4/chr/c5010.anibnd.dcx',
                         'dvdroot_ps4/sfx/frpg_sfxbnd_m29a.ffxbnd.dcx'):
            patched = install.patch / relative
            patched.parent.mkdir(parents=True, exist_ok=True)
            patched.write_bytes(b'official update ' + relative.encode())
            modded = install.mods / relative
            modded.parent.mkdir(parents=True, exist_ok=True)
            modded.write_bytes(b'active mod ' + relative.encode())
        unrelated = install.base / 'dvdroot_ps4/event/m29_99_99_00/unselected.emevd.dcx'
        unrelated.parent.mkdir(parents=True)
        unrelated.write_bytes(b'unselected source')
        events = encounter_event_sources(install, chalice=True)
        maps = chalice_map_sources(install)
        characters = encounter_character_sources(install)
        effects = encounter_sfx_sources(install)
        self.assertEqual({source_manifest(d)['event_file'] for d in donors},
                         {key.split('dvdroot_ps4/event/', 1)[1] for key in events
                          if key.startswith('dvdroot_ps4/event/m29_')})
        self.assertEqual(9, len(maps))
        self.assertEqual(install.base / 'dvdroot_ps4/event/m29.emevd.dcx',
                         events['dvdroot_ps4/event/m29.emevd.dcx'])
        for key, sources in ((event_key, events), (map_key, maps),
                             ('dvdroot_ps4/chr/c5010.anibnd.dcx', characters),
                             ('dvdroot_ps4/sfx/frpg_sfxbnd_m29a.ffxbnd.dcx', effects)):
            self.assertEqual(install.patch / key, sources[key])
        self.assertNotIn('dvdroot_ps4/event/m29_99_99_00/unselected.emevd.dcx', events)

    def test_good_pool_forwards_mode_and_pins_original_chalice_inputs(self):
        self.seed_good_pool_inputs()
        install = self.fixture.install
        selected = source_manifest('watchdog-of-the-old-lords')
        key = 'dvdroot_ps4/event/' + selected['event_file']
        patched = install.patch / key
        patched.parent.mkdir(parents=True, exist_ok=True)
        patched.write_bytes(b'official constructor v1')
        compiler = self.fixture.root / 'DarkScript3.exe'
        compiler.write_bytes(b'pinned compiler')
        tools = ReviewedBossToolchain(self.fixture.root / 'good-tools')
        workflow = LauncherWorkflow(self.fixture.repo, toolchain=tools,
            process_launcher=lambda _: [fixtures.Process(10), fixtures.Process(11)])
        with patch('bb_launcher.boss_compiler.ensure_boss_compiler', return_value=compiler):
            def launch():
                return workflow.randomize_and_launch(self.fixture.settings(),
                    EnemizerOptions(boss_pool='good'), process_is_running=lambda: False)
            first = launch()
            reused = launch()
            self.assertTrue(reused.reused)
            self.assertEqual(first.cache_key, reused.cache_key)
            patched.write_bytes(b'official constructor v2')
            changed = launch()
        self.assertEqual(2, len(tools.calls))
        self.assertTrue(all(call['options'].boss_pool == 'good' for call in tools.calls))
        self.assertFalse(changed.reused)
        self.assertNotEqual(first.cache_key, changed.cache_key)
        identity = json.loads((changed.build_path / 'seed-manifest.json').read_text())['identity']
        self.assertEqual('good', identity['options']['boss_pool'])
        self.assertEqual(sha256_file(patched), identity['source_hashes'][key])
        self.assertIn('dvdroot_ps4/event/m29.emevd.dcx', identity['source_hashes'])
        self.assertIn('dvdroot_ps4/chr/c5010.anibnd.dcx', identity['source_hashes'])

    def test_good_builder_stages_nested_originals_and_passes_selected_pool(self):
        self.seed_good_pool_inputs()
        install = self.fixture.install
        selected = source_manifest('beast-possessed-soul')
        event_relative = 'dvdroot_ps4/event/' + selected['event_file']
        source = install.patch / event_relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b'updated original BPS constructor')
        modded = install.mods / event_relative
        modded.parent.mkdir(parents=True, exist_ok=True)
        modded.write_bytes(b'modded constructor')
        compiler = self.fixture.root / 'DarkScript3.exe'
        compiler.write_bytes(b'pinned compiler')
        tool_root = self.fixture.root / 'builder-tools'
        builder = tool_root / 'tools/BBBossEncounterBuilder/BBBossEncounterBuilder.exe'
        writer = tool_root / 'tools/BBEnemizerWriter.exe'
        for executable in (builder, writer):
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b'tool')
        commands = []

        def runner(command, _cwd, _progress):
            commands.append(command)
            args = {command[index]: command[index + 1]
                    for index in range(len(command) - 1) if command[index].startswith('--')}
            self.assertEqual('good', args['--pool'])
            self.assertEqual(b'updated original BPS constructor',
                             (Path(args['--events']) / selected['event_file']).read_bytes())
            map_name = selected['source_map']
            self.assertTrue((Path(args['--maps']) / f'{map_name[:-2]}00' / f'{map_name}.msb.dcx').is_file())
            self.assertEqual(b'base watchdog character',
                             (Path(args['--characters']) / 'c5010.anibnd.dcx').read_bytes())
            output = Path(args['--output'])
            output.mkdir()
            (output / 'boss-encounters-report.json').write_text(json.dumps({
                'format': 'bb-boss-encounters-v1', 'applied': True, 'files': [{'path': 'fixture'}]}))
            (output / 'bb-enemizer-plan.json').write_text('{}')

        toolchain = EnemizerToolchain(self.fixture.repo, app_root=tool_root, runner=runner)
        def ordinary_plan(**kwargs):
            path = kwargs['output_root'] / 'ordinary-plan.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
            return EnemizerBuild(self.fixture.maps, {}, sha256_file(path), path)
        with patch.object(toolchain, 'build', side_effect=ordinary_plan):
            toolchain.build_boss_encounters(
                options=EnemizerOptions(boss_pool='good'), install=install,
                input_binder=self.fixture.suppression, darkscript=compiler, event_overrides={},
                output_root=self.fixture.root / 'direct-good', map_studio_source=self.fixture.maps,
                seed='fixture:1', progress=lambda _: None,
            )
        self.assertEqual(1, len(commands))


if __name__ == '__main__':
    unittest.main()
