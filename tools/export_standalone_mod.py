#!/usr/bin/env python3
"""Export a verified standalone randomizer overlay for BBLauncher.

Directory exports write one data-only package into BBLauncher's inactive
``Mods`` library.  ZIP exports contain that same package as their single
top-level directory.  Verification receipts stay outside the package so
BBLauncher only sees native Bloodborne paths.  This command never activates a
mod, writes to a game installation, launches the game, or touches saves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


BUILD_IDENTITY_NAME = "standalone-build-identity.json"
BUILD_RECEIPT_NAME = "standalone-build-receipt.json"
BUILD_IDENTITY_FORMAT = "bb-standalone-build-identity-v1"
BUILD_RECEIPT_FORMAT = "bb-standalone-build-receipt-v1"
EXPORT_RECEIPT_FORMAT = "bb-standalone-bblauncher-export-v1"
GAMEPARAM_PATH = "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"
WAKEUP_EVENT_PATH = "dvdroot_ps4/event/m24_01_00_00.emevd.dcx"
ACTIVE_MODS_DIR_NAME = "Mods-Active (DO NOT DELETE)"
PACKAGE_PREFIX = "Bloodborne-Standalone-"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class ValidatedOverlay:
    root: Path
    identity: Mapping[str, Any]
    receipt: Mapping[str, Any]
    identity_sha256: str
    receipt_sha256: str
    files: tuple[FileRecord, ...]
    payload: tuple[FileRecord, ...]


@dataclass(frozen=True)
class ExportResult:
    package_path: Path
    receipt_path: Path
    receipt: Mapping[str, Any]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _hash_bytes(encoded)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _check_existing_ancestors(path: Path, label: str) -> None:
    candidate = _absolute(path)
    existing = candidate
    while not existing.exists() and not existing.is_symlink() and existing.parent != existing:
        existing = existing.parent
    chain: list[Path] = []
    while True:
        chain.append(existing)
        if existing.parent == existing:
            break
        existing = existing.parent
    for part in reversed(chain):
        if _is_reparse(part):
            raise ValueError(f"{label} crosses a symbolic link or reparse point: {part}")


def _regular_directory(path: Path | str, label: str) -> Path:
    candidate = _absolute(path)
    _check_existing_ancestors(candidate, label)
    if not candidate.is_dir() or _is_reparse(candidate):
        raise ValueError(f"{label} is not a regular directory: {candidate}")
    return candidate


def _safe_relative(raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ValueError(f"{label} has an unsafe relative path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"{label} has an unsafe relative path: {raw!r}")
    if not path.parts or re.fullmatch(r"[A-Za-z]:", path.parts[0]):
        raise ValueError(f"{label} has an unsafe relative path: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw:
        raise ValueError(f"{label} path is not normalized: {raw!r}")
    return normalized


def _parse_records(value: Any, label: str) -> tuple[FileRecord, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    records: list[FileRecord] = []
    folded: dict[str, str] = {}
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {"path", "sha256", "size"}:
            raise ValueError(f"{label}[{index}] must be an exact file record")
        relative = _safe_relative(raw["path"], f"{label}[{index}]")
        prior = folded.get(relative.casefold())
        if prior is not None:
            raise ValueError(f"{label} has a case-insensitive duplicate: {prior}, {relative}")
        size = raw["size"]
        digest = raw["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"{label} has an invalid size for {relative}")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError(f"{label} has an invalid sha256 for {relative}")
        folded[relative.casefold()] = relative
        records.append(FileRecord(relative, size, digest))
    return tuple(sorted(records, key=lambda item: item.path.casefold()))


def _tree_files(root: Path, label: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    folded: dict[str, str] = {}

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as error:
            raise ValueError(f"cannot inspect {label}: {error}") from error
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if _is_reparse(path):
                raise ValueError(f"{label} contains a symbolic link or reparse point: {relative}")
            if entry.is_dir(follow_symlinks=False):
                visit(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise ValueError(f"{label} contains a non-regular entry: {relative}")
            safe = _safe_relative(relative, label)
            prior = folded.get(safe.casefold())
            if prior is not None:
                raise ValueError(f"{label} has a case-insensitive duplicate: {prior}, {safe}")
            folded[safe.casefold()] = safe
            found[safe] = path

    visit(root)
    return found


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase sha256")
    return value


def _is_native_payload_path(relative: str) -> bool:
    if relative in (GAMEPARAM_PATH, WAKEUP_EVENT_PATH):
        return True
    parts = PurePosixPath(relative).parts
    if len(parts) == 4 and parts[:3] == ("dvdroot_ps4", "map", "MapStudio"):
        return parts[3].endswith(".msb.dcx") and len(parts[3]) > len(".msb.dcx")
    if len(parts) == 3 and parts[:2] == ("dvdroot_ps4", "script"):
        return parts[2].endswith(".luabnd.dcx") and len(parts[2]) > len(".luabnd.dcx")
    return False


def validate_overlay(path: Path | str) -> ValidatedOverlay:
    """Validate an unpublished builder overlay without modifying it."""
    root = _regular_directory(path, "standalone overlay")
    files = _tree_files(root, "standalone overlay")
    receipt_path = root / BUILD_RECEIPT_NAME
    identity_path = root / BUILD_IDENTITY_NAME
    if BUILD_RECEIPT_NAME not in files or BUILD_IDENTITY_NAME not in files:
        raise ValueError("standalone overlay is missing its build identity or receipt")
    receipt = _read_object(receipt_path, "standalone build receipt")
    identity = _read_object(identity_path, "standalone build identity")
    if receipt.get("format") != BUILD_RECEIPT_FORMAT or receipt.get("applied") is not True:
        raise ValueError("standalone build receipt is not an applied v1 build")
    if identity.get("format") != BUILD_IDENTITY_FORMAT:
        raise ValueError("standalone build identity has the wrong format")
    seed = identity.get("seed")
    options = identity.get("options")
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("standalone build identity requires a non-empty seed")
    if not isinstance(options, dict) or set(options) != {"items", "enemies"}:
        raise ValueError("standalone build identity requires item and enemy options")
    if not all(isinstance(options[name], dict) for name in ("items", "enemies")):
        raise ValueError("standalone item and enemy options must be objects")
    source_hashes = identity.get("source_hashes")
    if not isinstance(source_hashes, dict) or receipt.get("source_hashes") != source_hashes:
        raise ValueError("standalone receipt source hashes do not match the build identity")
    if not source_hashes:
        raise ValueError("standalone build identity has invalid source hashes")
    folded_sources: set[str] = set()
    for name, source_digest in source_hashes.items():
        safe_name = _safe_relative(name, "standalone source hash")
        if safe_name.casefold() in folded_sources:
            raise ValueError("standalone build identity has duplicate source paths")
        if not isinstance(source_digest, str) or not _SHA256.fullmatch(source_digest):
            raise ValueError("standalone build identity has invalid source hashes")
        folded_sources.add(safe_name.casefold())

    records = _parse_records(receipt.get("files"), "standalone build receipt files")
    by_name = {record.path: record for record in records}
    expected = set(by_name) | {BUILD_RECEIPT_NAME}
    actual = set(files)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"standalone overlay file set differs from receipt; "
            f"missing={missing}, extra={extra}"
        )
    if BUILD_RECEIPT_NAME in by_name:
        raise ValueError("standalone build receipt cannot list itself")
    if BUILD_IDENTITY_NAME not in by_name:
        raise ValueError("standalone build receipt does not record its identity file")
    for record in records:
        source = files[record.path]
        if source.stat().st_size != record.size or _hash_file(source) != record.sha256:
            raise ValueError(f"standalone overlay file drifted from its receipt: {record.path}")

    identity_digest = _hash_file(identity_path)
    recorded_identity = _require_sha256(
        receipt.get("identity_sha256"), "build receipt identity_sha256"
    )
    if recorded_identity != identity_digest:
        raise ValueError("standalone build receipt does not authenticate its identity file")
    gameparam = by_name.get(GAMEPARAM_PATH)
    if gameparam is None:
        raise ValueError("standalone build receipt does not contain the composed gameparam")
    if _require_sha256(
        receipt.get("composed_gameparam_sha256"), "composed gameparam sha256"
    ) != gameparam.sha256:
        raise ValueError("composed gameparam hash does not match its file record")
    item_plan = by_name.get("standalone-item-plan.json")
    if item_plan is None or identity.get("item_plan_sha256") != item_plan.sha256:
        raise ValueError("standalone item plan provenance does not match the build identity")
    enemy_digest = identity.get("enemy_plan_sha256")
    enemy_plan = by_name.get("standalone-enemy-plan.json")
    if enemy_digest is None:
        if enemy_plan is not None:
            raise ValueError("standalone enemy plan exists without identity provenance")
    elif enemy_plan is None or enemy_digest != enemy_plan.sha256:
        raise ValueError("standalone enemy plan provenance does not match the build identity")

    plan = (_read_object(root / "standalone-enemy-plan.json", "standalone enemy plan")
            if enemy_plan is not None else {})
    fallbacks = plan.get("wakeup_fallbacks", [])
    wakeup = receipt.get("wakeup_writer")
    if fallbacks:
        event = by_name.get(WAKEUP_EVENT_PATH)
        report_record = by_name.get("wakeup-fallback-report.json")
        if event is None or report_record is None or not isinstance(wakeup, dict):
            raise ValueError("standalone wakeup fallback requires its event and writer receipt")
        report = _read_object(root / report_record.path, "standalone wakeup receipt")
        if (report != wakeup or report.get("format") != "bb-enemizer-wakeup-fallback-v1"
                or report.get("applied") is not True
                or report.get("plan_sha256") != enemy_digest
                or report.get("wakeup_fallbacks") != fallbacks
                or report.get("source_event_sha256") != source_hashes.get(WAKEUP_EVENT_PATH)
                or WAKEUP_EVENT_PATH not in source_hashes
                or report.get("output_event_sha256") != event.sha256):
            raise ValueError("standalone wakeup receipt differs from its plan, source or output")
    elif WAKEUP_EVENT_PATH in by_name or wakeup is not None:
        raise ValueError("standalone wakeup event has no planned fallback")

    game_records = tuple(
        record for record in records if record.path.startswith("dvdroot_ps4/")
    )
    unexpected_game_paths = [
        record.path for record in game_records if not _is_native_payload_path(record.path)
    ]
    if unexpected_game_paths:
        raise ValueError(
            "standalone build contains an unexpected game-data payload path: "
            + ", ".join(unexpected_game_paths)
        )
    payload = game_records
    if not payload:
        raise ValueError("standalone build contains no BBLauncher game-data payload")
    return ValidatedOverlay(
        root=root,
        identity=identity,
        receipt=receipt,
        identity_sha256=identity_digest,
        receipt_sha256=_hash_file(receipt_path),
        files=records,
        payload=payload,
    )


def _safe_seed(seed: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", seed.strip()).strip(" .-_")
    return (value or "Seed")[:48].rstrip(" .") or "Seed"


def package_name(overlay: ValidatedOverlay) -> str:
    seed = _safe_seed(str(overlay.identity["seed"]))
    return f"{PACKAGE_PREFIX}{seed}-{overlay.identity_sha256[:12]}"


def _overlap(left: Path, right: Path) -> bool:
    try:
        common = os.path.commonpath((os.path.normcase(str(left)), os.path.normcase(str(right))))
    except ValueError:
        return False
    return common in {os.path.normcase(str(left)), os.path.normcase(str(right))}


def _refuse_active(path: Path, label: str) -> None:
    if any(part.casefold() == ACTIVE_MODS_DIR_NAME.casefold() for part in path.parts):
        raise ValueError(f"{label} cannot be inside BBLauncher's active Mods directory")


def _receipt_document(
    overlay: ValidatedOverlay,
    *,
    name: str,
    kind: str,
    archive_sha256: str | None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "format": EXPORT_RECEIPT_FORMAT,
        "receipt_id": "",
        "package_name": name,
        "package_kind": kind,
        "display_name": f"Bloodborne Standalone Randomizer — {overlay.identity['seed']}",
        "seed": overlay.identity["seed"],
        "options": overlay.identity["options"],
        "build": {
            "identity_format": BUILD_IDENTITY_FORMAT,
            "identity_sha256": overlay.identity_sha256,
            "receipt_format": BUILD_RECEIPT_FORMAT,
            "receipt_sha256": overlay.receipt_sha256,
        },
        "files": [record.as_dict() for record in overlay.payload],
        "archive_sha256": archive_sha256,
        "installation": {
            "manager": "BBLauncher",
            "library_directory": "Mods",
            "activation": "Activate this package with BBLauncher's Mod Manager.",
        },
        "validation": {
            "build_receipt_verified": True,
            "gameplay_tested": False,
        },
    }
    payload = dict(receipt)
    payload.pop("receipt_id")
    receipt["receipt_id"] = _canonical_hash(payload)
    return receipt


def _write_receipt(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite existing export receipt: {path}")
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _receipt_path(receipt_root: Path, name: str) -> Path:
    return receipt_root / f"{name}.export-receipt.json"


def _ensure_roots(
    overlay: ValidatedOverlay, output_root: Path | str, receipt_root: Path | str
) -> tuple[Path, Path]:
    output = _regular_directory(output_root, "export output root")
    receipts = _regular_directory(receipt_root, "export receipt root")
    _refuse_active(output, "export output root")
    _refuse_active(receipts, "export receipt root")
    if _overlap(output, overlay.root) or _overlap(receipts, overlay.root):
        raise ValueError("export destinations must stay outside the generated overlay")
    return output, receipts


def _verify_directory_files(root: Path, records: tuple[FileRecord, ...]) -> None:
    actual = _tree_files(root, "exported BBLauncher package")
    expected = {record.path: record for record in records}
    if set(actual) != set(expected):
        raise ValueError("exported BBLauncher package file set differs from its receipt")
    for relative, record in expected.items():
        path = actual[relative]
        if path.stat().st_size != record.size or _hash_file(path) != record.sha256:
            raise ValueError(f"exported BBLauncher package file drifted: {relative}")


def export_directory(
    overlay_root: Path | str, *, mods_root: Path | str, receipt_root: Path | str
) -> ExportResult:
    """Publish one verified package into an existing inactive ``Mods`` library."""
    overlay = validate_overlay(overlay_root)
    mods, receipts = _ensure_roots(overlay, mods_root, receipt_root)
    if mods.name.casefold() != "mods":
        raise ValueError("directory export requires BBLauncher's inactive directory named Mods")
    if _overlap(receipts, mods.parent):
        raise ValueError("export receipts must stay outside BBLauncher's managed directory")
    name = package_name(overlay)
    target = mods / name
    receipt_path = _receipt_path(receipts, name)
    if target.exists() or target.is_symlink():
        raise ValueError(f"refusing to overwrite existing BBLauncher package: {target}")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError(f"refusing to overwrite existing export receipt: {receipt_path}")
    active_root = mods.with_name(ACTIVE_MODS_DIR_NAME)
    if active_root.exists() or active_root.is_symlink():
        active = _regular_directory(active_root, "BBLauncher active Mods directory")
        if any(child.name.casefold() == name.casefold() for child in active.iterdir()):
            raise ValueError(
                "the same package name already exists in BBLauncher's active Mods directory"
            )

    stage = mods / f".{name}.staging-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        for record in overlay.payload:
            source = overlay.root.joinpath(*PurePosixPath(record.path).parts)
            destination = stage.joinpath(*PurePosixPath(record.path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        _verify_directory_files(stage, overlay.payload)
        validate_overlay(overlay.root)
        receipt = _receipt_document(
            overlay, name=name, kind="directory", archive_sha256=None
        )
        _write_receipt(receipt_path, receipt)
        if target.exists() or target.is_symlink():
            raise ValueError(f"refusing to overwrite existing BBLauncher package: {target}")
        os.rename(stage, target)
    finally:
        if stage.exists() and not _is_reparse(stage):
            shutil.rmtree(stage)
    return ExportResult(target, receipt_path, receipt)


def _write_zip(path: Path, name: str, overlay: ValidatedOverlay) -> None:
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for record in overlay.payload:
            source = overlay.root.joinpath(*PurePosixPath(record.path).parts)
            info = zipfile.ZipInfo(f"{name}/{record.path}", date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            with source.open("rb") as input_stream, archive.open(
                info, "w", force_zip64=True
            ) as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)


def _verify_zip_files(path: Path, name: str, records: tuple[FileRecord, ...]) -> None:
    expected = {f"{name}/{record.path}": record for record in records}
    try:
        with zipfile.ZipFile(path) as archive:
            actual: dict[str, zipfile.ZipInfo] = {}
            folded: dict[str, str] = {}
            for info in archive.infolist():
                relative = _safe_relative(info.filename, "BBLauncher ZIP entry")
                if info.is_dir():
                    raise ValueError(
                        f"BBLauncher ZIP contains an unexpected directory entry: {relative}"
                    )
                prior = folded.get(relative.casefold())
                if prior is not None:
                    raise ValueError(
                        f"BBLauncher ZIP has a case-insensitive duplicate: {prior}, {relative}"
                    )
                folded[relative.casefold()] = relative
                actual[relative] = info
            if set(actual) != set(expected):
                raise ValueError("BBLauncher ZIP file set differs from its receipt")
            for relative, record in expected.items():
                data = archive.read(actual[relative])
                if len(data) != record.size or _hash_bytes(data) != record.sha256:
                    raise ValueError(f"BBLauncher ZIP file drifted: {relative}")
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError(f"cannot verify BBLauncher ZIP: {error}") from error


def export_zip(
    overlay_root: Path | str, *, zip_root: Path | str, receipt_root: Path | str
) -> ExportResult:
    """Publish one deterministic, extraction-ready BBLauncher package ZIP."""
    overlay = validate_overlay(overlay_root)
    output, receipts = _ensure_roots(overlay, zip_root, receipt_root)
    if output.name.casefold() == "mods":
        raise ValueError("ZIP export root cannot be BBLauncher's live Mods library")
    name = package_name(overlay)
    target = output / f"{name}.zip"
    receipt_path = _receipt_path(receipts, name)
    for path, label in ((target, "ZIP"), (receipt_path, "export receipt")):
        if path.exists() or path.is_symlink():
            raise ValueError(f"refusing to overwrite existing {label}: {path}")
    stage = output / f".{name}.staging-{uuid.uuid4().hex}.zip"
    try:
        _write_zip(stage, name, overlay)
        _verify_zip_files(stage, name, overlay.payload)
        validate_overlay(overlay.root)
        receipt = _receipt_document(
            overlay, name=name, kind="zip", archive_sha256=_hash_file(stage)
        )
        _write_receipt(receipt_path, receipt)
        if target.exists() or target.is_symlink():
            raise ValueError(f"refusing to overwrite existing ZIP: {target}")
        os.rename(stage, target)
    finally:
        if stage.exists() and not _is_reparse(stage):
            stage.unlink()
    return ExportResult(target, receipt_path, receipt)


def load_export_receipt(path: Path | str) -> dict[str, Any]:
    source = _absolute(path)
    _check_existing_ancestors(source, "export receipt")
    if not source.is_file() or _is_reparse(source):
        raise ValueError(f"export receipt is not a regular file: {source}")
    receipt = _read_object(source, "standalone BBLauncher export receipt")
    expected_keys = {
        "format", "receipt_id", "package_name", "package_kind", "display_name",
        "seed", "options", "build", "files", "archive_sha256", "installation",
        "validation",
    }
    if set(receipt) != expected_keys or receipt.get("format") != EXPORT_RECEIPT_FORMAT:
        raise ValueError("standalone BBLauncher export receipt has the wrong format or fields")
    raw_build = receipt.get("build")
    identity_digest = (
        raw_build.get("identity_sha256") if isinstance(raw_build, dict) else None
    )
    if not isinstance(receipt.get("seed"), str) or not receipt["seed"].strip():
        raise ValueError("standalone BBLauncher export receipt has no seed")
    if not isinstance(receipt.get("options"), dict):
        raise ValueError("standalone BBLauncher export receipt has invalid options")
    if set(receipt["options"]) != {"items", "enemies"} or not all(
        isinstance(receipt["options"].get(name), dict) for name in ("items", "enemies")
    ):
        raise ValueError("standalone BBLauncher export receipt has invalid options")
    identity_digest = _require_sha256(identity_digest, "export build identity sha256")
    expected_name = f"{PACKAGE_PREFIX}{_safe_seed(receipt['seed'])}-{identity_digest[:12]}"
    if receipt.get("package_name") != expected_name:
        raise ValueError("standalone BBLauncher export receipt has an invalid package name")
    if receipt.get("display_name") != f"Bloodborne Standalone Randomizer — {receipt['seed']}":
        raise ValueError("standalone BBLauncher export receipt has an invalid display name")
    if receipt.get("package_kind") not in ("directory", "zip"):
        raise ValueError("standalone BBLauncher export receipt has an invalid package kind")
    build = receipt.get("build")
    if (
        not isinstance(build, dict)
        or set(build) != {"identity_format", "identity_sha256", "receipt_format", "receipt_sha256"}
        or build.get("identity_format") != BUILD_IDENTITY_FORMAT
        or build.get("receipt_format") != BUILD_RECEIPT_FORMAT
    ):
        raise ValueError("standalone BBLauncher export receipt has invalid build provenance")
    _require_sha256(build.get("receipt_sha256"), "export build receipt sha256")
    records = _parse_records(receipt.get("files"), "export receipt files")
    invalid_payload = [
        record.path for record in records if not _is_native_payload_path(record.path)
    ]
    if invalid_payload:
        raise ValueError(
            "export receipt contains an unexpected game-data payload path: "
            + ", ".join(invalid_payload)
        )
    archive_digest = receipt.get("archive_sha256")
    if receipt["package_kind"] == "zip":
        _require_sha256(archive_digest, "export archive sha256")
    elif archive_digest is not None:
        raise ValueError("directory export receipt unexpectedly records an archive hash")
    if receipt.get("installation") != {
        "manager": "BBLauncher",
        "library_directory": "Mods",
        "activation": "Activate this package with BBLauncher's Mod Manager.",
    }:
        raise ValueError("standalone BBLauncher export receipt has invalid installation metadata")
    if receipt.get("validation") != {
        "build_receipt_verified": True,
        "gameplay_tested": False,
    }:
        raise ValueError("standalone BBLauncher export receipt has invalid validation metadata")
    payload = dict(receipt)
    receipt_id = payload.pop("receipt_id")
    if not isinstance(receipt_id, str) or receipt_id != _canonical_hash(payload):
        raise ValueError("standalone BBLauncher export receipt identity digest does not match")
    return receipt


def verify_export(
    package_path: Path | str,
    receipt_path: Path | str,
    *,
    overlay_root: Path | str | None = None,
) -> Mapping[str, Any]:
    """Verify exported bytes, and optionally their original build provenance."""
    package = _absolute(package_path)
    receipt = load_export_receipt(receipt_path)
    records = _parse_records(receipt["files"], "export receipt files")
    name = receipt["package_name"]
    if receipt["package_kind"] == "directory":
        if package.name != name or not package.is_dir() or _is_reparse(package):
            raise ValueError("exported directory does not match its receipt package name")
        _verify_directory_files(package, records)
    else:
        if package.name != f"{name}.zip" or not package.is_file() or _is_reparse(package):
            raise ValueError("exported ZIP does not match its receipt package name")
        if _hash_file(package) != receipt["archive_sha256"]:
            raise ValueError("exported ZIP hash changed from its receipt")
        _verify_zip_files(package, name, records)
    if overlay_root is not None:
        overlay = validate_overlay(overlay_root)
        if (
            overlay.identity_sha256 != receipt["build"]["identity_sha256"]
            or overlay.receipt_sha256 != receipt["build"]["receipt_sha256"]
            or overlay.identity["seed"] != receipt["seed"]
            or overlay.identity["options"] != receipt["options"]
            or [record.as_dict() for record in overlay.payload] != receipt["files"]
        ):
            raise ValueError("export receipt provenance does not match the standalone overlay")
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="export a verified standalone overlay")
    export.add_argument("--overlay", type=Path, required=True)
    destination = export.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--mods-root", type=Path, help="existing inactive BBLauncher Mods directory"
    )
    destination.add_argument(
        "--zip-root", type=Path, help="existing directory for an extraction-ready ZIP"
    )
    export.add_argument("--receipt-root", type=Path, required=True)

    verify = commands.add_parser("verify", help="verify a directory or ZIP export")
    verify.add_argument("--package", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--overlay", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "export":
        if args.mods_root is not None:
            result = export_directory(
                args.overlay, mods_root=args.mods_root, receipt_root=args.receipt_root
            )
        else:
            result = export_zip(
                args.overlay, zip_root=args.zip_root, receipt_root=args.receipt_root
            )
        print(f"Verified BBLauncher package: {result.package_path}")
        print(f"Verification receipt: {result.receipt_path}")
        return 0
    receipt = verify_export(args.package, args.receipt, overlay_root=args.overlay)
    print(f"Verified BBLauncher export: {receipt['package_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
