from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json

from bb_launcher.core import GameInstall, ValidationError
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


def _request_payload(fmt: str) -> dict:
    return {
        "format": fmt,
        "player": 1,
        "player_name": "Tester",
        "runtime_build": "bb-0.1.0-r5",
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
        self.assertEqual(legacy, current)

    def test_unknown_format_is_refused_naming_both_accepted_formats(self):
        with self.assertRaises(ValidationError) as raised:
            self._identity_for(_request_payload("bb-enemizer-request-v0"))
        message = str(raised.exception)
        self.assertIn(REQUEST_FORMAT, message)
        self.assertIn(LEGACY_REQUEST_FORMAT, message)


if __name__ == "__main__":
    unittest.main()
