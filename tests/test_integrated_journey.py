"""Simulated end-to-end Qt/backend journey (no game, fake processes).

Drives the real coordinator sequencing -- prepare, arm, connect, status,
reconnect, stop -- the way the fork's Qt AP page will: choose seed, Play,
with preparation, activation, verification, startup and client connection
behind one action.  Receipt paths never appear in any response.  A second
Play reuses the live session instead of spawning a duplicate client.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from bb_launcher.integrated.backend import Backend
from bb_launcher.integrated.protocol import PROTOCOL_VERSION


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class FakeVerifiedFile:
    path: str
    installation: str = "copy"


@dataclass
class FakeVerified:
    files: tuple
    activation_fingerprint: str
    installed_gameparam: str = "C:\\fake\\gameparam.parambnd.dcx"


def request(op: str, params: dict | None = None, seq: int = 0, op_id: str = "op-1") -> dict:
    return {"protocol": PROTOCOL_VERSION, "op": op, "id": op_id, "seq": seq,
            "params": params or {}}


def journey_backend(state: str, *, route: str = "copy",
                    game_running_at_arm: bool = False) -> Backend:
    def prepare(params: dict, op_id: str) -> dict:
        return {"receipt_id": digest("receipt-journey"),
                "receipt_digest": digest("payload-journey"),
                "seed": "Evening hunt", "slot": "Alaric",
                "cache_key": digest("cache-journey"),
                "package_name": "Archipelago-Alaric-journey",
                "server": "archipelago.gg:12345", "title": "Evening hunt"}

    def verify(play: object, params: dict) -> FakeVerified:
        return FakeVerified(
            files=(FakeVerifiedFile("dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx",
                                    route),),
            activation_fingerprint=digest("fingerprint-journey"),
        )

    spawned = {"count": 0}

    def spawn(play: object, arm: object, params: dict, verified: object) -> dict:
        spawned["count"] += 1
        return {"executable": "C:\\games\\shadPS4.exe",
                "executable_sha256": digest("shad-exe"), "pid": 4242,
                "creation_time": 987654, "client_pid": 4243}

    def processes() -> dict:
        return {"game_running": game_running_at_arm, "pid": 4242,
                "creation_time": 987654, "alive": True}

    backend = Backend(Path(state), prepare_fn=prepare, verify_fn=verify,
                      spawn_fn=spawn, process_check_fn=processes)
    backend.spawned = spawned  # type: ignore[attr-defined]
    return backend


class SimulatedJourneyTests(unittest.TestCase):
    def test_choose_seed_then_play(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state)
            play = backend.handle(request("prepare_play", {"game_root": state}, op_id="p1"))
            self.assertTrue(play["ok"], play)
            play_id = play["result"]["play_id"]

            arm = backend.handle(request(
                "verify_and_arm",
                {"play_id": play_id, "game_root": state,
                 "mods_root": state, "server": "archipelago.gg:12345"}, op_id="a1"))
            self.assertTrue(arm["ok"], arm)
            arm_id = arm["result"]["arm_id"]
            self.assertTrue(arm_id.startswith("arm_"))

            connect = backend.handle(request(
                "connect_and_start_client",
                {"arm_id": arm_id, "game_root": state, "mods_root": state,
                 "process_plan": "plan"}, op_id="c1"))
            self.assertTrue(connect["ok"], connect)
            self.assertFalse(connect["result"]["reused"])

            status = backend.handle(request("session_status", {"play_id": play_id}))
            self.assertTrue(status["ok"], status)
            self.assertEqual(status["result"]["state"], "recoverable")
            self.assertIsNone(status["result"]["client_running"])

            # No receipt paths or handles leak into the wrong layer: arm
            # responses carry only the opaque arm handle.
            self.assertNotIn("receipts", json.dumps(arm["result"]))
            self.assertNotIn("receipts", json.dumps(connect["result"]))

    def test_repeated_play_reuses_the_live_session(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state)
            play_id = backend.handle(
                request("prepare_play", {"game_root": state}, op_id="p1"))["result"]["play_id"]
            arm_id = backend.handle(request(
                "verify_and_arm",
                {"play_id": play_id, "game_root": state, "mods_root": state},
                op_id="a1"))["result"]["arm_id"]
            params = {"arm_id": arm_id, "game_root": state, "mods_root": state,
                      "process_plan": "plan"}
            first = backend.handle(request("connect_and_start_client", params, op_id="c1"))
            second = backend.handle(request("connect_and_start_client", params, op_id="c2"))
            self.assertTrue(second["ok"], second)
            self.assertTrue(second["result"]["reused"])
            self.assertEqual(first["result"]["session_id"], second["result"]["session_id"])
            self.assertEqual(backend.spawned["count"], 1)  # type: ignore[attr-defined]

    def test_symlink_activation_is_refused_before_connection(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state, route="symlink")
            play_id = backend.handle(
                request("prepare_play", {"game_root": state}, op_id="p1"))["result"]["play_id"]
            arm = backend.handle(request(
                "verify_and_arm",
                {"play_id": play_id, "game_root": state, "mods_root": state}, op_id="a1"))
            self.assertFalse(arm["ok"])
            self.assertEqual(arm["error"]["code"], "activation-route-refused")

    def test_arming_while_the_game_runs_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state, game_running_at_arm=True)
            play_id = backend.handle(
                request("prepare_play", {"game_root": state}, op_id="p1"))["result"]["play_id"]
            arm = backend.handle(request(
                "verify_and_arm",
                {"play_id": play_id, "game_root": state, "mods_root": state}, op_id="a1"))
            self.assertFalse(arm["ok"])
            self.assertEqual(arm["error"]["code"], "conflict")

    def test_activation_drift_between_arm_and_connect_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state)
            play_id = backend.handle(
                request("prepare_play", {"game_root": state}, op_id="p1"))["result"]["play_id"]
            arm_id = backend.handle(request(
                "verify_and_arm",
                {"play_id": play_id, "game_root": state, "mods_root": state},
                op_id="a1"))["result"]["arm_id"]

            original = backend.verify_fn

            def drifted(play: object, params: dict) -> FakeVerified:
                return FakeVerified(
                    files=(FakeVerifiedFile("dvdroot_ps4/x"),),
                    activation_fingerprint=digest("drifted"),
                )

            backend.verify_fn = drifted  # type: ignore[method-assign]
            connect = backend.handle(request(
                "connect_and_start_client",
                {"arm_id": arm_id, "game_root": state, "mods_root": state,
                 "process_plan": "plan"}, op_id="c1"))
            self.assertFalse(connect["ok"])
            self.assertEqual(connect["error"]["code"], "verification-failed")
            backend.verify_fn = original  # type: ignore[method-assign]

    def test_stop_client_releases_only_the_owned_client(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            self.addCleanup(lambda: child.kill() if child.poll() is None else None)
            backend.spawn_fn = lambda play, arm, params, verified: {
                "executable": "C:\\games\\shadPS4.exe",
                "executable_sha256": digest("shad-exe"), "pid": 4242,
                "creation_time": 987654, "client_pid": child.pid, "_process": child,
            }
            play_id = backend.handle(
                request("prepare_play", {"game_root": state}, op_id="p1"))["result"]["play_id"]
            arm_id = backend.handle(request(
                "verify_and_arm",
                {"play_id": play_id, "game_root": state, "mods_root": state},
                op_id="a1"))["result"]["arm_id"]
            session_id = backend.handle(request(
                "connect_and_start_client",
                {"arm_id": arm_id, "game_root": state, "mods_root": state,
                 "process_plan": "plan"}, op_id="c1"))["result"]["session_id"]
            stopped = backend.handle(request("stop_client", {"session_id": session_id}))
            self.assertTrue(stopped["ok"], stopped)
            self.assertTrue(stopped["result"]["stopped"])
            self.assertIsNotNone(child.poll())

    def test_stop_refuses_to_clear_session_when_backend_lost_process_handle(self) -> None:
        from bb_launcher.integrated.supervisor import existing_session_for_play

        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            self.addCleanup(lambda: child.kill() if child.poll() is None else None)
            backend.spawn_fn = lambda play, arm, params, verified: {
                "executable": "C:\\games\\shadPS4.exe",
                "executable_sha256": digest("shad-exe"), "pid": 4242,
                "creation_time": 987654, "client_pid": child.pid, "_process": child,
            }
            play_id = backend.handle(request("prepare_play", {"game_root": state}))[
                "result"]["play_id"]
            arm_id = backend.handle(request("verify_and_arm", {
                "play_id": play_id, "game_root": state, "mods_root": state,
            })) ["result"]["arm_id"]
            session_id = backend.handle(request("connect_and_start_client", {
                "arm_id": arm_id, "game_root": state, "mods_root": state,
            })) ["result"]["session_id"]
            backend.client_processes.pop(session_id)

            stopped = backend.handle(request("stop_client", {"session_id": session_id}))
            self.assertFalse(stopped["ok"])
            self.assertEqual(stopped["error"]["code"], "stale-session")
            session = existing_session_for_play(state, play_id)
            self.assertIsNotNone(session)
            self.assertEqual(session.client_pid, child.pid)
            self.assertIsNone(child.poll())

    def test_cancel_lands_at_a_safe_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = journey_backend(state)
            cancelled = backend.handle(request("cancel_operation", {"target_id": "p9"}))
            self.assertTrue(cancelled["ok"], cancelled)
            play = backend.handle(request("prepare_play", {"game_root": state}, op_id="p9"))
            self.assertFalse(play["ok"])
            self.assertEqual(play["error"]["code"], "cancelled")


def claimed_backend(state: str, live: dict) -> Backend:
    backend = journey_backend(state)
    backend.process_check_fn = lambda: dict(live)  # type: ignore[method-assign]
    return backend


def armed_stopped(backend: Backend, state: str) -> str:
    """Arm while the game is stopped, as the real flow requires."""

    backend.process_check_fn = lambda: {"game_running": False}  # type: ignore[method-assign]
    play_id = backend.handle(
        request("prepare_play", {"game_root": state}, op_id="p1"))["result"]["play_id"]
    return backend.handle(request(
        "verify_and_arm",
        {"play_id": play_id, "game_root": state, "mods_root": state},
        op_id="a1"))["result"]["arm_id"]


class ClaimedProcessTests(unittest.TestCase):
    live = {"game_running": True, "pid": 4242, "creation_time": 987654,
            "executable": "C:\\games\\shadPS4.exe",
            "executable_sha256": digest("shad-exe"), "alive": True}

    def connect(self, backend: Backend, state: str, arm_id: str,
                process: dict | None, live: dict | None = None) -> dict:
        backend.process_check_fn = (  # type: ignore[method-assign]
            lambda: dict(self.live if live is None else live))
        params = {"arm_id": arm_id, "game_root": state, "mods_root": state,
                  "process_plan": "plan"}
        if process is not None:
            params["process"] = process
        return backend.handle(request("connect_and_start_client", params, op_id="c1"))

    def test_matching_claimed_identity_connects(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = claimed_backend(state, self.live)
            arm_id = armed_stopped(backend, state)
            response = self.connect(backend, state, arm_id, {
                "executable": "C:\\games\\shadPS4.exe",
                "executable_sha256": digest("shad-exe"),
                "pid": 4242, "creation_time": 987654})
            self.assertTrue(response["ok"], response)

    def test_reused_pid_with_new_birth_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = claimed_backend(state, self.live)
            arm_id = armed_stopped(backend, state)
            response = self.connect(backend, state, arm_id, {
                "executable": "C:\\games\\shadPS4.exe", "pid": 4242,
                "creation_time": 111111})
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "stale-session")

    def test_swapped_executable_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = claimed_backend(state, self.live)
            arm_id = armed_stopped(backend, state)
            response = self.connect(backend, state, arm_id, {
                "executable": "C:\\evil\\shadPS4.exe", "pid": 4242})
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "stale-session")

    def test_dead_game_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = claimed_backend(state, {**self.live, "game_running": False})
            arm_id = armed_stopped(backend, state)
            response = self.connect(backend, state, arm_id, {"pid": 4242},
                                    {**self.live, "game_running": False})
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "stale-session")


if __name__ == "__main__":
    unittest.main()

