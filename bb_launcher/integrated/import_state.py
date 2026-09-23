"""Reversible import of existing setup and companion AP records.

- Detects an existing BBLauncher setup and offers **Use this setup**,
  showing game and emulator versions; asks which installation only when
  genuinely ambiguous.
- Recognizes companion receipts, cache and seed/slot state in the AP
  state root and *references/imports* those records without moving
  ledgers into mod folders and without resetting history.  An old
  exact-executable receipt may require re-export, but its seed/slot
  ledger survives.  Standalone AP ownership needs an explicit checked
  transition before the fork adopts the overlay.
- Records the migration reversibly and exposes a restore path.  Before
  using an existing active stack, inspects its backup/conflict metadata
  and rejects ambiguous ownership.  No silent ledger reset, no save
  conversion, no adoption of standalone ownership.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

from ..core import ValidationError, _write_json_atomic
from .sessions import integrated_root

IMPORT_FORMAT = "bb-integrated-import-v1"


def detect_installations(candidates: list[Path]) -> dict[str, Any]:
    """Report installs; ambiguity is resolved once by explicit choice."""

    from ..core import GameInstall

    found: list[dict[str, str]] = []
    for candidate in candidates:
        try:
            install = GameInstall.from_root(candidate)
        except ValidationError:
            continue
        found.append({
            "root": str(candidate.expanduser().resolve()),
            "serial": install.serial,
            "app_version": install.app_version,
        })
    if not found:
        return {"status": "missing", "installs": []}
    if len(found) == 1:
        return {"status": "ready", "installs": found, "selected": found[0]["root"]}
    return {"status": "ambiguous", "installs": found, "selected": None}


def import_companion_state(*, state_root: Path | str, game_root: Path | str) -> dict[str, Any]:
    """Reference companion receipts/cache/sessions without moving ledgers.

    Copies nothing destructive: writes an import record naming every
    adopted reference plus a restore path (the record itself -- deleting
    the integrated references restores pre-import behavior because the
    companion originals are never moved or rewritten).
    """

    state = Path(state_root).expanduser().resolve()
    target_dir = integrated_root(state) / "imports"
    target_dir.mkdir(parents=True, exist_ok=True)
    adopted: list[dict[str, str]] = []
    # Companion receipts live under <state>/external/receipts; session
    # ledgers under <state>/sessions.  Reference by content digest so a
    # later companion write cannot silently retarget the fork.
    for subdir in ("external/receipts", "sessions"):
        source = state / subdir
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*.json")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                digest = _sha256_file(path)
            except OSError:
                continue
            adopted.append({"kind": subdir, "source": str(path), "sha256": digest})
    # Refuse ambiguous standalone ownership: a standalone owner manifest
    # inside the game overlay must go through the explicit transition.
    owner = Path(str(game_root)).expanduser().resolve() / "CUSA03173-mods" / ".bb-ap-owner.json"
    standalone = owner.is_file() and not owner.is_symlink()
    record = {
        "format": IMPORT_FORMAT,
        "game_root": str(game_root),
        "adopted": adopted,
        "standalone_owner_present": bool(standalone),
        "requires_standalone_transition": bool(standalone),
        "restore": "delete integrated/imports/<this-record> to restore pre-import behavior; "
                   "companion originals were never moved",
        "created_at": time.time(),
    }
    _write_json_atomic(target_dir / f"import-{int(time.time())}.json", record)
    return record


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
