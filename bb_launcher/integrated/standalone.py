"""Standalone randomization for the fork's inactive BBLauncher mod library.

The existing builder owns planning and native writes.  The existing exporter
owns package shape and receipts.  This boundary only resolves installed
inputs, selects bundled writers, and insists on a verified inactive export.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
import json
from pathlib import Path
from typing import Any, Mapping

from ..core import GameInstall, ValidationError, _write_json_atomic, sha256_file
from ..resources import application_root
from .protocol import ProtocolError


def _required_path(params: Mapping[str, Any], name: str) -> Path:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("bad-request", f"standalone {name} is required")
    # Preserve the supplied final component so receipt validation can reject
    # symlinks and junctions instead of silently following them.
    return Path(value).expanduser().absolute()


def _choices(params: Mapping[str, Any]) -> tuple[str, bool, bool, bool]:
    seed = params.get("seed")
    if not isinstance(seed, str) or not seed.strip():
        raise ProtocolError("bad-request", "standalone seed must be non-empty text")
    for name in ("include_dlc", "randomize_enemies", "expanded_coverage"):
        if name in params and not isinstance(params[name], bool):
            raise ProtocolError("bad-request", f"standalone {name} must be a boolean")
    # Keep standalone choices separate from AP-only boss settings.
    unsupported = sorted(set(params) - {
        "seed", "include_dlc", "randomize_enemies", "expanded_coverage",
        "game_root", "mods_root",
        "state_root",
    })
    if unsupported:
        raise ProtocolError("bad-request", "unsupported standalone option(s): "
                            + ", ".join(unsupported))
    enemies = params.get("randomize_enemies", False)
    expanded = params.get("expanded_coverage", False)
    if expanded and not enemies:
        raise ProtocolError("bad-request", "expanded coverage requires enemy randomization")
    return seed, params.get("include_dlc", False), enemies, expanded


def _source_directory(install: GameInstall, relative: str, destination: Path,
                      suffixes: tuple[str, ...]) -> Path:
    """Stage the patch-over-base file set consumed by the standalone builder."""
    selected: dict[str, Path] = {}
    for _layer, root in install.content_backends():
        source = root / relative
        if not source.is_dir() or source.is_symlink():
            continue
        for path in source.iterdir():
            if not path.is_file() or path.is_symlink():
                continue
            if path.name.lower().endswith(suffixes):
                selected.setdefault(path.name.casefold(), path)
    if not selected:
        raise ValidationError(f"game source has no {relative} files")
    destination.mkdir(parents=True)
    for path in selected.values():
        shutil.copyfile(path, destination / path.name)
    return destination


def _result(receipt: Mapping[str, Any], package: Path, receipt_path: Path) -> dict[str, Any]:
    return {
        "package_name": receipt["package_name"],
        "package_path": str(package),
        "receipt_path": str(receipt_path),
        "receipt_id": receipt["receipt_id"],
        "seed": receipt["seed"],
        "options": receipt["options"],
        "display_name": receipt["display_name"],
    }


def _prepared_path(state_root: Path, receipt_id: str) -> Path:
    if len(receipt_id) != 64 or any(char not in "0123456789abcdef" for char in receipt_id):
        raise ProtocolError("verification-failed", "standalone receipt ID is invalid")
    return state_root / "standalone" / "prepared" / f"{receipt_id}.json"


def _record_prepared(state_root: Path, receipt: Mapping[str, Any], package: Path,
                     receipt_path: Path, overlay_path: Path, selected_game_root: Path,
                     install_root: Path, mods_root: Path) -> None:
    _write_json_atomic(_prepared_path(state_root, str(receipt["receipt_id"])), {
        "format": "bb-integrated-standalone-prepared-v1",
        "receipt_id": receipt["receipt_id"],
        "package_name": receipt["package_name"],
        "package_path": str(package),
        "receipt_path": str(receipt_path),
        "overlay_path": str(overlay_path),
        "game_root": str(selected_game_root),
        "install_root": str(install_root),
        "mods_root": str(mods_root),
        "seed": receipt["seed"],
        "options": receipt["options"],
    })


def prepare_standalone(params: Mapping[str, Any], *, state_root: Path) -> dict[str, Any]:
    """Build and export a receipt-backed mod without activating or launching."""
    from tools.bb_standalone import StandaloneOptions
    from tools.bb_standalone.schema import GAMEPARAM_PATH, PARAMDEF_PATH
    from tools.build_standalone_randomizer import BuildConfig, EnemyOptions, build
    from tools.export_standalone_mod import (
        export_directory, package_name, validate_overlay, verify_export,
    )

    seed, include_dlc, randomize_enemies, expanded_coverage = _choices(params)
    game_root = _required_path(params, "game_root")
    mods_root = _required_path(params, "mods_root")
    if mods_root.name.casefold() != "mods" or not mods_root.is_dir() or mods_root.is_symlink():
        raise ProtocolError("bad-request", "standalone mods_root must be the inactive Mods directory")
    state = state_root.expanduser().resolve()
    if "state_root" in params and _required_path(params, "state_root").resolve() != state:
        raise ProtocolError("bad-request", "standalone state_root differs from backend state")
    try:
        install = GameInstall.from_root(game_root)
        gameparam = install.resolve_file(GAMEPARAM_PATH, include_mods=False)[1]
        paramdef = install.resolve_file(PARAMDEF_PATH, include_mods=False)[1]
        wakeup_event = (install.resolve_file(
            "dvdroot_ps4/event/m24_01_00_00.emevd.dcx", include_mods=False)[1]
            if expanded_coverage else None)
        tools = application_root() / "tools"
        item_writer = tools / "BBSuppressionWriter.exe"
        enemy_writer = tools / "BBEnemizerWriter.exe" if randomize_enemies else None
        for path in (item_writer, enemy_writer):
            if path is not None and (not path.is_file() or path.is_symlink()):
                raise ValidationError(f"bundled standalone writer is missing: {path}")
        base = state / "standalone"
        overlays = base / "overlays"
        receipts = base / "receipts"
        for directory in (overlays, receipts):
            directory.mkdir(parents=True, exist_ok=True)
        output = overlays / f"overlay-{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory(prefix="inputs-", dir=base) as temporary:
            input_root = Path(temporary)
            maps = scripts = None
            if randomize_enemies:
                maps = _source_directory(install, "dvdroot_ps4/map/MapStudio",
                                         input_root / "maps", (".msb", ".msb.dcx"))
                scripts = _source_directory(install, "dvdroot_ps4/script",
                                            input_root / "scripts", (".luabnd", ".luabnd.dcx"))
            build(BuildConfig(
                seed=seed, gameparam=gameparam, paramdef=paramdef,
                item_writer=item_writer, output=output,
                item_options=StandaloneOptions(include_dlc=include_dlc),
                enemy_options=EnemyOptions(
                    enabled=randomize_enemies, expanded_coverage=expanded_coverage),
                maps=maps, scripts=scripts, enemy_writer=enemy_writer,
                wakeup_event=wakeup_event,
            ))
        overlay = validate_overlay(output)
        if (overlay.identity["seed"] != seed
                or overlay.identity["options"]["items"].get("include_dlc") != include_dlc
                or overlay.identity["options"]["enemies"].get("enabled") != randomize_enemies
                or (randomize_enemies and overlay.identity["options"]["enemies"].get(
                    "allow_tier_mixing") is not True)
                or overlay.identity["options"]["enemies"].get(
                    "expanded_coverage", False) != expanded_coverage):
            raise ValueError("standalone build identity differs from requested seed or options")
        name = package_name(overlay)
        existing_package = mods_root / name
        existing_receipt = receipts / f"{name}.export-receipt.json"
        if existing_package.exists() or existing_receipt.exists():
            # Deterministic seed/options/input identity can be reused only if
            # both the old export and freshly built provenance still agree.
            verified = verify_export(existing_package, existing_receipt,
                                     overlay_root=output)
            previous = _prepared_path(state, str(verified["receipt_id"]))
            old_overlay = None
            if previous.is_file():
                try:
                    old_overlay = Path(json.loads(previous.read_text(encoding="utf-8"))["overlay_path"])
                    verify_export(existing_package, existing_receipt, overlay_root=old_overlay)
                except (OSError, ValueError, KeyError):
                    old_overlay = None
            if old_overlay is not None:
                shutil.rmtree(output)
            _record_prepared(state, verified, existing_package, existing_receipt,
                             old_overlay or output, game_root, install.root, mods_root)
            return _result(verified, existing_package, existing_receipt)
        exported = export_directory(output, mods_root=mods_root, receipt_root=receipts)
        verified = verify_export(exported.package_path, exported.receipt_path,
                                 overlay_root=output)
        _record_prepared(state, verified, exported.package_path, exported.receipt_path,
                         output, game_root, install.root, mods_root)
        return _result(verified, exported.package_path, exported.receipt_path)
    except (OSError, ValueError, ValidationError) as error:
        raise ProtocolError("verification-failed", str(error)) from error


def verify_standalone(params: Mapping[str, Any], *, state_root: Path) -> dict[str, Any]:
    """Rehash the exact inactive package immediately before Qt activation."""
    from tools.export_standalone_mod import validate_overlay, verify_export

    package = _required_path(params, "package_path")
    receipt_path = _required_path(params, "receipt_path")
    receipt_id = params.get("receipt_id")
    if not isinstance(receipt_id, str):
        raise ProtocolError("bad-request", "standalone receipt_id is required")
    record_path = _prepared_path(state_root.expanduser().resolve(), receipt_id)
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProtocolError("verification-failed", "standalone prepared record is missing") from error
    if not isinstance(record, dict) or record.get("format") != "bb-integrated-standalone-prepared-v1":
        raise ProtocolError("verification-failed", "standalone prepared record is invalid")
    required = ("package_name", "seed", "game_root", "mods_root",
                "include_dlc", "randomize_enemies", "expanded_coverage")
    if any(name not in params for name in required):
        raise ProtocolError("bad-request", "standalone verification identity is incomplete")
    if not isinstance(params["expanded_coverage"], bool):
        raise ProtocolError("bad-request", "standalone expanded_coverage must be a boolean")
    identity_matches = (
        record.get("receipt_id") == receipt_id
        and record.get("package_path") == str(package)
        and record.get("receipt_path") == str(receipt_path)
        and record.get("package_name") == params["package_name"]
        and record.get("seed") == params["seed"]
        and record.get("game_root") == str(_required_path(params, "game_root").resolve())
        and record.get("mods_root") == str(_required_path(params, "mods_root"))
        and record.get("options", {}).get("items", {}).get("include_dlc") == params["include_dlc"]
        and record.get("options", {}).get("enemies", {}).get("enabled") == params["randomize_enemies"]
        and record.get("options", {}).get("enemies", {}).get(
            "expanded_coverage", False) == params["expanded_coverage"]
    )
    if not identity_matches:
        raise ProtocolError("verification-failed", "standalone selection differs from prepared export")
    if params["randomize_enemies"] and record.get("options", {}).get(
            "enemies", {}).get("allow_tier_mixing") is not True:
        raise ProtocolError("verification-failed", "standalone enemy build lacks mixed-tier policy")
    expected_receipts = (state_root.expanduser().resolve() / "standalone" / "receipts")
    if receipt_path.parent != expected_receipts or package.parent.name.casefold() != "mods":
        raise ProtocolError("verification-failed", "standalone paths are outside the inactive export")
    if package.parent != Path(record["mods_root"]):
        raise ProtocolError("verification-failed", "standalone package moved from the selected Mods library")
    overlay_path = Path(str(record.get("overlay_path", "")))
    if overlay_path.parent != state_root.expanduser().resolve() / "standalone" / "overlays":
        raise ProtocolError("verification-failed", "standalone build provenance is outside backend state")
    try:
        overlay = validate_overlay(overlay_path)
        receipt = verify_export(package, receipt_path, overlay_root=overlay_path)
        install = GameInstall.from_root(_required_path(params, "game_root"))
        if str(install.root) != record.get("install_root"):
            raise ValueError("selected game installation changed since randomization")
        for relative, expected in overlay.identity["source_hashes"].items():
            original = install.resolve_file(relative, include_mods=False)[1]
            if sha256_file(original) != expected:
                raise ValueError(f"original game input changed since randomization: {relative}")
    except (OSError, ValueError, ValidationError) as error:
        raise ProtocolError("verification-failed", str(error)) from error
    if (receipt["receipt_id"] != receipt_id or receipt["package_name"] != record["package_name"]
            or receipt["seed"] != record["seed"] or receipt["options"] != record["options"]):
        raise ProtocolError("verification-failed", "standalone export differs from prepared identity")
    return _result(receipt, package, receipt_path)
