"""The binder-in-CI pin check (tools/check_suppression_plan_pin.py).

Motivating case (#138): the plan pin the world stamps into every seed was
asserted, never reproduced -- a plan/pin mismatch shipped a seed no binder
could satisfy, and CI stayed green. The checker must red on exactly that
mismatch, and must fail closed on every degenerate input rather than pass.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.check_suppression_plan_pin import (
    BUNDLE_PATH,
    EXPECTED_OUTPUT_SHA256,
    EXPECTED_SOURCE_SHA256,
    MANIFEST_FORMAT,
    main,
    read_bundle_source_sha,
    read_pin,
)

REPO = Path(__file__).resolve().parent.parent
WORLD_SOURCE = REPO / "worlds" / "bloodborne" / "__init__.py"


def write_manifest(directory: Path, **overrides) -> Path:
    manifest = {
        "format": MANIFEST_FORMAT,
        "plan_sha256": read_pin(WORLD_SOURCE),
        "source_gameparam_sha256": EXPECTED_SOURCE_SHA256,
        "output_gameparam_sha256": EXPECTED_OUTPUT_SHA256,
    }
    manifest.update(overrides)
    path = directory / "build-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


class PlanPinCheck(unittest.TestCase):
    def check(self, manifest: Path) -> int:
        # The committed bundle is the default and carries the pinned source.
        return main(["--manifest", str(manifest)])

    def test_matching_pin_passes(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(self.check(write_manifest(Path(tmp))), 0)

    def test_mismatched_pin_reds(self):
        # The motivating case: a built plan the world's pin disagrees with.
        with TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp), plan_sha256="f" * 64)
            self.assertEqual(self.check(manifest), 1)

    def test_missing_manifest_fails_closed(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "build-manifest.json"
            with self.assertRaises(SystemExit) as caught:
                self.check(missing)
            self.assertIn("fails closed", str(caught.exception))

    def test_wrong_format_fails_closed(self):
        with TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp), format="bb-something-else-v9")
            with self.assertRaises(SystemExit):
                self.check(manifest)

    def test_absent_plan_sha_fails_closed(self):
        # A manifest without the field is not a manifest that matches.
        with TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp))
            data = json.loads(manifest.read_text(encoding="utf-8"))
            del data["plan_sha256"]
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.check(manifest)

    def test_pin_is_read_from_the_world_source(self):
        # The checker reads the shipped constant, not a copy: the value it
        # compares against is the one the world stamps into slot data.
        pin = read_pin(WORLD_SOURCE)
        self.assertRegex(pin, r"^[0-9a-f]{64}$")
        self.assertIn(f'SUPPRESSION_PLAN_SHA256 = "{pin}"',
                      WORLD_SOURCE.read_text(encoding="utf-8"))


class LineagePins(unittest.TestCase):
    def test_the_committed_bundle_carries_the_installed_patch_layer(self):
        # The #200 regression itself: the bundle's gameparam IS the pin.
        self.assertEqual(read_bundle_source_sha(BUNDLE_PATH), EXPECTED_SOURCE_SHA256)

    def test_a_binder_from_foreign_source_bytes_reds(self):
        with TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp), source_gameparam_sha256="a" * 64)
            self.assertEqual(main(["--manifest", str(manifest)]), 1)

    def test_a_binder_whose_output_drifts_from_the_validated_one_reds(self):
        with TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp), output_gameparam_sha256="b" * 64)
            self.assertEqual(main(["--manifest", str(manifest)]), 1)

    def test_a_missing_bundle_fails_closed(self):
        with TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp))
            with self.assertRaises(SystemExit) as caught:
                main(["--manifest", str(manifest), "--bundle", str(Path(tmp) / "absent.db")])
            self.assertIn("refusing to pass", str(caught.exception))

    def test_the_fully_pinned_manifest_passes(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(main(["--manifest", str(write_manifest(Path(tmp)))]), 0)


if __name__ == "__main__":
    unittest.main()
