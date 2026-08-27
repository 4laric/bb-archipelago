from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json

from bb_launcher.core import (
    SUPPRESSION_CHECK_PLAN,
    SUPPRESSION_CHECK_SOURCE,
    SUPPRESSION_OVERRIDE_KNOB,
    GameInstall,
    ValidationError,
)
from bb_launcher.workflow import (
    LEGACY_REQUEST_FORMAT,
    REQUEST_FORMAT,
    _request_identity,
    _validate_suppression,
)

from test_launcher_doctor import PLAN_HASH, DoctorFixture


class LauncherWorkflowTests(unittest.TestCase):
    def test_source_hash_mismatch_names_the_installed_path(self):
        # bb-archipelago#104: the opaque "does not match the installed game"
        # cost a full build cycle; the error must name the file it hashed.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DoctorFixture(Path(tmp))
            fixture.gameparam.write_bytes(b"modified after the binder was built")
            install = GameInstall.from_root(fixture.root / "game")
            with self.assertRaises(ValidationError) as raised:
                _validate_suppression(
                    install, fixture.binder, fixture.manifest_path, PLAN_HASH
                )
            message = str(raised.exception)
            self.assertIn(str(fixture.gameparam), message)
            self.assertIn("build.ps1 -Package -GameRoot", message)


class SuppressionMismatchOverrideTests(unittest.TestCase):
    """bb-archipelago#183: the operator escape hatch over binder hash skew.

    The default half of each pair is the control: without the knob the refusal
    must be exactly the one this code has always raised.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = DoctorFixture(Path(self.temporary.name))
        self.install = GameInstall.from_root(self.fixture.root / "game")

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self, plan_hash: str = PLAN_HASH, **kwargs):
        lines: list[str] = []
        result = _validate_suppression(
            self.install,
            self.fixture.binder,
            self.fixture.manifest_path,
            plan_hash,
            progress=lines.append,
            **kwargs,
        )
        return result, lines

    def skew_the_plan(self) -> str:
        wrong = "b" * 64
        self.assertNotEqual(wrong, PLAN_HASH)
        return wrong

    def test_plan_hash_skew_still_refuses_without_the_knob(self):
        with self.assertRaises(ValidationError) as raised:
            self.validate(self.skew_the_plan())
        self.assertEqual(
            "suppression build plan hash does not match the AP seed",
            str(raised.exception),
        )

    def test_plan_hash_skew_passes_under_the_knob_with_one_loud_line(self):
        result, lines = self.validate(self.skew_the_plan(), allow_mismatch=True)
        self.assertEqual((SUPPRESSION_CHECK_PLAN,), result.bypassed)
        self.assertEqual(1, len(lines))
        self.assertIn(SUPPRESSION_OVERRIDE_KNOB, lines[0])
        self.assertIn(SUPPRESSION_CHECK_PLAN, lines[0])
        self.assertIn("BYPASSED", lines[0])
        # expected-vs-found, both named, both truncated the same way
        self.assertIn(f"expected {'b' * 12}...", lines[0])
        self.assertIn(f"found {PLAN_HASH[:12]}...", lines[0])
        self.assertEqual(lines[0], lines[0].encode("ascii").decode("ascii"))

    def test_source_hash_skew_still_refuses_without_the_knob(self):
        self.fixture.gameparam.write_bytes(b"an install one re-copy behind")
        with self.assertRaises(ValidationError) as raised:
            self.validate()
        self.assertIn("does not match the installed game", str(raised.exception))

    def test_source_hash_skew_passes_under_the_knob_naming_the_installed_file(self):
        self.fixture.gameparam.write_bytes(b"an install one re-copy behind")
        result, lines = self.validate(allow_mismatch=True)
        self.assertEqual((SUPPRESSION_CHECK_SOURCE,), result.bypassed)
        self.assertEqual(1, len(lines))
        self.assertIn(SUPPRESSION_CHECK_SOURCE, lines[0])
        self.assertIn(str(self.fixture.gameparam), lines[0])

    def test_both_skews_at_once_emit_one_line_each(self):
        self.fixture.gameparam.write_bytes(b"an install one re-copy behind")
        result, lines = self.validate(self.skew_the_plan(), allow_mismatch=True)
        self.assertEqual(
            (SUPPRESSION_CHECK_PLAN, SUPPRESSION_CHECK_SOURCE), result.bypassed
        )
        self.assertEqual(2, len(lines))
        self.assertIn(SUPPRESSION_CHECK_PLAN, lines[0])
        self.assertIn(SUPPRESSION_CHECK_SOURCE, lines[1])

    def test_a_matching_chain_under_the_knob_adds_no_noise(self):
        result, lines = self.validate(allow_mismatch=True)
        self.assertEqual(
            {"bypassed": (), "lines": [], "plan": PLAN_HASH},
            {
                "bypassed": result.bypassed,
                "lines": lines,
                "plan": result.manifest["plan_sha256"],
            },
        )

    def test_the_knob_never_covers_a_corrupt_binder(self):
        # Skew is bypassable; a binder that disagrees with its own manifest is
        # corruption, and the override must not touch it.
        self.fixture.binder.write_bytes(b"not what the manifest describes")
        with self.assertRaises(ValidationError) as raised:
            self.validate(allow_mismatch=True)
        self.assertEqual(
            "suppression binder hash does not match its build manifest",
            str(raised.exception),
        )


def _request_payload(fmt: str) -> dict:
    return {
        "format": fmt,
        "player": 1,
        "player_name": "Tester",
        "runtime_build": "bb-0.1.0-r7",
        "world_version": "0.1.0",
        "enemizer_seed": "AP_1:1",
        "suppression": {"plan_sha256": "0" * 64},
    }


class RequestIdentityFormatTests(unittest.TestCase):
    """bb-archipelago#149: the request file is the seed's identity document.

    It is emitted for every slot regardless of the enemizer option, under the
    seed-request format name; seeds generated before the rename still carry
    the enemizer-request name and must keep working.
    """

    def _identity_for(self, payload: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return _request_identity(path)

    def test_seed_request_format_is_accepted(self):
        identity = self._identity_for(_request_payload(REQUEST_FORMAT))
        self.assertEqual(identity["slot"], "Tester")
        self.assertEqual(identity["enemizer_seed"], "AP_1:1")
        self.assertEqual(identity["suppression_plan_sha256"], "0" * 64)

    def test_legacy_enemizer_request_format_is_accepted(self):
        legacy = self._identity_for(_request_payload(LEGACY_REQUEST_FORMAT))
        current = self._identity_for(_request_payload(REQUEST_FORMAT))
        legacy["request"].pop("format"); current["request"].pop("format")
        # Both were written to their own tmpdir, so the resolved source
        # differs by construction; the identity either side of it must not.
        for identity in (legacy, current):
            identity.pop("source"); identity.pop("path")
        self.assertEqual(legacy, current)

    def test_unknown_format_is_refused_naming_both_accepted_formats(self):
        with self.assertRaises(ValidationError) as raised:
            self._identity_for(_request_payload("bb-enemizer-request-v0"))
        message = str(raised.exception)
        self.assertIn(REQUEST_FORMAT, message)
        self.assertIn(LEGACY_REQUEST_FORMAT, message)


if __name__ == "__main__":
    unittest.main()
