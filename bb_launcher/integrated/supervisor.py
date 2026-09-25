"""Session supervisor: the persistent owner of game + client processes.

The GUI-owned command backend (a QProcess the window manages) and the
independently launched persistent session supervisor have distinct
lifetimes.  The backend launches the supervisor independently before
client startup; destroying the GUI's QProcess must not destroy that
supervisor.

- Closing the window during play defaults to tray minimization; **Quit
  launcher and keep playing** detaches the verified game and supervisor.
  The supervisor retains client ownership and ends its client when that
  game exits.  GUI failure must not kill Bloodborne or erase delivery
  state.
- Reopening discovers and verifies the session before offering Return to
  game.  Reattachment validates executable, process creation identity and
  session -- never PID alone.  Stale PID files are not proof; a
  supervisor crash requires fresh process/activation checks on recovery.
- All startup paths, including Restart, IPC and no-GUI/shortcuts, go
  through AP preflight.  Repeated Play never spawns a duplicate client:
  the supervisor record owns one client per session.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..core import ValidationError, _require_sha256, _write_json_atomic
from .path_identity import same_path
from .protocol import ProtocolError
from .sessions import integrated_root

SUPERVISOR_FORMAT = "bb-integrated-supervisor-v1"


@dataclass(frozen=True)
class SupervisorSession:
    session_id: str
    play_id: str
    arm_id: str
    executable: str
    executable_sha256: str
    pid: int
    creation_time: int | None
    owner: str  # "supervisor" -- GUI QProcess records never own the client
    client_pid: int | None
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": SUPERVISOR_FORMAT,
            "session_id": self.session_id,
            "play_id": self.play_id,
            "arm_id": self.arm_id,
            "executable": self.executable,
            "executable_sha256": self.executable_sha256,
            "pid": self.pid,
            "creation_time": self.creation_time,
            "owner": self.owner,
            "client_pid": self.client_pid,
            "created_at": self.created_at,
        }


def supervisor_path(state_root: Path | str) -> Path:
    return integrated_root(state_root) / "supervisor.json"


def _load_all(state_root: Path | str) -> dict[str, Any]:
    path = supervisor_path(state_root)
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read supervisor record {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError(f"supervisor record is not an object: {path}")
    return raw


def register_session(state_root: Path | str, session: SupervisorSession) -> None:
    if session.owner != "supervisor":
        raise ValidationError("only the persistent supervisor may own a game session")
    records = _load_all(state_root)
    records[session.session_id] = session.as_dict()
    _write_json_atomic(supervisor_path(state_root), records)


def existing_session_for_play(state_root: Path | str, play_id: str) -> SupervisorSession | None:
    for raw in _load_all(state_root).values():
        if isinstance(raw, dict) and raw.get("play_id") == play_id:
            try:
                return SupervisorSession(
                    session_id=raw["session_id"], play_id=raw["play_id"],
                    arm_id=raw["arm_id"], executable=raw["executable"],
                    executable_sha256=raw["executable_sha256"], pid=int(raw["pid"]),
                    creation_time=raw.get("creation_time"), owner=raw["owner"],
                    client_pid=raw.get("client_pid"),
                    created_at=float(raw.get("created_at", 0)),
                )
            except (KeyError, TypeError, ValueError):
                continue
    return None


def reattach_session(
    state_root: Path | str,
    session_id: str,
    *,
    executable: str,
    executable_sha256: str,
    pid: int,
    creation_time: int | str | None,
    process_alive: bool,
) -> SupervisorSession:
    """Reopen/reattach: validate executable, creation identity and session.

    PID alone is never sufficient: a reused PID with a different creation
    time, a different executable path/hash, or a dead process fails closed
    and requires fresh process/activation checks.
    """

    records = _load_all(state_root)
    raw = records.get(session_id)
    if not isinstance(raw, dict):
        raise ProtocolError("stale-session", f"no supervisor session: {session_id}",
                            retryable=False, recovery=("fresh-boot",))
    if not same_path(str(raw.get("executable", "")), executable):
        raise ProtocolError("stale-session", "supervisor executable path changed",
                            retryable=False, recovery=("fresh-boot",))
    if str(raw.get("executable_sha256", "")).lower() != executable_sha256.lower():
        raise ProtocolError("stale-session", "supervisor executable hash changed",
                            retryable=False, recovery=("fresh-boot",))
    if int(raw.get("pid", -1)) != pid or not process_alive:
        raise ProtocolError("stale-session", "supervised process is gone",
                            retryable=False, recovery=("fresh-boot",))
    if (raw.get("creation_time") is not None
            and str(creation_time) != str(raw["creation_time"])):
        raise ProtocolError("stale-session", "PID was reused by another process",
                            retryable=False, recovery=("fresh-boot",))
    return SupervisorSession(
        session_id=raw["session_id"], play_id=raw["play_id"], arm_id=raw["arm_id"],
        executable=raw["executable"], executable_sha256=raw["executable_sha256"],
        pid=pid, creation_time=raw.get("creation_time"), owner=raw["owner"],
        client_pid=raw.get("client_pid"), created_at=float(raw.get("created_at", 0)),
    )


def claim_client(state_root: Path | str, session_id: str, client_pid: int) -> None:
    """Repeated Play must not spawn duplicate clients: one owner per session."""

    records = _load_all(state_root)
    raw = records.get(session_id)
    if not isinstance(raw, dict):
        raise ProtocolError("stale-session", f"no supervisor session: {session_id}")
    if raw.get("client_pid") not in (None, client_pid):
        raise ProtocolError(
            "duplicate-client",
            f"session {session_id} already owns client pid {raw['client_pid']}",
            retryable=False,
            recovery=("return-to-game",),
            ids={"session_id": session_id},
        )
    raw["client_pid"] = client_pid
    _write_json_atomic(supervisor_path(state_root), records)


def release_client(state_root: Path | str, session_id: str) -> None:
    """Stop only this session's owned client; never an unrelated process."""

    records = _load_all(state_root)
    raw = records.get(session_id)
    if not isinstance(raw, dict):
        return
    raw["client_pid"] = None
    _write_json_atomic(supervisor_path(state_root), records)


def drop_session(state_root: Path | str, session_id: str) -> None:
    records = _load_all(state_root)
    records.pop(session_id, None)
    _write_json_atomic(supervisor_path(state_root), records)
