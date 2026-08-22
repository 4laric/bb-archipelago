"""Read-only session readiness surface for the launcher UI (bb-archipelago#65).

Everything the player-facing status panel shows is derived here, from verified
on-disk state only: the active overlay's ownership manifest, the session's
client runtime config path, the client's durable ledger, and the CE bridge
state file. This module never writes anything and never raises for a missing
or malformed runtime artifact -- an absent overlay, a not-yet-created ledger,
or a bridge that has not reported yet are all normal states, and a corrupt one
is a visible note rather than a crash in a status display.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .client_config import ClientRuntimePaths, session_paths
from .core import GameInstall, LauncherError, _load_owner


BRIDGE_STATE_NAME = "native-grant-state.txt"


@dataclass(frozen=True)
class OverlayStatus:
    cache_key: str
    seed: str
    slot: str
    suppression_sha256: str
    enemizer_enabled: bool
    enemizer_files: int
    previous_cache_key: str | None


@dataclass(frozen=True)
class LedgerStatus:
    highest_processed_index: int | None
    acknowledged: int
    pending: bool
    save_watermark: int | None


@dataclass(frozen=True)
class BridgeStatus:
    status: str
    build: str | None
    protocol: str | None
    harness: str | None
    pid: int | None
    tag: str | None
    detail: str


@dataclass(frozen=True)
class LauncherReadiness:
    paths: ClientRuntimePaths
    overlay: OverlayStatus | None
    ledger: LedgerStatus | None
    bridge: BridgeStatus | None
    notes: tuple[str, ...]


def _overlay_status(install: GameInstall, notes: list[str]) -> OverlayStatus | None:
    if not install.mods.exists():
        return None
    try:
        owner = _load_owner(install.mods)
    except LauncherError as exc:
        notes.append(f"active overlay: {exc}")
        return None
    identity = owner.get("identity") if isinstance(owner.get("identity"), dict) else {}
    enemizer = owner.get("enemizer") if isinstance(owner.get("enemizer"), dict) else {}
    suppression = owner.get("suppression") if isinstance(owner.get("suppression"), dict) else {}
    return OverlayStatus(
        cache_key=str(owner["cache_key"]),
        seed=str(identity.get("seed", "?")),
        slot=str(identity.get("slot", "?")),
        suppression_sha256=str(suppression.get("sha256", "")),
        enemizer_enabled=bool(enemizer.get("enabled")),
        enemizer_files=int(enemizer.get("file_count", 0) or 0),
        previous_cache_key=(
            None if owner.get("previous_cache_key") is None else str(owner["previous_cache_key"])
        ),
    )


def _ledger_status(paths: ClientRuntimePaths, seed: str, slot: str, notes: list[str]) -> LedgerStatus | None:
    if not paths.ledger.is_file():
        return None
    try:
        value = json.loads(paths.ledger.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        notes.append(f"receive ledger is unreadable: {exc}")
        return None
    slots = value.get("slots") if isinstance(value, dict) else None
    if not isinstance(slots, dict):
        notes.append(f"receive ledger {paths.ledger} has no slots object")
        return None
    # The same key the native client uses for this AP seed/slot pair. A ledger
    # that exists but has no entry for this session is a fresh session, not a
    # zero-progress one.
    entry = slots.get(f"{seed}\x1f{slot}")
    if entry is None:
        return None
    if not isinstance(entry, dict):
        notes.append(f"receive ledger entry for {seed}/{slot} is not an object")
        return None
    acknowledged = entry.get("acknowledged")
    highest = entry.get("highest_processed_index")
    watermark = entry.get("save_watermark")
    return LedgerStatus(
        highest_processed_index=highest if isinstance(highest, int) else None,
        acknowledged=len(acknowledged) if isinstance(acknowledged, dict) else 0,
        pending=entry.get("pending") is not None,
        save_watermark=watermark if isinstance(watermark, int) else None,
    )


def _bridge_status(paths: ClientRuntimePaths, notes: list[str]) -> BridgeStatus | None:
    state_path = paths.bridge_root / BRIDGE_STATE_NAME
    if not state_path.is_file():
        return None
    try:
        text = state_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        notes.append(f"bridge state is unreadable: {exc}")
        return None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key] = value
    status = fields.get("status")
    if not status:
        notes.append(f"bridge state {state_path} has no status line")
        return None
    raw_pid = fields.get("pid", "")
    return BridgeStatus(
        status=status,
        build=fields.get("build") or None,
        protocol=fields.get("protocol") or None,
        harness=fields.get("harness") or None,
        pid=int(raw_pid) if raw_pid.isdigit() else None,
        tag=fields.get("tag") or None,
        detail=fields.get("detail", ""),
    )


def gather_readiness(
    install: GameInstall,
    state_root: Path | str,
    *,
    seed: str,
    slot: str,
) -> LauncherReadiness:
    """Snapshot everything the status panel shows, without writing anything."""

    paths = session_paths(state_root, seed=seed, slot=slot)
    notes: list[str] = []
    return LauncherReadiness(
        paths=paths,
        overlay=_overlay_status(install, notes),
        ledger=_ledger_status(paths, seed, slot, notes),
        bridge=_bridge_status(paths, notes),
        notes=tuple(notes),
    )


def format_readiness(readiness: LauncherReadiness) -> str:
    """Render the snapshot as the panel's plain-text lines."""

    lines: list[str] = []
    overlay = readiness.overlay
    if overlay is None:
        lines.append("Overlay: none active (vanilla search path)")
    else:
        enemizer = (
            f"enemizer on ({overlay.enemizer_files} maps)"
            if overlay.enemizer_enabled
            else "enemies unchanged"
        )
        lines.append(
            f"Overlay: {overlay.seed} / {overlay.slot} · cache {overlay.cache_key[:12]} · "
            f"suppression {overlay.suppression_sha256[:12]} · {enemizer}"
        )
    config_state = "written" if readiness.paths.config.is_file() else "written at launch"
    lines.append(f"Client config: {readiness.paths.config} ({config_state})")
    ledger = readiness.ledger
    if ledger is None:
        lines.append(f"Ledger: {readiness.paths.ledger} (no deliveries recorded yet)")
    else:
        cursor = (
            "none"
            if ledger.highest_processed_index is None
            else str(ledger.highest_processed_index)
        )
        watermark = (
            "attested mode"
            if ledger.save_watermark is None
            else f"save watermark {ledger.save_watermark}"
        )
        pending = ", one delivery in flight" if ledger.pending else ""
        lines.append(
            f"Ledger: {ledger.acknowledged} acknowledged, cursor {cursor}, {watermark}{pending}"
        )
    bridge = readiness.bridge
    if bridge is None:
        lines.append("Bridge: no state yet (the CE table reports here once attached)")
    else:
        harness = bridge.harness or "unknown harness"
        protocol = bridge.protocol or "unknown protocol"
        pid = "" if bridge.pid is None else f" · pid {bridge.pid}"
        detail = f" · {bridge.detail}" if bridge.detail else ""
        lines.append(f"Bridge: {bridge.status} · {harness} · {protocol}{pid}{detail}")
    lines.extend(f"Note: {note}" for note in readiness.notes)
    return "\n".join(lines)
