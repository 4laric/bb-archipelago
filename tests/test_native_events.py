"""Native recipe coverage, byte encoding and constructor composition controls."""
import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.bb_enemizer.native_events import NativeEventCatalog, fingerprint, compose_override


def instruction(value):
    return {'bank': 2000, 'id': 0, 'arg_data': base64.b64encode(bytes([value, 0, 0, 0])).decode(), 'layer': None}


def event(eid, values):
    return {'id': eid, 'rest_behavior': 0, 'parameters': [],
            'instructions': [instruction(value) for value in values], 'name': None}


class NativeEventTests(unittest.TestCase):
    def catalog(self, statements=None, events=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'catalog.json'
        path.write_text(json.dumps({'format': 'bb-native-event-catalog-v1', 'sources': {},
                                    'events': events or {}, 'statements': statements or {}}))
        return NativeEventCatalog(path)

    def test_catalog_covers_every_current_boss_route(self):
        from tools.build_boss_encounters import good_boss_routes
        catalog = NativeEventCatalog()
        self.assertEqual(good_boss_routes(), {tuple(pair) for pair in catalog.data['coverage']})
        self.assertTrue(catalog.data['sources'])
        self.assertTrue(catalog.data['events'])

    def test_current_adapter_bodies_have_native_templates(self):
        from functools import lru_cache
        from unittest.mock import patch
        import sys
        from tools.bb_enemizer.boss_canary import event_blocks
        from tools.build_boss_encounters import (
            ARENAS, PACKAGES, patch_pair_events, reusable_recipes, chalice_recipes,
        )
        catalog = NativeEventCatalog()
        texts = {name: '\n\n'.join(next(iter(variants.values())) for variants in events.values()) + '\n'
                 for name, events in catalog.data['sources'].items()}
        recipes = reusable_recipes()
        recipes.update(chalice_recipes())
        cached = lru_cache(maxsize=128)(event_blocks)
        modules = [m for name, m in list(sys.modules.items())
                   if name.startswith('tools.') and getattr(m, 'event_blocks', None) is event_blocks]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for module in modules:
                stack.enter_context(patch.object(module, 'event_blocks', lambda text: dict(cached(text))))
            for arena, donor in catalog.data['coverage']:
                with self.subTest(arena=arena, donor=donor):
                    before = texts[ARENAS[arena].event_file]
                    after = patch_pair_events(ARENAS[arena], PACKAGES[donor], texts, recipes, {}, materialized=True)
                    original = cached(before)
                    for eid, block in cached(after).items():
                        if eid != 0 and block != original.get(eid):
                            key = hashlib.sha256(block.encode()).hexdigest()
                            self.assertIn(key, catalog.data['events'], f'event {eid}: refresh native catalogue')
                            self.assertEqual(eid, catalog.data['events'][key]['id'])

    def test_constructor_edits_preserve_native_records_and_original_object(self):
        before = '$Event(0, Default, function() {\n    A();\n    B();\n});'
        after = '$Event(0, Default, function() {\n    Reset();\n    A();\n    C();\n});'
        native = event(0, [1, 2])
        original = copy.deepcopy(native)
        catalog = self.catalog({'A();': [instruction(1)], 'B();': [instruction(2)],
                                'C();': [instruction(3)], 'Reset();': [instruction(4)]})
        patched = catalog.constructor(native, before, after)
        self.assertEqual(event(0, [4, 1, 3]), patched)
        self.assertEqual(original, native)

    def test_constructor_refuses_ambiguous_witness_and_control_flow_edits(self):
        catalog = self.catalog({'A();': [instruction(1)]})
        before = '$Event(0, Default, function() {\n    A();\n});'
        after = '$Event(0, Default, function() {\n});'
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            catalog.constructor(event(0, [1, 1]), before, after)
        guarded = '$Event(0, Default, function() {\n    if (x) {\n        A();\n    }\n});'
        with self.assertRaisesRegex(ValueError, 'guarded control flow'):
            catalog.constructor(event(0, [1]), guarded, guarded.replace('        A();\n', ''))

    def test_recipe_rejects_unreviewed_events_and_protected_progression(self):
        before = '$Event(7, Default, function() {\n    A();\n});'
        after = before.replace('A();', 'B();')
        native = {'sha256': 'a' * 64, 'events': [event(7, [1])]}
        with self.assertRaisesRegex(ValueError, 'no reviewed native recipe'):
            self.catalog().recipe(native, before, after, [])
        key = hashlib.sha256(after.encode()).hexdigest()
        catalog = self.catalog(events={key: event(7, [2])})
        with self.assertRaisesRegex(ValueError, 'protected progression'):
            catalog.recipe(native, before, after, [7])
        request = catalog.recipe(native, before, after, [])
        self.assertEqual({"7": fingerprint(event(7, [2]))}, request['fingerprints'])

    def test_guarded_tail_insertion_relocates_skips_and_composes_ap_prefix(self):
        skip = {'bank': 1003, 'id': 1, 'arg_data': base64.b64encode(bytes([2]) + bytes(7)).decode(), 'layer': None}
        jump = {'bank': 1000, 'id': 3, 'arg_data': base64.b64encode(bytes([1, 0, 0, 0])).decode(), 'layer': None}
        native = event(0, [])
        native['instructions'] = [skip, instruction(1), jump, instruction(2), instruction(3)]
        before = '$Event(0, Default, function() {\n    if (x) {\n        A();\n    } else {\n        B();\n    }\n    C();\n});'
        after = before.replace('    } else {', '    New();\n    } else {')
        catalog = self.catalog({'A();': [instruction(1)], 'B();': [instruction(2)],
                                'C();': [instruction(3)], 'New();': [instruction(4)]})
        patched = catalog.constructor(native, before, after)
        self.assertEqual(instruction(4), patched['instructions'][2])
        self.assertEqual(3, base64.b64decode(patched['instructions'][0]['arg_data'])[0])
        self.assertEqual(jump, patched['instructions'][3])
        ap = copy.deepcopy(native)
        ap['instructions'].insert(0, instruction(5))
        combined = compose_override({'events': [native]}, {'events': [patched], 'protected_events': []},
                                    {'events': [ap]})['events'][0]
        self.assertEqual(instruction(5), combined['instructions'][0])
        self.assertEqual(patched['instructions'], combined['instructions'][1:])

    def test_ap_and_boss_constructor_insertions_compose_and_conflicts_refuse(self):
        original = {'sha256': 'a' * 64, 'events': [event(0, [1, 2]), event(7, [3])]}
        boss = {'events': [event(0, [4, 1, 2, 5])], 'protected_events': [7]}
        override = {'events': [event(0, [6, 1, 2]), event(7, [3])]}
        combined = compose_override(original, boss, override)
        self.assertEqual(event(0, [4, 6, 1, 2, 5]), combined['events'][0])
        with self.assertRaisesRegex(ValueError, 'protected boss progression'):
            compose_override(original, boss, {'events': [event(0, [1, 2]), event(7, [9])]})
        with self.assertRaisesRegex(ValueError, 'overlap event 7'):
            compose_override(original, {'events': [event(7, [8])], 'protected_events': []},
                             {'events': [event(0, [1, 2]), event(7, [9])]})

    def test_unknown_source_events_are_preserved_as_opaque_witnesses(self):
        native_event = event(8, [1])
        source = self.catalog().source('test.js', {'events': [native_event],
                                                 'fingerprints': {'8': fingerprint(native_event)}})
        self.assertIn('Unmodified native event', source)
        with self.assertRaisesRegex(ValueError, 'readback fingerprint differs'):
            self.catalog().source('test.js', {'events': [native_event], 'fingerprints': {'8': 'b' * 64}})
