import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from worlds.bloodborne.attire import ATTIRE_CATALOG
from worlds.bloodborne.insight_armor import build_insight_armor_suppression

ROOT = Path(__file__).resolve().parents[1]

class InsightPlanTests(unittest.TestCase):
    def test_complete_census_and_npc_exclusion(self):
        rows = build_insight_armor_suppression({p.item_key for p in ATTIRE_CATALOG})
        self.assertEqual(len(rows), 80)
        self.assertEqual(len({r['row_id'] for r in rows}), 80)
        self.assertEqual({r['qwc_id'] for r in rows}, {5910, 5090, 5091, 6675})
    def test_only_items_in_pool_are_suppressed(self):
        self.assertEqual(len(build_insight_armor_suppression(set())), 0)
        keys = {p.item_key for p in ATTIRE_CATALOG if not p.dlc}
        rows = build_insight_armor_suppression(keys)
        self.assertEqual(len(rows), 60)
        self.assertNotIn(6675, {r['qwc_id'] for r in rows})

@unittest.skipUnless(os.environ.get('BB_INSIGHT_WRITER'), 'requires compiled production writer')
class InsightWriterTests(unittest.TestCase):
    def test_real_binder_round_trip_and_drift_refusal(self):
        command = [os.environ.get('DOTNET_HOST', 'dotnet'), os.environ['BB_INSIGHT_WRITER']]
        def run(*args, ok=True):
            r = subprocess.run(command + list(map(str,args)), capture_output=True)
            if ok: self.assertEqual(r.returncode, 0, r.stderr.decode(errors='replace'))
            else: self.assertNotEqual(r.returncode, 0)
            return r.stdout.splitlines()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with sqlite3.connect(ROOT/'research/bb_inputs.db') as db:
                for name in ('gameparam.parambnd.dcx', 'paramdef.paramdefbnd.dcx'):
                    blob = db.execute('SELECT blob FROM files WHERE path = ?', ('parambnd/'+name,)).fetchone()
                    self.assertIsNotNone(blob)
                    (root/name).write_bytes(zlib.decompress(blob[0]))
            game, defs = root/'gameparam.parambnd.dcx', root/'paramdef.paramdefbnd.dcx'
            plan = build_insight_armor_suppression({p.item_key for p in ATTIRE_CATALOG})
            request, output = root/'request.json', root/'output.dcx'
            request.write_text(json.dumps({'insight_armor_suppression':plan}))
            before = run('--inspect-shops', game, defs)
            run('--seed-weapons', request, game, defs, output, '--apply')
            after = run('--inspect-shops', output, defs)
            ids = {r['row_id'] for r in plan}
            expected = [line for line in before if not (line.startswith(b'SHOP\t') and int(line.split(b'\t')[1]) in ids)]
            self.assertEqual(len(before)-len(after), 80)
            self.assertEqual(after, expected)
            bad = root/'bad.dcx'
            plan[0]['equip_id'] += 1
            request.write_text(json.dumps({'insight_armor_suppression':plan}))
            run('--seed-weapons', request, game, defs, bad, '--apply', ok=False)
            self.assertFalse(bad.exists())
