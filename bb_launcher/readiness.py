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
import time
from dataclasses import dataclass
from pathlib import Path

from .client_config import ClientRuntimePaths, session_paths
from .core import GameInstall, LauncherError, _load_owner


BRIDGE_STATE_NAME = "native-grant-state.txt"
CLIENT_HEALTH_FORMAT = "bb-client-health-v1"
CLIENT_HEALTH_STALE_SECONDS = 8.0


def grants_watchdog_warning(
    readiness: "LauncherReadiness", *, bridge_expected: bool
) -> str | None:
    """Verdict for the post-launch grant watchdog.

    Returns the warning to show when the launch pinned a CE bridge but the
    grant harness still has not reported, so the player finds out in minutes
    rather than after a session of undeliverable items. None when grants
    are armed (any bridge state at all means the harness reported) or when
    no bridge was expected.
    """
    if not bridge_expected or readiness.bridge is not None:
        return None
    return (
        "The Cheat Engine grant table has not reported since launch -- item "
        "grants are NOT armed and nothing you are owed can be delivered. "
        "Open Cheat Engine with the bundled grant table, accept its "
        "administrator and script prompts, and let it attach to shadPS4. "
        "The status panel shows 'Bridge: no state yet' until it reports."
    )


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
class ClientHealthStatus:
    process_alive: bool
    ap_connected: bool
    delivery_armed: bool
    detail: str
    age_seconds: float
    stale: bool

    @property
    def ready(self) -> bool:
        return not self.stale and self.process_alive and self.ap_connected and self.delivery_armed


@dataclass(frozen=True)
class LauncherReadiness:
    paths: ClientRuntimePaths
    overlay: OverlayStatus | None
    ledger: LedgerStatus | None
    bridge: BridgeStatus | None
    client_health: ClientHealthStatus | None
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


def _client_health_status(
    paths: ClientRuntimePaths, notes: list[str], *, now: float
) -> ClientHealthStatus | None:
    if not paths.client_health.is_file():
        return None
    try:
        value = json.loads(paths.client_health.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        notes.append(f"client health is unreadable: {exc}")
        return None
    if not isinstance(value, dict) or value.get("format") != CLIENT_HEALTH_FORMAT:
        notes.append(f"client health {paths.client_health} has an unsupported format")
        return None
    updated = value.get("updated_unix_ms")
    process_alive = value.get("process_alive")
    ap_connected = value.get("ap_connected")
    delivery_armed = value.get("delivery_armed")
    if (
        not isinstance(updated, (int, float))
        or isinstance(updated, bool)
        or not isinstance(process_alive, bool)
        or not isinstance(ap_connected, bool)
        or not isinstance(delivery_armed, bool)
    ):
        notes.append(f"client health {paths.client_health} is missing typed status fields")
        return None
    age = max(0.0, now - float(updated) / 1000.0)
    return ClientHealthStatus(
        process_alive=process_alive,
        ap_connected=ap_connected,
        delivery_armed=delivery_armed,
        detail=str(value.get("detail", "")),
        age_seconds=age,
        stale=age > CLIENT_HEALTH_STALE_SECONDS,
    )


def gather_readiness(
    install: GameInstall,
    state_root: Path | str,
    *,
    seed: str,
    slot: str,
    now: float | None = None,
) -> LauncherReadiness:
    """Snapshot everything the status panel shows, without writing anything."""

    paths = session_paths(state_root, seed=seed, slot=slot)
    notes: list[str] = []
    return LauncherReadiness(
        paths=paths,
        overlay=_overlay_status(install, notes),
        ledger=_ledger_status(paths, seed, slot, notes),
        bridge=_bridge_status(paths, notes),
        client_health=_client_health_status(paths, notes, now=time.time() if now is None else now),
        notes=tuple(notes),
    )


def format_client_health(readiness: LauncherReadiness) -> str:
    """One honest player-facing line for the live client contract."""
    health = readiness.client_health
    if health is None:
        return "Client: not running (no live status)"
    if health.stale:
        return f"Client: stopped or unresponsive (last update {health.age_seconds:.0f}s ago)"
    game = "running" if health.process_alive else "stopped"
    ap = "AP connected" if health.ap_connected else "AP disconnected"
    delivery = "delivery ready" if health.delivery_armed else "delivery not ready"
    return f"Client: {game} · {ap} · {delivery}"


def format_readiness(readiness: LauncherReadiness) -> str:
    """Render the snapshot as the panel's plain-text lines."""

    lines: list[str] = [format_client_health(readiness)]
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
