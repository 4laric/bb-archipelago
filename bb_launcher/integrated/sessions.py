"""Opaque play/arm handles, remembered sessions and per-install locking.

- Qt passes opaque ``play_<hex>`` / ``arm_<hex>`` handles; receipt paths
  never cross the protocol.  Play-ID-to-receipt mappings persist
  atomically under ``<state>/integrated/plays/`` -- outside mod trees.
- Idempotent package reuse: identical byte caches may belong to different
  seed/slot identities, so the *receipt* (seed/slot authority) is the
  session authority, never the package bytes or filename.  Ledgers stay
  keyed by seed+slot via :func:`session_key`, independently of cache
  identity.  Play ids resolve by validated receipt identity, never by
  package name/path alone.
- ``remembered.json`` keeps the last game/seed/player/server choice so the
  next visit is Play-only.  A server edit never silently changes
  seed/player: the stored server is namespaced by the seed/slot it was
  used with.
- Per-install locking serialises the fork UI, backend and mod service.
  Locks are advisory file locks (exclusive-create) because the original
  BBLauncher does not know them; fingerprints are still rechecked late
  at every mutation boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from ..client_config import session_key
from ..core import ValidationError, _require_sha256, _write_json_atomic
from .path_identity import canonical_path

INTEGRATED_DIR_NAME = "integrated"
PLAY_HANDLE_PREFIX = "play_"
ARM_HANDLE_PREFIX = "arm_"


def integrated_root(state_root: Path | str) -> Path:
    return Path(state_root).expanduser().resolve() / INTEGRATED_DIR_NAME


def plays_dir(state_root: Path | str) -> Path:
    return integrated_root(state_root) / "plays"


def arms_dir(state_root: Path | str) -> Path:
    return integrated_root(state_root) / "arms"


def remembered_path(state_root: Path | str) -> Path:
    return integrated_root(state_root) / "remembered.json"


def _mint(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(16)}"


def install_hash(game_root: Path | str) -> str:
    resolved = canonical_path(str(Path(game_root).expanduser().resolve()))
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PlayRecord:
    play_id: str
    receipt_id: str
    receipt_digest: str
    seed: str
    slot: str
    cache_key: str
    ledger_key: str
    package_name: str
    launch_config: Mapping[str, Any]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "bb-integrated-play-v1",
            "play_id": self.play_id,
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
            "seed": self.seed,
            "slot": self.slot,
            "cache_key": self.cache_key,
            "ledger_key": self.ledger_key,
            "package_name": self.package_name,
            "launch_config": dict(self.launch_config),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ArmRecord:
    arm_id: str
    play_id: str
    receipt_id: str
    activation_fingerprint: str
    process_expected: Mapping[str, Any]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "bb-integrated-arm-v1",
            "arm_id": self.arm_id,
            "play_id": self.play_id,
            "receipt_id": self.receipt_id,
            "activation_fingerprint": self.activation_fingerprint,
            "process_expected": dict(self.process_expected),
            "created_at": self.created_at,
        }


def _read_record(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} is not a JSON object: {path}")
    return value


def mint_play(state_root: Path | str, *, receipt_id: str, receipt_digest: str,
              seed: str, slot: str, cache_key: str, package_name: str,
              launch_config: Mapping[str, Any] | None = None) -> PlayRecord:
    if not seed.strip() or not slot.strip():
        raise ValidationError("play record requires a non-empty seed and slot")
    _require_sha256(cache_key.lower(), "play cache_key")
    record = PlayRecord(
        play_id=_mint(PLAY_HANDLE_PREFIX),
        receipt_id=_require_sha256(receipt_id.lower(), "play receipt_id"),
        receipt_digest=_require_sha256(receipt_digest.lower(), "play receipt_digest"),
        seed=seed,
        slot=slot,
        cache_key=cache_key.lower(),
        ledger_key=session_key(seed, slot),
        package_name=package_name,
        launch_config=dict(launch_config or {}),
        created_at=time.time(),
    )
    directory = plays_dir(state_root)
    directory.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(directory / f"{record.play_id}.json", record.as_dict())
    return record


def load_play(state_root: Path | str, play_id: str) -> PlayRecord:
    if not play_id.startswith(PLAY_HANDLE_PREFIX) or len(play_id) != len(PLAY_HANDLE_PREFIX) + 32:
        raise ValidationError(f"unknown play handle: {play_id}")
    path = plays_dir(state_root) / f"{play_id}.json"
    if not path.is_file() or path.is_symlink():
        raise ValidationError(f"unknown play handle: {play_id}")
    raw = _read_record(path, "play record")
    try:
        return PlayRecord(
            play_id=raw["play_id"], receipt_id=raw["receipt_id"],
            receipt_digest=raw["receipt_digest"], seed=raw["seed"], slot=raw["slot"],
            cache_key=raw["cache_key"], ledger_key=raw["ledger_key"],
            package_name=raw["package_name"],
            launch_config=(raw.get("launch_config")
                           if isinstance(raw.get("launch_config", {}), dict) else {}),
            created_at=float(raw["created_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"play record is malformed: {path}") from exc


def update_play_launch_config(state_root: Path | str, play_id: str,
                              launch_config: Mapping[str, Any]) -> PlayRecord:
    """Refresh machine-specific launch settings for an existing receipt handle."""

    record = load_play(state_root, play_id)
    updated = PlayRecord(
        play_id=record.play_id, receipt_id=record.receipt_id,
        receipt_digest=record.receipt_digest, seed=record.seed, slot=record.slot,
        cache_key=record.cache_key, ledger_key=record.ledger_key,
        package_name=record.package_name, launch_config=dict(launch_config),
        created_at=record.created_at,
    )
    _write_json_atomic(plays_dir(state_root) / f"{play_id}.json", updated.as_dict())
    return updated


def find_play_by_receipt(state_root: Path | str, receipt_id: str) -> PlayRecord | None:
    """Idempotent reuse: an existing play for this receipt avoids a rebuild."""

    directory = plays_dir(state_root)
    if not directory.is_dir():
        return None
    wanted = receipt_id.lower()
    for path in sorted(directory.glob(f"{PLAY_HANDLE_PREFIX}*.json")):
        try:
            raw = _read_record(path, "play record")
        except ValidationError:
            continue
        if str(raw.get("receipt_id", "")).lower() == wanted:
            try:
                return load_play(state_root, str(raw.get("play_id", "")))
            except ValidationError:
                continue
    return None


def mint_arm(state_root: Path | str, *, play_id: str, receipt_id: str,
             activation_fingerprint: str,
             process_expected: Mapping[str, Any] | None = None) -> ArmRecord:
    record = ArmRecord(
        arm_id=_mint(ARM_HANDLE_PREFIX),
        play_id=play_id,
        receipt_id=_require_sha256(receipt_id.lower(), "arm receipt_id"),
        activation_fingerprint=activation_fingerprint,
        process_expected=dict(process_expected or {}),
        created_at=time.time(),
    )
    directory = arms_dir(state_root)
    directory.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(directory / f"{record.arm_id}.json", record.as_dict())
    return record


def load_arm(state_root: Path | str, arm_id: str) -> ArmRecord:
    if not arm_id.startswith(ARM_HANDLE_PREFIX) or len(arm_id) != len(ARM_HANDLE_PREFIX) + 32:
        raise ValidationError(f"unknown arm handle: {arm_id}")
    path = arms_dir(state_root) / f"{arm_id}.json"
    if not path.is_file() or path.is_symlink():
        raise ValidationError(f"unknown arm handle: {arm_id}")
    raw = _read_record(path, "arm record")
    try:
        return ArmRecord(
            arm_id=raw["arm_id"], play_id=raw["play_id"], receipt_id=raw["receipt_id"],
            activation_fingerprint=raw["activation_fingerprint"],
            process_expected=raw.get("process_expected", {}),
            created_at=float(raw["created_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"arm record is malformed: {path}") from exc


def remember_session(state_root: Path | str, *, game_root: str, seed: str,
                     slot: str, server: str, play_id: str) -> dict[str, Any]:
    """Remember the last successful choice; server edits stay namespaced."""

    if not seed.strip() or not slot.strip():
        raise ValidationError("remembered session requires a non-empty seed and slot")
    path = remembered_path(state_root)
    previous: dict[str, Any] = {}
    if path.is_file() and not path.is_symlink():
        previous = _read_record(path, "remembered session")
        if not isinstance(previous, dict):
            previous = {}
    value = {
        "format": "bb-integrated-remembered-v1",
        "game_root": game_root,
        "seed": seed,
        "slot": slot,
        # The server is stored alongside the seed/slot it was validated
        # with, so editing it later cannot silently re-target a session.
        "server": server,
        "server_for_seed": seed,
        "server_for_slot": slot,
        "play_id": play_id,
        "previous": previous.get("seed"),
    }
    _write_json_atomic(path, value)
    return value


def load_remembered(state_root: Path | str) -> dict[str, Any] | None:
    path = remembered_path(state_root)
    if not path.is_file() or path.is_symlink():
        return None
    raw = _read_record(path, "remembered session")
    if raw.get("format") != "bb-integrated-remembered-v1":
        raise ValidationError("unsupported remembered session format")
    return raw


class InstallLockError(ValidationError):
    pass


@contextmanager
def install_lock(state_root: Path | str, game_root: Path | str,
                 *, owner: str, timeout_s: float = 30.0) -> Iterator[Path]:
    """Advisory per-install exclusive lock shared by UI, backend and service.

    Implemented with exclusive file creation so it works without POSIX
    locking primitives.  The original BBLauncher does not know this lock,
    so callers must still recheck fingerprints late at mutation boundaries.
    """

    directory = integrated_root(state_root) / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"install-{install_hash(game_root)}.lock"
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise InstallLockError(
                    f"installation is locked by another operation: {game_root}"
                )
            time.sleep(0.05)
            continue
        break
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"owner": owner, "created_at": time.time()}, stream)
        yield path
    finally:
        try:
            path.unlink()
        except OSError:
            pass
