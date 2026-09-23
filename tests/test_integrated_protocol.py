"""Protocol envelope, capabilities and opaque-handle discipline."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bb_launcher.integrated.backend import Backend
from bb_launcher.integrated.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    check_request,
    error_response,
    ok_response,
    redact_for_log,
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def request(op: str, params: dict | None = None, seq: int = 0, op_id: str = "op-1") -> dict:
    return {"protocol": PROTOCOL_VERSION, "op": op, "id": op_id, "seq": seq,
            "params": params or {}}


class ProtocolEnvelopeTests(unittest.TestCase):
    def test_rejects_wrong_protocol_version(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            check_request({"protocol": "v0", "op": "capabilities", "id": "a", "seq": 0})
        self.assertEqual(caught.exception.code, "incompatible-protocol")

    def test_rejects_unknown_operation(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            check_request({"protocol": PROTOCOL_VERSION, "op": "run-anything",
                           "id": "a", "seq": 0})
        self.assertEqual(caught.exception.code, "unknown-operation")

    def test_rejects_unknown_error_code(self) -> None:
        with self.assertRaises(ValueError):
            ProtocolError("not-a-code", "x")

    def test_redacts_secrets_for_logs(self) -> None:
        redacted = redact_for_log({"password": "hunter2", "server": "example:1234",
                                   "nested": {"token": "abc"}})
        self.assertEqual(redacted["password"], "<redacted>")
        self.assertEqual(redacted["server"], "example:1234")
        self.assertEqual(redacted["nested"]["token"], "<redacted>")

    def test_ok_and_error_envelopes_carry_protocol_id_seq(self) -> None:
        ok = ok_response("op-9", 3, {"a": 1})
        self.assertTrue(ok["ok"])
        self.assertEqual((ok["protocol"], ok["id"], ok["seq"]), (PROTOCOL_VERSION, "op-9", 3))
        err = error_response("op-9", 3, ProtocolError("bad-request", "nope"))
        self.assertFalse(err["ok"])
        self.assertEqual(err["error"]["code"], "bad-request")


class CapabilitiesTests(unittest.TestCase):
    def test_capabilities_reports_compat_and_fork_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = Backend(Path(state))
            response = backend.handle(request("capabilities"))
            self.assertTrue(response["ok"], response)
            result = response["result"]
            self.assertEqual(result["protocol"], PROTOCOL_VERSION)
            self.assertIn("prepare_play", result["operations"])
            self.assertEqual(result["activation_route"], "copy")
            self.assertIn("fork", result)
            self.assertEqual(result["fork"]["upstream_baseline"],
                             "ca12c2fc38b8ba485e508bde815e8ea8cb49ac10")

    def test_stdout_stays_protocol_only_on_garbage(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = Backend(Path(state))
            response = backend.handle({"nope": True})
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "incompatible-protocol")
            # No receipt paths, no tracebacks in the envelope.
            self.assertNotIn("traceback", json.dumps(response).lower())


class OpaqueHandleTests(unittest.TestCase):
    def _backend(self, state: str) -> Backend:
        counter = {"n": 0}

        def prepare(params: dict, op_id: str) -> dict:
            counter["n"] += 1
            return {"receipt_id": digest("receipt-1"), "receipt_digest": digest("payload-1"),
                    "seed": "Evening hunt", "slot": "Alaric", "cache_key": digest("cache-1"),
                    "package_name": "Archipelago-Alaric-abc123", "server": "archipelago.gg:1"}

        return Backend(Path(state), prepare_fn=prepare)

    def test_prepare_mints_opaque_play_handle_and_hides_receipt_path(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = self._backend(state)
            first = backend.handle(request("prepare_play", {"game_root": state}, op_id="p1"))
            self.assertTrue(first["ok"], first)
            play_id = first["result"]["play_id"]
            self.assertTrue(play_id.startswith("play_"))
            blob = json.dumps(first["result"])
            self.assertNotIn("receipts", blob)
            self.assertNotIn(".json", blob)

    def test_prepare_is_idempotent_for_the_same_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = self._backend(state)
            first = backend.handle(request("prepare_play", {"game_root": state}, op_id="p1"))
            second = backend.handle(request("prepare_play", {"game_root": state}, op_id="p2"))
            self.assertTrue(second["ok"], second)
            self.assertEqual(first["result"]["play_id"], second["result"]["play_id"])
            self.assertTrue(second["result"]["reused"])

    def test_reused_receipt_with_different_seed_slot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            calls = {"n": 0}

            def prepare(params: dict, op_id: str) -> dict:
                calls["n"] += 1
                seed = "seed-B" if calls["n"] > 1 else "seed-A"
                return {"receipt_id": digest("same-receipt"),
                        "receipt_digest": digest("same-payload"), "seed": seed,
                        "slot": "Alaric", "cache_key": digest("cache-1"),
                        "package_name": "Archipelago-Alaric-abc123", "server": ""}

            backend = Backend(Path(state), prepare_fn=prepare)
            first = backend.handle(request("prepare_play", {"game_root": state}, op_id="p1"))
            self.assertTrue(first["ok"], first)
            second = backend.handle(request("prepare_play", {"game_root": state}, op_id="p2"))
            self.assertFalse(second["ok"])
            self.assertEqual(second["error"]["code"], "seed-identity-mismatch")

    def test_unknown_play_handle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = self._backend(state)
            response = backend.handle(
                request("verify_and_arm", {"play_id": "play_" + "0" * 32,
                                          "game_root": state}, op_id="v1"))
            self.assertFalse(response["ok"])
            # Unknown handle maps to bad-request, never a receipt path leak.
            self.assertNotIn("receipts", json.dumps(response))


if __name__ == "__main__":
    unittest.main()
