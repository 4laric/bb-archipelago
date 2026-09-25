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
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ..client_config import session_key
from ..core import ValidationError, ConflictError, RecoveryError
from ..external import ExternalPackageExists
from ..workflow import WorkflowError
from . import fork_identity
from .import_state import detect_installations, import_companion_state
from .journal import append_entry, decide_recovery, plan_activation, read_journal
from .policy import fork_build_warning
from .path_identity import same_path
from .protocol import PROTOCOL_VERSION, ProtocolError, check_request, error_response, ok_response
from .enemizer import enemizer_options_record, parse_enemizer_options
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
    update_play_launch_config,
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


def _build_diagnostic(message: str) -> str | None:
    """Keep a bounded validation reason, never a command, path or traceback."""
    for raw in reversed(message.splitlines()[1:]):
        line = raw.strip()
        if not line or re.search(r"(?i)traceback|^file\s+[\"']|^at\s+", line):
            continue
        if ("CalledProcessError:" in line or
                re.search(r"(?i)failed to execute script|returned non-zero exit status", line)):
            # Python and PyInstaller append wrapper failures after the native
            # validation line; their argv and stack are not the root cause.
            continue
        match = re.match(
            r"(?i)^(?:unhandled exception\.\s*)?"
            r"(?:[\w.]+(?:error|exception)|error|fatal|failed)\s*:\s*(.+)$",
            line,
        )
        if match is None:
            continue
        detail = match.group(1).strip()
        # Tool stdout is untrusted. A useful prefix is enough when the rest
        # contains a path, address or credential-bearing argument.
        unsafe = re.search(
            r"(?i)(?:[a-z]:[\\/]|(?<!\w)/\S+|(?:https?|ap)://|"
            r"\b(?:password|passwd|secret|token|authorization|api[_-]?key|bearer)\b\s*(?:[:=]|\s))",
            detail,
        )
        if unsafe is not None:
            detail = detail[:unsafe.start()].rstrip(" :;,.-")
        if (not detail or len(detail) > 200 or
                re.search(r"[\x00-\x1f\x7f]", detail)):
            continue
        return detail
    return None


def _workflow_error(exc: WorkflowError) -> ProtocolError:
    """Translate known safe build failures without returning arbitrary logs."""
    message = str(exc)
    exit_code = re.match(r"^build tool exited with code (-?\d+):", message)
    if exit_code is not None:
        detail = f"Build tool failed (exit code {exit_code.group(1)})."
        diagnostic = _build_diagnostic(message)
        detail += (f" {diagnostic}" if diagnostic else
                   " Check the original game files and packaged build tools, then retry.")
        return ProtocolError("verification-failed", detail)
    if message.startswith("could not start build tool "):
        return ProtocolError(
            "missing-prerequisite",
            "Could not start a required build tool. Check the launcher package and retry.",
        )
    if message.startswith("AP server/slot does not match the selected seed package"):
        return ProtocolError(
            "seed-identity-mismatch",
            "AP server/slot does not match the selected seed package. Select the matching "
            "seed and server, or use the explicit mismatch override.",
        )
    if message.startswith(("refusing to evict unexpected cache path:",
                           "refusing to clean unexpected build path:")):
        return ProtocolError(
            "conflict", "An unexpected build/cache folder blocks preparation. "
            "Choose a different cache location or remove the conflicting folder.",
        )
    return ProtocolError(
        "internal-error", "Preparation stopped before launch. Check the selected game "
        "installation and launcher package, then retry.",
    )


@dataclass
class Backend:
    """Coordinator with injectable process-facing hooks."""

    state_root: Path
    prepare_fn: PrepareFn | None = None
    verify_fn: VerifyFn | None = None
    spawn_fn: SpawnFn | None = None
    process_check_fn: ProcessCheckFn | None = None
    cancelled: set[str] = field(default_factory=set)
    # Server passwords live only for this backend process lifetime. They are
    # keyed by opaque play handle and never written into the play record.
    launch_secrets: dict[str, dict[str, str]] = field(default_factory=dict)
    client_processes: dict[str, Any] = field(default_factory=dict)

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
            "migrate_legacy_overlay": self._migrate_legacy_overlay,
            "prepare_standalone": self._prepare_standalone,
            "verify_standalone": self._verify_standalone,
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
        except WorkflowError as exc:
            return error_response(request["id"], request["seq"], _workflow_error(exc))
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
                "prepare_standalone", "verify_standalone", "migrate_legacy_overlay",
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
            "build_warning": fork_build_warning(
                str(params.get("fork_build", {}).get("commit", "")),
                str(params.get("fork_build", {}).get("executable_sha256", ""))),
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
        from ..seed_request import archive_slots, looks_like_archive, resolve_request_source

        seed_path = params.get("seed_path")
        if not seed_path:
            raise ProtocolError("bad-request", "inspect_seed requires seed_path")
        player_name = str(params.get("player_name", ""))
        resolved_player = player_name
        if looks_like_archive(Path(str(seed_path))):
            archive_entries = archive_slots(Path(str(seed_path)))
            archive_names = [name for _member, name in archive_entries]
            if not archive_entries:
                raise ProtocolError("bad-request", "seed zip carries no Bloodborne player slots")
            remembered = load_remembered(self.state_root)
            chosen = (player_name or (remembered or {}).get("slot")) if len(archive_entries) > 1 else archive_names[0]
            if len(archive_entries) > 1 and not chosen:
                return {"slots": archive_names, "selected": None, "needs_choice": True,
                        "server": "", "seed": ""}
            if chosen and chosen not in archive_names:
                return {"slots": archive_names, "selected": None, "needs_choice": True,
                        "server": "", "seed": ""}
            resolved_player = str(chosen or "")
        try:
            resolved = resolve_request_source(
                Path(str(seed_path)), player_name=resolved_player,
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
        return {"slots": slots, "selected": None, "needs_choice": True,
                "server": raw.get("server", ""), "seed": raw.get("seed", "")}

    # -- prepare ----------------------------------------------------------------

    def _prepare_standalone(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        from .standalone import prepare_standalone

        if op_id in self.cancelled:
            raise ProtocolError("cancelled", "operation was cancelled")
        return prepare_standalone(params, state_root=self.state_root)

    def _verify_standalone(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        from .standalone import verify_standalone

        return verify_standalone(params, state_root=self.state_root)

    def _migrate_legacy_overlay(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        from .migration import migrate_legacy_overlay

        game_root = params.get("game_root")
        if not isinstance(game_root, str) or not game_root.strip():
            raise ProtocolError("bad-request", "Choose a Bloodborne installation before launching.")
        if self.process_check_fn is None:
            raise ProtocolError("missing-prerequisite", "Cannot check whether the game is stopped. Restart the launcher.")
        if op_id in self.cancelled:
            raise ProtocolError("cancelled", "operation was cancelled")
        def game_running() -> bool:
            observed = self.process_check_fn()
            if observed.get("reason") == "process-query-refused":
                raise ProtocolError("missing-prerequisite", "Cannot check whether the game is stopped. Close the emulator and restart the launcher.")
            return observed.get("game_running") is not False

        try:
            return migrate_legacy_overlay(game_root, process_is_running=game_running,
                                          state_root=self.state_root)
        except (ConflictError, RecoveryError, ValidationError) as exc:
            raise ProtocolError("conflict", str(exc), retryable=True) from exc

    def _prepare_play(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        if op_id in self.cancelled:
            raise ProtocolError("cancelled", "operation was cancelled")
        if self.prepare_fn is None:
            raise ProtocolError("internal-error", "backend has no prepare function wired")
        reuse_existing = params.get("reuse_existing", False)
        if type(reuse_existing) is not bool:
            raise ProtocolError("bad-request", "reuse_existing must be a boolean")
        options = parse_enemizer_options(params)
        prepare_params = {
            **params,
            "state_root": str(self.state_root),
            "enemizer": enemizer_options_record(options),
            "reuse_existing": reuse_existing,
        }
        try:
            prepared = self.prepare_fn(prepare_params, op_id)  # workflow + inactive export
        except ExternalPackageExists as exc:
            raise ProtocolError(
                "package-exists", str(exc), retryable=options.enabled,
                recovery=("rerandomize-enemies",) if options.enabled else (),
                ids={"package_name": exc.path.name},
            ) from exc
        receipt_id = str(prepared["receipt_id"])
        existing = find_play_by_receipt(self.state_root, receipt_id)
        if existing is not None:
            # Idempotent reuse: same receipt authority, no rebuild.  Byte
            # cache identity never replaces the receipt as authority.
            if existing.seed != prepared["seed"] or existing.slot != prepared["slot"]:
                raise ProtocolError("seed-identity-mismatch",
                                    "existing play for this receipt names a different seed/slot")
            launch_config = {
                **dict(prepared.get("launch_config", {})),
                "enemizer": enemizer_options_record(options),
            }
            existing = update_play_launch_config(
                self.state_root, existing.play_id, launch_config)
            if params.get("password"):
                self.launch_secrets[existing.play_id] = {
                    "password": str(params["password"])}
            return {"play_id": existing.play_id, "package_name": existing.package_name,
                    "reused": True, "build_warning": prepared.get("build_warning"),
                    "enemizer": prepared.get("enemizer"),
                    "display": _display(prepared)}
        launch_config = {
            **dict(prepared.get("launch_config", {})),
            "enemizer": enemizer_options_record(options),
        }
        record = mint_play(
            self.state_root, receipt_id=receipt_id,
            receipt_digest=str(prepared["receipt_digest"]), seed=str(prepared["seed"]),
            slot=str(prepared["slot"]), cache_key=str(prepared["cache_key"]),
            package_name=str(prepared["package_name"]),
            launch_config=launch_config,
        )
        if params.get("password"):
            self.launch_secrets[record.play_id] = {"password": str(params["password"])}
        append_entry(self.state_root, params.get("game_root", "."), "plan",
                     record.play_id, {"package": record.package_name})
        return {"play_id": record.play_id, "package_name": record.package_name,
                "reused": False, "build_warning": prepared.get("build_warning"),
                "enemizer": prepared.get("enemizer"),
                "display": _display(prepared)}

    # -- verify/arm ---------------------------------------------------------------

    def _verify_and_arm(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        play_id = str(params.get("play_id", ""))
        play = load_play(self.state_root, play_id)
        launch_params = {**play.launch_config, **params}
        self.preflight(launch_params, stage="arm")
        verified = self._verify(play, launch_params)
        arm = mint_arm(
            self.state_root, play_id=play.play_id, receipt_id=play.receipt_id,
            activation_fingerprint=verified.activation_fingerprint,
        )
        append_entry(self.state_root, params.get("game_root", "."), "commit",
                     play.play_id, {"arm_id": arm.arm_id,
                                    "fingerprint": verified.activation_fingerprint})
        remember_session(self.state_root, game_root=str(launch_params.get("game_root", "")),
                         seed=play.seed, slot=play.slot,
                         server=str(launch_params.get("server", "")), play_id=play.play_id)
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

    def _check_claimed_process(self, claimed: Mapping[str, Any],
                                 live: Mapping[str, Any]) -> None:
        """Cross-check the fork-reported process identity against live state.

        A PID alone is never sufficient: the claimed executable path and
        hash must match the live process, and a claimed creation time must
        equal the live one, or the PID was reused by another process.
        """

        if not live.get("game_running"):
            raise ProtocolError("stale-session", "the game is no longer running",
                                retryable=False, recovery=("fresh-boot",))
        if live.get("ambiguous"):
            try:
                claimed_pid = int(claimed.get("pid", -1))
            except (TypeError, ValueError):
                claimed_pid = -1
            matching = [item for item in live.get("processes", [])
                        if isinstance(item, Mapping) and item.get("pid") == claimed_pid]
            if len(matching) != 1:
                raise ProtocolError("stale-session",
                                    "the claimed emulator process is not present",
                                    retryable=False, recovery=("fresh-boot",))
            live = {**live, **matching[0]}
        claimed_exe = str(claimed.get("executable", ""))
        live_exe = str(live.get("executable", ""))
        if claimed_exe and live_exe and not same_path(claimed_exe, live_exe):
            raise ProtocolError("stale-session", "game executable path changed",
                                retryable=False, recovery=("fresh-boot",))
        claimed_sha = str(claimed.get("executable_sha256", "")).lower()
        live_sha = str(live.get("executable_sha256", "")).lower()
        if claimed_sha and live_sha and claimed_sha != live_sha:
            raise ProtocolError("stale-session", "game executable hash changed",
                                retryable=False, recovery=("fresh-boot",))
        try:
            claimed_pid = int(claimed.get("pid", -1))
        except (TypeError, ValueError):
            claimed_pid = -1
        if claimed_pid >= 0 and live.get("pid") != claimed_pid:
            raise ProtocolError("stale-session",
                                "the game process is not the armed one (PID changed)",
                                retryable=False, recovery=("fresh-boot",))
        claimed_birth = claimed.get("creation_time")
        if (claimed_birth is not None and live.get("creation_time") is not None
                and str(claimed_birth) != str(live.get("creation_time"))):
            raise ProtocolError("stale-session", "PID was reused by another process",
                                retryable=False, recovery=("fresh-boot",))

    def _connect_and_start_client(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        arm_id = str(params.get("arm_id", ""))
        arm = load_arm(self.state_root, arm_id)
        play = load_play(self.state_root, arm.play_id)
        launch_params = {**play.launch_config, **params}
        launch_params.update(self.launch_secrets.get(play.play_id, {}))
        self.preflight(launch_params, stage="connect")
        # Late checks: installed bytes + fresh game process, never PID alone.
        verified = self._verify(play, launch_params)
        if verified.activation_fingerprint != arm.activation_fingerprint:
            raise ProtocolError("verification-failed", "activation drifted since arming",
                                recovery=("prepare-again",))
        live = self.process_check_fn() if self.process_check_fn else {}
        claimed = params.get("process") or {}
        if claimed:
            # The fork started the game through its emulator service after
            # arming and reports the actual process identity: cross-check
            # it against the live enumeration instead of trusting it.
            self._check_claimed_process(claimed, live)
            live = {**live, **{k: claimed[k] for k in
                               ("pid", "creation_time", "executable",
                                "executable_sha256") if k in claimed},
                     "alive": live.get("alive", True)}
        if live.get("game_running") and live.get("pid") is not None:
            launch_params["process_identity"] = {
                key: live[key] for key in ("pid", "creation_time", "executable",
                                           "executable_sha256") if key in live
            }
        prior = existing_session_for_play(self.state_root, play.play_id)
        if prior is not None and live.get("pid") == prior.pid:
            # Duplicate Play reuses the live session instead of spawning again.
            reattached = reattach_session(
                self.state_root, prior.session_id,
                executable=str(live.get("executable") or prior.executable),
                executable_sha256=str(live.get("executable_sha256") or prior.executable_sha256),
                pid=prior.pid,
                creation_time=live.get("creation_time", prior.creation_time),
                process_alive=bool(live.get("alive")),
            )
            return {"session_id": reattached.session_id, "reused": True,
                    "client_pid": reattached.client_pid}
        if self.spawn_fn is None:
            raise ProtocolError("internal-error", "backend has no spawn function wired")
        spawned = self.spawn_fn(play, arm, launch_params, verified)
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
        process_handle = spawned.get("_process")
        if process_handle is not None:
            self.client_processes[session.session_id] = process_handle
        if session.client_pid is not None:
            try:
                claim_client(self.state_root, session.session_id, session.client_pid)
            except ProtocolError:
                release_client(self.state_root, session.session_id)
                raise
        return {"session_id": session.session_id, "reused": False,
                "client_pid": session.client_pid}

    # -- status / stop / cancel ------------------------------------------------------

    def _session_status(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        play_id = str(params.get("play_id", ""))
        session = existing_session_for_play(self.state_root, play_id)
        if session is None:
            return {"state": "idle", "play_id": play_id}
        live = self.process_check_fn() if self.process_check_fn else {}
        if live.get("ambiguous"):
            matching = [item for item in live.get("processes", [])
                        if isinstance(item, Mapping) and item.get("pid") == session.pid]
            if len(matching) == 1:
                live = {**live, **matching[0]}
        same_process = live.get("pid") == session.pid
        if same_process and session.creation_time is not None and live.get("creation_time") is not None:
            same_process = str(session.creation_time) == str(live.get("creation_time"))
        if same_process and session.executable and live.get("executable"):
            same_process = same_path(session.executable, str(live["executable"]))
        if same_process and session.executable_sha256 and live.get("executable_sha256"):
            same_process = session.executable_sha256.lower() == str(
                live["executable_sha256"]).lower()
        alive = same_process and bool(live.get("alive", True))
        client = self.client_processes.get(session.session_id)
        client_running: bool | None = None
        if client is not None:
            poll = getattr(client, "poll", None)
            if callable(poll):
                client_running = poll() is None
        return {"state": "playing" if alive and client_running is True else "recoverable",
                "session_id": session.session_id, "client_pid": session.client_pid,
                "client_running": client_running, "play_id": play_id}

    def _stop_client(self, params: Mapping[str, Any], op_id: str) -> dict[str, Any]:
        session_id = str(params.get("session_id", ""))
        process = self.client_processes.get(session_id)
        if process is None:
            raise ProtocolError(
                "stale-session",
                "this backend does not own the client process; session ownership was preserved",
                retryable=False,
                recovery=("return-to-game",),
                ids={"session_id": session_id},
            )
        poll = getattr(process, "poll", None)
        if not callable(poll):
            raise ProtocolError("stale-session", "owned client handle cannot verify process state",
                                retryable=False, recovery=("return-to-game",),
                                ids={"session_id": session_id})
        if poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except Exception:
                process.kill()
                process.wait(timeout=5)
        if poll() is None:
            raise ProtocolError("stale-session", "owned client is still running after stop",
                                retryable=True, recovery=("return-to-game",),
                                ids={"session_id": session_id})
        self.client_processes.pop(session_id, None)
        release_client(self.state_root, session_id)
        return {"stopped": True, "session_id": session_id,
                "detail": "owned client stopped or already exited"}

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
