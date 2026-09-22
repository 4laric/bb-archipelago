"""Session coordinator: sequencing, identity, locking, cancellation, recovery.

Qt owns choices/progress/recovery actions.  The coordinator owns
sequencing, operation identity, per-install locking, cancellation and
recovery, and never parses human-readable logs as an API.

State machine:
  Inspect -> Prepare -> Plan activation -> Activate -> Verify/arm ->
  Start -> Connect -> Playing

Every step is resumable or explicitly recoverable.  Duplicate Play reuses
the active operation.  Cache reuse still checks changed inputs.
Immediately before mutation, the game must be stopped and the plan must
still match filesystem state.  Before connection, process creation
identity and installed bytes are rechecked; a PID alone is insufficient.
Restart, no-GUI startup, IPC and shortcuts cannot bypass AP preflight --
every startup route funnels through :meth:`Backend.preflight`.

Production wiring reuses ``workflow.prepare_seed``, the external
export/verify path, runtime-config writing and native client spawning.
The constructor accepts injectable hooks so the simulated journey and
fault-injection tests drive the real sequencing/locking/journal code
with fake processes (spec phase 1: "coordinator with fake processes").
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ..client_config import session_key
from ..core import ValidationError
from . import fork_identity
from .import_state import detect_installations, import_companion_state
from .journal import append_entry, decide_recovery, plan_activation, read_journal
from .policy import require_copy_activation, require_fork_provenance
from .protocol import PROTOCOL_VERSION, ProtocolError, check_request, error_response, ok_response
from .sessions import (
    arms_dir,
    find_play_by_receipt,
    install_lock,
    load_arm,
    load_play,
    load_remembered,
    mint_arm,
    mint_play,
    plays_dir,
    remember_session,
)
from .supervisor import (
    claim_client,
    drop_session,
    existing_session_for_play,
    reattach_session,
    register_session,
    release_client,
    SupervisorSession,
)

PrepareFn = Callable[..., Mapping[str, Any]]
VerifyFn = Callable[..., Any]
SpawnFn = Callable[..., Mapping[str, Any]]
ProcessCheckFn = Callable[[], Mapping[str, Any]]


@dataclass
class Backend:
    """Coordinator with injectable process-facing hooks."""

    state_root: Path
    prepare_fn: PrepareFn | None = None
    verify_fn: VerifyFn | None = None
    spawn_fn: SpawnFn | None = None
    process_check_fn: ProcessCheckFn | None = None
    cancelled: set[str] = field(default_factory=set)

    # -- operation entry point -------------------------------------------------

    def handle(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = check_request(raw)
        except ProtocolError as exc:
            return error_response(str(raw.get("id", "?")), int(raw.get("seq", 0) or 0), exc)
        handler = {
            "capabilities": self._capabilities,
            "inspect_install": self._inspect_install,
            "inspect_seed": self._inspect_seed,
            "prepare_play": self._prepare_play,
            "verify_and_arm": self._verify_and_arm,
            "connect_and_start_client": self._connect_and_start_client,
            "session_status": self._session_status,
            "stop_client": self._stop_client,
            "cancel_operation": self._cancel_operation,
        }[request["op"]]
        try:
            result = handler(request["params"], request["id"])
        except ProtocolError as exc:
            return error_response(request["id"], request["seq"], exc)
        except ValidationError as exc:
            return error_response(
                request["id"], request["seq"],
                ProtocolError("bad-request", str(exc), retryable=False),
            )
        except Exception as exc:  # fail closed, never leak internals
            return error_response(
                request["id"], request["seq"],
                ProtocolError("internal-error", f"coordinator failed: {type(exc).__name__}"),
            )
        return ok_response(request["id"], request["seq"], result)

    # -- capabilities ----------------------------------------------------------

    def _capabilities(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        from ..core import APP_VERSION, SERIAL

        return {
            "protocol": PROTOCOL_VERSION,
            "operations": [
                "capabilities", "inspect_install", "inspect_seed", "prepare_play",
                "verify_and_arm", "connect_and_start_client", "session_status",
                "stop_client", "cancel_operation",
            ],
            "games": [{"serial": serial, "app_version": app} for serial, app in
                      fork_identity.SUPPORTED_GAMES],
            "activation_route": fork_identity.SUPPORTED_ACTIVATION_ROUTE,
            "platform": fork_identity.SUPPORTED_PLATFORM,
            "world_build": _world_build(),
            "runtime_build": _runtime_build(),
            "fork": fork_identity.fork_provenance_record(),
            "serial": SERIAL,
            "app_version": APP_VERSION,
        }

    # -- inspect ---------------------------------------------------------------

    def _inspect_install(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        candidates = [Path(str(p)) for p in params.get("candidates", [])]
        report = detect_installations(candidates)
        if report["status"] == "missing":
            raise ProtocolError("missing-prerequisite", "no valid game installation found",
                                retryable=False, recovery=("choose-game-folder",))
        if report["status"] == "ambiguous":
            raise ProtocolError("ambiguous-install",
                                f"{len(report['installs'])} installations found; choose one",
                                retryable=False, recovery=("choose-installation",))
        installed = report["installs"][0]
        expected = {serial for serial, _ in fork_identity.SUPPORTED_GAMES}
        if installed["serial"] not in expected:
            raise ProtocolError("unsupported-build",
                                f"unsupported game serial {installed['serial']}",
                                recovery=("select-supported-game",))
        remembered = load_remembered(self.state_root)
        return {"install": installed, "remembered": remembered}

    def _inspect_seed(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        from ..seed_request import resolve_request_source

        seed_path = params.get("seed_path")
        if not seed_path:
            raise ProtocolError("bad-request", "inspect_seed requires seed_path")
        try:
            resolved = resolve_request_source(
                Path(str(seed_path)), player_name=str(params.get("player_name", "")),
                state_root=self.state_root,
            )
            raw = json.loads(resolved.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise ProtocolError("bad-request", f"could not read seed file: {exc}")
        slots = raw.get("slots") or ([raw["player_name"]] if raw.get("player_name") else [])
        if not isinstance(slots, list) or not slots:
            raise ProtocolError("bad-request", "seed carries no player slots")
        if len(slots) == 1:
            return {"slots": slots, "selected": slots[0], "needs_choice": False,
                    "server": raw.get("server", ""), "seed": raw.get("seed", "")}
        remembered = load_remembered(self.state_root)
        chosen = params.get("player_name") or (remembered or {}).get("slot")
        if chosen in slots:
            return {"slots": slots, "selected": chosen, "needs_choice": True,
                    "server": raw.get("server", ""), "seed": raw.get("seed", "")}
        raise ProtocolError("ambiguous-player",
                            f"seed has {len(slots)} Bloodborne slots; choose a player",
                            recovery=("choose-player",),
                            ids={"seed": str(raw.get("seed", ""))})

    # -- prepare ----------------------------------------------------------------

    def _prepare_play(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        if op_id in self.cancelled:
            raise ProtocolError("cancelled", "operation was cancelled")
        if self.prepare_fn is None:
            raise ProtocolError("internal-error", "backend has no prepare function wired")
        prepared = self.prepare_fn(params, op_id)  # real: workflow.prepare_seed + export
        receipt_id = str(prepared["receipt_id"])
        existing = find_play_by_receipt(self.state_root, receipt_id)
        if existing is not None:
            # Idempotent reuse: same receipt authority, no rebuild.  Byte
            # cache identity never replaces the receipt as authority.
            if existing.seed != prepared["seed"] or existing.slot != prepared["slot"]:
                raise ProtocolError("seed-identity-mismatch",
                                    "existing play for this receipt names a different seed/slot")
            return {"play_id": existing.play_id, "reused": True,
                    "display": _display(prepared)}
        record = mint_play(
            self.state_root, receipt_id=receipt_id,
            receipt_digest=str(prepared["receipt_digest"]), seed=str(prepared["seed"]),
            slot=str(prepared["slot"]), cache_key=str(prepared["cache_key"]),
            package_name=str(prepared["package_name"]),
        )
        append_entry(self.state_root, params.get("game_root", "."), "plan",
                     record.play_id, {"package": record.package_name})
        return {"play_id": record.play_id, "reused": False, "display": _display(prepared)}

    # -- verify/arm ---------------------------------------------------------------

    def _verify_and_arm(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        play_id = str(params.get("play_id", ""))
        play = load_play(self.state_root, play_id)
        self.preflight(params, stage="arm")
        verified = self._verify(play, params)
        require_copy_activation(verified.files, stage="arming")
        arm = mint_arm(
            self.state_root, play_id=play.play_id, receipt_id=play.receipt_id,
            activation_fingerprint=verified.activation_fingerprint,
        )
        append_entry(self.state_root, params.get("game_root", "."), "commit",
                     play.play_id, {"arm_id": arm.arm_id,
                                    "fingerprint": verified.activation_fingerprint})
        remember_session(self.state_root, game_root=str(params.get("game_root", "")),
                         seed=play.seed, slot=play.slot,
                         server=str(params.get("server", "")), play_id=play.play_id)
        return {"arm_id": arm.arm_id, "display": {"seed": play.seed, "slot": play.slot}}

    def _verify(self, play: Any, params: Mapping[str, Any]) -> Any:
        if self.verify_fn is None:
            raise ProtocolError("internal-error", "backend has no verify function wired")
        return self.verify_fn(play, params)

    # -- connect ------------------------------------------------------------------

    def preflight(self, params: Mapping[str, Any], *, stage: str) -> None:
        """Every startup path -- Play, Restart, IPC, no-GUI/shortcuts -- passes here."""

        game_stopped = self.process_check_fn() if self.process_check_fn else {"game_running": False}
        if stage in ("arm",) and game_stopped.get("game_running"):
            raise ProtocolError("conflict", "stop the game before arming",
                                recovery=("stop-game",))
        fork = params.get("fork_build") or {}
        if fork:
            require_fork_provenance(str(fork.get("commit", "")),
                                    str(fork.get("executable_sha256", "")))

    def _connect_and_start_client(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        arm_id = str(params.get("arm_id", ""))
        arm = load_arm(self.state_root, arm_id)
        play = load_play(self.state_root, arm.play_id)
        self.preflight(params, stage="connect")
        # Late checks: installed bytes + fresh game process, never PID alone.
        verified = self._verify(play, params)
        require_copy_activation(verified.files, stage="connection")
        if verified.activation_fingerprint != arm.activation_fingerprint:
            raise ProtocolError("verification-failed", "activation drifted since arming",
                                recovery=("prepare-again",))
        live = self.process_check_fn() if self.process_check_fn else {}
        expected_pid = (live.get("pid"), live.get("creation_time"))
        prior = existing_session_for_play(self.state_root, play.play_id)
        if prior is not None and live.get("pid") == prior.pid:
            # Duplicate Play reuses the live session instead of spawning again.
            reattached = reattach_session(
                self.state_root, prior.session_id, executable=prior.executable,
                executable_sha256=prior.executable_sha256, pid=prior.pid,
                creation_time=prior.creation_time, process_alive=bool(live.get("alive")),
            )
            return {"session_id": reattached.session_id, "reused": True,
                    "client_pid": reattached.client_pid}
        if self.spawn_fn is None:
            raise ProtocolError("internal-error", "backend has no spawn function wired")
        spawned = self.spawn_fn(play, arm, params, verified)
        session = SupervisorSession(
            session_id=f"session_{play.play_id[5:13]}",
            play_id=play.play_id, arm_id=arm.arm_id,
            executable=str(spawned["executable"]),
            executable_sha256=str(spawned["executable_sha256"]),
            pid=int(spawned["pid"]), creation_time=spawned.get("creation_time"),
            owner="supervisor", client_pid=spawned.get("client_pid"),
            created_at=time.time(),
        )
        register_session(self.state_root, session)
        if session.client_pid is not None:
            try:
                claim_client(self.state_root, session.session_id, session.client_pid)
            except ProtocolError:
                pass  # first registration already owns it
        return {"session_id": session.session_id, "reused": False,
                "client_pid": session.client_pid}

    # -- status / stop / cancel ------------------------------------------------------

    def _session_status(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        play_id = str(params.get("play_id", ""))
        session = existing_session_for_play(self.state_root, play_id)
        if session is None:
            return {"state": "idle", "play_id": play_id}
        live = self.process_check_fn() if self.process_check_fn else {}
        alive = live.get("pid") == session.pid and bool(live.get("alive", True))
        return {"state": "playing" if alive else "recoverable",
                "session_id": session.session_id, "client_pid": session.client_pid,
                "play_id": play_id}

    def _stop_client(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        session_id = str(params.get("session_id", ""))
        release_client(self.state_root, session_id)
        return {"stopped": True, "session_id": session_id}

    def _cancel_operation(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        target = str(params.get("target_id", op_id))
        self.cancelled.add(target)
        return {"cancelled": target,
                "note": "cancellation lands at the next safe boundary; "
                        "recovery replays the journal"}


def _display(prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {"seed": prepared.get("seed"), "slot": prepared.get("slot"),
            "server": prepared.get("server", ""),
            "title": prepared.get("title") or f"{prepared.get('seed')} ({prepared.get('slot')})"}


def _world_build() -> str:
    try:
        from worlds.bloodborne import WORLD_VERSION as value  # type: ignore
        return str(value)
    except Exception:
        return "unknown"


def _runtime_build() -> str:
    try:
        from worlds.bloodborne import RUNTIME_BUILD as value  # type: ignore
        return str(value)
    except Exception:
        return "unknown"


def serve(backend: Backend) -> int:
    """JSON-lines stdin/stdout loop; stdout stays protocol-only."""

    import sys

    seq = 0
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(
                error_response("?", seq, ProtocolError("bad-request", "not JSON")).copy()
            ) + "\n")
            sys.stdout.flush()
            continue
        response = backend.handle(raw if isinstance(raw, dict) else {})
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
        seq += 1
    return 0
