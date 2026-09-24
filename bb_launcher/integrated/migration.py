"""Checked transition from the companion AP overlay to Qt ModService.

The companion owns the entire game overlay, whereas ModService owns individual
files.  Move the verified companion tree out of shadPS4's search path before
ModService plans its new package.  Merged player files are copied back as a
plain overlay so ModService can retain or back them up in the usual way.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from .. import core
from .sessions import install_lock

MIGRATION_NAME = ".bb-ap-qt-migration.json"
MIGRATION_FORMAT = "bb-ap-qt-migration-v1"


def _journal_path(install: core.GameInstall) -> Path:
    return install.root / MIGRATION_NAME


def _read_journal(install: core.GameInstall) -> dict[str, Any] | None:
    path = _journal_path(install)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise core.RecoveryError(f"legacy migration record is not a regular file: {path}")
    record = core._read_json(path, "legacy migration record")
    if record.get("format") != MIGRATION_FORMAT or record.get("game_root") != str(install.root):
        raise core.RecoveryError(f"legacy migration record does not match selected game: {path}")
    core._require_sha256(str(record.get("cache_key", "")), "legacy migration cache_key")
    if record.get("phase") not in ("prepared", "disabled", "completed"):
        raise core.RecoveryError(f"invalid legacy migration phase in {path}")
    return record


def _disabled_path(install: core.GameInstall, record: dict[str, Any]) -> Path:
    name = record.get("disabled")
    if name is None:
        transaction = core._read_json(core._transaction_path(install), "activation transaction")
        if (transaction.get("format") != core.TRANSACTION_FORMAT
                or transaction.get("mode") != "deactivate"
                or transaction.get("cache_key") != record["cache_key"]):
            raise core.RecoveryError("legacy overlay deactivation transaction is missing or changed")
        name = transaction.get("disabled")
    if not isinstance(name, str) or not name.startswith(f".{core.MODS_DIR_NAME}.bb-ap-disabled-"):
        raise core.RecoveryError("legacy disabled overlay has an unexpected name")
    disabled = core._transaction_child(install, name, "disabled")
    if disabled is None:
        raise core.RecoveryError("legacy disabled overlay path is missing")
    return disabled


def _merged_files(owner: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in core._user_merge_records(owner)]


def _verify_plain_merge(root: Path, records: list[dict[str, Any]]) -> None:
    if not root.is_dir() or root.is_symlink():
        raise core.RecoveryError(f"plain overlay is not a regular directory: {root}")
    actual = core._tree_files(root)
    expected = {str(item["path"]).casefold(): item for item in records}
    found = {name.casefold(): path for name, path in actual.items()}
    if set(found) != set(expected) or len(found) != len(actual):
        raise core.RecoveryError("plain overlay changed during legacy migration; it was preserved")
    for key, item in expected.items():
        path = found[key]
        if path.stat().st_size != item["size"] or core.sha256_file(path) != item["sha256"]:
            raise core.RecoveryError(f"merged user file changed during legacy migration: {item['path']}")


def _copy_merged_files(install: core.GameInstall, disabled: Path,
                       records: list[dict[str, Any]]) -> None:
    if not records:
        return
    if install.mods.exists() or install.mods.is_symlink():
        raise core.ConflictError(f"a mods overlay appeared before legacy migration: {install.mods}")
    source_files = core._tree_files(disabled, ignore=(core.OWNER_NAME,), allow_file_links=True)
    source_by_key = {name.casefold(): path for name, path in source_files.items()}
    stage = Path(tempfile.mkdtemp(prefix=f".{core.MODS_DIR_NAME}.bb-ap-user-stage-",
                                  dir=install.root))
    try:
        for item in records:
            relative = core._safe_relative_path(str(item["path"]))
            source = source_by_key.get(relative.as_posix().casefold())
            if source is None:
                raise core.RecoveryError(f"merged user file disappeared: {relative}")
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        _verify_plain_merge(stage, records)
        core._load_owner(disabled)  # Source must still match its owner after copying.
        if install.mods.exists() or install.mods.is_symlink():
            raise core.ConflictError(f"a mods overlay appeared before legacy migration: {install.mods}")
        os.replace(stage, install.mods)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def migrate_legacy_overlay(
    game_root: Path | str,
    *,
    process_is_running: Callable[[], bool] | None = None,
    state_root: Path | str | None = None,
) -> dict[str, Any]:
    """Preserve an exact companion overlay before Qt plans a replacement.

    Call after Qt deactivates its own active package and restores its backup,
    and before ModService.PlanActivate.  This function never adopts an unknown
    or altered overlay.  It is resumable after companion deactivation or the
    player-file copy, and never removes the disabled original.
    """

    install = core.GameInstall.from_root(game_root)
    guard = (install_lock(state_root, install.root, owner="legacy-overlay-migration")
             if state_root is not None else nullcontext())
    with guard:
        return _migrate_locked(install, process_is_running)


def _migrate_locked(install: core.GameInstall,
                    process_is_running: Callable[[], bool] | None) -> dict[str, Any]:
    core._require_shad_stopped(process_is_running)
    record = _read_journal(install)
    if record is not None and record["phase"] == "completed":
        # A player can later use the companion again.  Its new owned overlay
        # needs another checked transition; the earlier disabled copy stays.
        if (install.mods / core.OWNER_NAME).is_file():
            record = None
        else:
            return {"status": "already_migrated", "disabled_overlay": str(_disabled_path(install, record)),
                    "merged_files": int(record["merged_files"])}
    if record is None:
        if not install.mods.exists() and not install.mods.is_symlink():
            return {"status": "no_legacy", "disabled_overlay": None, "merged_files": 0}
        if not (install.mods / core.OWNER_NAME).is_file():
            return {"status": "no_legacy", "disabled_overlay": None, "merged_files": 0}
        owner = core._load_owner(install.mods)
        record = {"format": MIGRATION_FORMAT, "game_root": str(install.root),
                  "cache_key": owner["cache_key"], "merged_files": len(_merged_files(owner)),
                  "phase": "prepared", "disabled": None}
        core._write_json_atomic(_journal_path(install), record)

    if record["phase"] == "prepared":
        if install.mods.exists():
            owner = core._load_owner(install.mods, expected_key=record["cache_key"])
            if len(_merged_files(owner)) != record["merged_files"]:
                raise core.RecoveryError("legacy merged-file count changed during migration")
            disabled = core.deactivate_overlay(install, process_is_running=process_is_running)
            if disabled is None:
                raise core.RecoveryError("legacy overlay disappeared during migration")
        else:
            core.recover_activation(install, process_is_running=process_is_running)
            disabled = _disabled_path(install, record)
        record["disabled"] = disabled.name
        record["phase"] = "disabled"
        core._write_json_atomic(_journal_path(install), record)

    disabled = _disabled_path(install, record)
    owner = core._load_owner(disabled, expected_key=record["cache_key"])
    merged = _merged_files(owner)
    if len(merged) != record["merged_files"]:
        raise core.RecoveryError("legacy merged-file count changed in disabled overlay")
    if install.mods.exists() or install.mods.is_symlink():
        _verify_plain_merge(install.mods, merged)
    else:
        _copy_merged_files(install, disabled, merged)
    record["phase"] = "completed"
    core._write_json_atomic(_journal_path(install), record)
    return {"status": "migrated", "disabled_overlay": str(disabled),
            "merged_files": len(merged)}
