"""Native writer integration against user-owned original game data.

BB_STANDALONE_WRITER_INPUTS points to a JSON object containing writer,
gameparam and paramdef paths. No game directory or save is modified.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.apply_vanilla_suppression import read_params

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = os.environ.get("BB_STANDALONE_WRITER_INPUTS")


@unittest.skipUnless(MANIFEST, "requires original standalone writer inputs")
class StandaloneItemWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = json.loads(Path(MANIFEST).read_text(encoding="utf-8"))
        cls.source_hash = hashlib.sha256(Path(cls.inputs["gameparam"]).read_bytes()).hexdigest()
        rows = csv.DictReader(io.StringIO(read_params(ROOT / "research/bb_inputs.db")))
        cls.sources = []
        for row in rows:
            if (int(row["getItemFlagId"]) > 0 and row["lotItemCategory01"] == "4"
                    and int(row["lotItemId01"]) > 0 and int(row["lotItemNum01"]) > 0):
                cls.sources.append({"item_lot_id": int(row["ID"]), "slot": 1, "role": "delivery",
                    "source": {"item_category": 4, "item_id": int(row["lotItemId01"]),
                               "quantity": int(row["lotItemNum01"]),
                               "acquisition_flag": int(row["getItemFlagId"])}})
            if len(cls.sources) == 3:
                break
        assert len(cls.sources) == 3

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        targets = copy.deepcopy(self.sources)
        targets[1]["role"] = "alternative"
        targets[2]["role"] = "retire"
        self.plan = {
            "format": "bb-standalone-item-plan-v1", "seed": "native-reward-regression",
            "generator_build": "test", "options": {}, "catalog_sha256": "1" * 64,
            "source_hashes": {"dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx": self.source_hash,
                "dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx": hashlib.sha256(
                    Path(self.inputs["paramdef"]).read_bytes()).hexdigest()},
            "unsupported": [], "placements": [{"location_key": "fixture", "item_key": "fixture",
                "reward": {"item_category": 4, "item_id": self.sources[0]["source"]["item_id"],
                           "quantity": 2}, "award_targets": targets}],
        }

        self.catalog = {
            "format": "bb-standalone-award-target-catalog-v1",
            "entries": [{"location_key": "fixture", "status": "placeable", "when": {},
                         "targets": copy.deepcopy(targets)}],
            "items": [{"item_key": "fixture", "reward": copy.deepcopy(self.plan["placements"][0]["reward"])}],
        }
        self.save_catalog()

    def save_catalog(self):
        raw = json.dumps(self.catalog).encode("utf-8")
        (self.root / "catalog.json").write_bytes(raw)
        self.plan["catalog_sha256"] = hashlib.sha256(raw).hexdigest()

    def invoke(self, label="output"):
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        output = self.root / f"{label}.parambnd.dcx"
        result = subprocess.run([
            "dotnet", "--roll-forward", "Major", self.inputs["writer"], "--standalone-items",
            str(plan_path), str(self.root / "catalog.json"), self.inputs["gameparam"], self.inputs["paramdef"], str(output), "--apply",
        ], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(hashlib.sha256(Path(self.inputs["gameparam"]).read_bytes()).hexdigest(),
                         self.source_hash)
        return result, output

    def assert_refused(self, message):
        result, output = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".standalone-items-*")))

    def test_delivery_alternative_and_retirement_round_trip_preserves_unrelated_data(self):
        result, output = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["award_targets"], 3)
        self.assertEqual(receipt["locations"], 1)
        self.assertEqual(receipt["source_sha256"], self.source_hash)
        self.assertEqual(receipt["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertNotEqual(receipt["output_sha256"], self.source_hash)
        self.assertFalse(receipt["runtime_validated"])
        before = output.read_bytes()
        retry, same_output = self.invoke()
        self.assertNotEqual(retry.returncode, 0)
        self.assertEqual(same_output.read_bytes(), before)

    def test_source_archive_and_award_witness_drift_are_refused_before_output(self):
        original = copy.deepcopy(self.plan)
        self.plan["source_hashes"]["dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"] = "0" * 64
        self.assert_refused("hash mismatch")
        self.plan = original
        self.plan["placements"][0]["award_targets"][1]["source"]["acquisition_flag"] += 1
        self.assert_refused("award targets differ from catalog")

    def test_duplicate_target_or_unresolved_location_is_refused(self):
        original = copy.deepcopy(self.plan)
        placement = self.plan["placements"][0]
        duplicate = copy.deepcopy(placement["award_targets"][0])
        duplicate["role"] = "alternative"
        placement["award_targets"].append(duplicate)
        self.assert_refused("award targets differ from catalog")
        self.plan = original
        self.plan["unsupported"] = [{"location_key": "missing"}]
        self.assert_refused("unresolved award targets")

    def test_virtual_reward_and_quantity_overflow_are_refused_without_partial_output(self):
        reward = self.plan["placements"][0]["reward"]
        reward["item_category"] = 255
        self.assert_refused("item reward differs from catalog")
        reward["item_category"] = 4
        reward["quantity"] = 2 ** 40
        self.catalog["items"][0]["reward"]["quantity"] = 2 ** 40
        self.save_catalog()
        self.assert_refused("OverflowException")

    def test_catalog_paramdef_and_active_location_set_are_bound(self):
        original = copy.deepcopy(self.plan)
        self.plan["catalog_sha256"] = "0" * 64
        self.assert_refused("catalog hash mismatch")
        self.plan = copy.deepcopy(original)
        self.plan["source_hashes"]["dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx"] = "0" * 64
        self.assert_refused("paramdef hash mismatch")
        self.plan = copy.deepcopy(original)
        self.plan["placements"][0]["location_key"] = "different"
        self.assert_refused("placement set differs from active catalog")
        self.plan = copy.deepcopy(original)
        self.catalog["entries"].append({"location_key": "dlc", "status": "placeable",
                                       "when": {"include_dlc": True}, "targets": []})
        self.save_catalog()
        self.plan["options"]["include_dlc"] = True
        self.assert_refused("placement set differs from active catalog")
