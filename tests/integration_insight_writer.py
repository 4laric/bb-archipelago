import dataclasses
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from tests.test_insight_armor import ROOT, ATTIRE_CATALOG, build_insight_armor_suppression
from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

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
            # The award table rides along so this real-binder run exercises the
            # category-8 path against vanilla ItemLotParam rows, including the
            # Beast rune award whose source lot keeps its recipe in slot 02.
            awards = [dataclasses.asdict(a) for a in CATEGORY8_AWARDS]
            self.assertTrue(any(
                a['item_key'] == 'category8_cathedral_ward_avatar_beast_rune'
                for a in awards))
            body = {'insight_armor_suppression':plan, 'category8_awards':awards}
            request.write_text(json.dumps(body))
            before = run('--inspect-shops', game, defs)
            run('--seed-weapons', request, game, defs, output, '--apply')
            after = run('--inspect-shops', output, defs)
            ids = {r['row_id'] for r in plan}
            expected = [line for line in before if not (line.startswith(b'SHOP\t') and int(line.split(b'\t')[1]) in ids)]
            self.assertEqual(len(before)-len(after), 80)
            self.assertEqual(after, expected)
            bad = root/'bad.dcx'
            plan[0]['equip_id'] += 1
            request.write_text(json.dumps({**body, 'insight_armor_suppression':plan}))
            run('--seed-weapons', request, game, defs, bad, '--apply', ok=False)
            self.assertFalse(bad.exists())
