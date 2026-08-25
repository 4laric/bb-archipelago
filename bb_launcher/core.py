"""Safe seed caching, shadPS4 overlay activation, and process launch.

Only launcher-owned files may enter ``CUSA03173-mods``.  Base and update trees
are read-only inputs and never appear as mutation targets in this module.

Player-supplied mods live in the sibling ``CUSA03173-mods-user`` directory,
which the launcher only ever *reads*.  Activation copies its files into the
staged overlay alongside the generated ones and records them in the ownership
manifest, so the launcher still owns ``CUSA03173-mods`` exclusively and the
activation transaction is unchanged.  Archipelago-owned paths always win: a
user file that collides with one is excluded and reported, never merged.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence, TextIO


SERIAL = "CUSA03173"
APP_VERSION = "01.09"
BASE_DIR_NAME = SERIAL
PATCH_DIR_NAMES = (f"{SERIAL}-patch", f"{SERIAL}-UPDATE")
MODS_DIR_NAME = f"{SERIAL}-mods"
USER_MODS_DIR_NAME = f"{SERIAL}-mods-user"
SEED_MANIFEST_NAME = "seed-manifest.json"
SEED_MANIFEST_FORMAT = "bb-launcher-seed-build-v1"
OWNER_NAME = ".bb-ap-owner.json"
OWNER_FORMAT = "bb-launcher-overlay-owner-v1"
TRANSACTION_NAME = ".bb-ap-launcher-transaction.json"
TRANSACTION_FORMAT = "bb-launcher-activation-transaction-v1"
DVDROOT_PREFIX = "dvdroot_ps4/"
SUPPRESSION_PATH = f"{DVDROOT_PREFIX}param/gameparam/gameparam.parambnd.dcx"
MAP_PREFIX = f"{DVDROOT_PREFIX}map/MapStudio/"
USER_MERGE_FORMAT = "bb-launcher-user-merge-v1"
# Names the launcher's own transaction and ownership machinery uses inside the
# overlay.  A user file claiming one of them is excluded, not merged.
RESERVED_OVERLAY_PREFIX = ".bb-ap-"
EXCLUDED_AP_OWNED = "ap-owned"
EXCLUDED_RESERVED = "reserved"
# A user file whose overlay path does not begin with dvdroot_ps4/ is a path
# shadPS4 never resolves: merging it is indistinguishable from doing nothing,
# which is exactly how a wrapper-folder mod tree failed silently
# (bb-archipelago#173).  Excluded, and reported by wrapper so the remedy is
# one move per mod rather than one per file.
EXCLUDED_DEAD_PATH = "dead-path"


class LauncherError(RuntimeError):
    """Base class for actionable launcher failures."""


class ValidationError(LauncherError):
    """An input, build, or installed overlay failed closed."""


class DiscoveryError(LauncherError):
    """Automatic setup discovery was missing or ambiguous."""


class ConflictError(LauncherError):
    """Unowned content would be affected by an operation."""


class RecoveryError(LauncherError):
    """An interrupted transaction could not be recovered safely."""


class LaunchError(LauncherError):
    """A configured process could not be started safely."""


def canonical_json(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"value is not canonical JSON: {exc}") from exc
    return text.encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: str, label: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValidationError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} {path} is not a JSON object")
    return value


def _safe_overlay_path(raw: str) -> str:
    value = raw.replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError(f"unsafe overlay path: {raw!r}")
    normalized = path.as_posix()
    is_suppression = normalized == SUPPRESSION_PATH
    is_map = (
        normalized.startswith(MAP_PREFIX)
        and "/" not in normalized[len(MAP_PREFIX):]
        and normalized.lower().endswith(".msb.dcx")
    )
    if not is_suppression and not is_map:
        raise ValidationError(
            f"overlay path is outside the param/map contract: {normalized}"
        )
    return normalized


def _safe_relative_path(raw: str) -> PurePosixPath:
    value = raw.replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError(f"unsafe game-relative path: {raw!r}")
    return path


def _tree_files(root: Path, *, ignore: Iterable[str] = ()) -> dict[str, Path]:
    ignored = set(ignore)
    found: dict[str, Path] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValidationError(f"symbolic links are not allowed in managed trees: {path}")
        if path.is_file() and relative not in ignored:
            found[relative] = path
    return found


@dataclass(frozen=True)
class UserModExclusion:
    """One user file that was not merged, and why."""

    path: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}


@dataclass(frozen=True)
class UserModMerge:
    """The decided file set for one activation: what merges, what does not.

    Pure policy over path sets -- no filesystem access -- so the conflict rule
    is testable on its own.  Archipelago-owned overlay paths always win; a user
    file claiming one is excluded and reported rather than merged or dropped
    silently.  Comparison is case-insensitive because the overlay is consumed
    on case-insensitive filesystems, where two such paths are one file.
    """

    merged: Mapping[str, str]
    excluded: tuple[UserModExclusion, ...]

    @property
    def fingerprint(self) -> str:
        """Digest of the decision, so a changed user directory forces a rebuild."""

        payload = {
            "format": USER_MERGE_FORMAT,
            "merged": sorted(self.merged.items()),
            "excluded": [exclusion.as_dict() for exclusion in self.excluded],
        }
        return hashlib.sha256(canonical_json(payload)).hexdigest()


def plan_user_merge(
    user_hashes: Mapping[str, str], owned_paths: Iterable[str]
) -> UserModMerge:
    """Decide which user files may enter the overlay beside the owned ones."""

    protected = {str(path).replace("\\", "/").casefold() for path in owned_paths}
    merged: dict[str, str] = {}
    excluded: list[UserModExclusion] = []
    for relative in sorted(user_hashes):
        normalized = _safe_relative_path(relative).as_posix()
        digest = _require_sha256(str(user_hashes[relative]), f"user mod file {normalized!r}")
        parts = PurePosixPath(normalized).parts
        if any(part.startswith(RESERVED_OVERLAY_PREFIX) for part in parts):
            excluded.append(UserModExclusion(normalized, EXCLUDED_RESERVED))
            continue
        if normalized.casefold() in protected:
            excluded.append(UserModExclusion(normalized, EXCLUDED_AP_OWNED))
            continue
        if not normalized.casefold().startswith(DVDROOT_PREFIX.casefold()):
            excluded.append(UserModExclusion(normalized, EXCLUDED_DEAD_PATH))
            continue
        merged[normalized] = digest
    return UserModMerge(merged, tuple(excluded))


def dead_path_wrappers(
    exclusions: Iterable[UserModExclusion],
) -> tuple[tuple[str, int], ...]:
    """Group dead-path exclusions by their top-level folder, largest first.

    Mods ship one wrapper folder each, so a mistaken tree produces one wrapper
    with many dead files, not many unrelated ones.  Reporting the wrapper names
    the single move that fixes every file under it.
    """

    counts: dict[str, int] = {}
    for exclusion in exclusions:
        if exclusion.reason != EXCLUDED_DEAD_PATH:
            continue
        parts = PurePosixPath(exclusion.path).parts
        wrapper = parts[0] if len(parts) > 1 else exclusion.path
        counts[wrapper] = counts.get(wrapper, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def dead_path_remedy(wrapper: str) -> str:
    """The one sentence that fixes a wrapper folder, named for that wrapper."""

    return (
        f"move the contents of {wrapper} up one level so paths start with "
        f"{DVDROOT_PREFIX}"
    )


def collect_user_mod_files(root: Path) -> dict[str, Path]:
    """Read the player's mods directory. Never written, never renamed."""

    if not root.exists():
        return {}
    if not root.is_dir() or root.is_symlink():
        raise ConflictError(f"user mods path is not a regular directory: {root}")
    found: dict[str, Path] = {}
    for relative, path in _tree_files(root).items():
        found[_safe_relative_path(relative).as_posix()] = path
    return found


@dataclass(frozen=True)
class SeedIdentity:
    """Every input that can change a generated overlay."""

    seed: str
    slot: str
    world_build: str
    runtime_build: str
    shad_build: str
    source_hashes: Mapping[str, str]
    options: Mapping[str, Any] = field(default_factory=dict)
    enemizer_seed: str | None = None
    suppression_plan_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        for label, value in (
            ("seed", self.seed),
            ("slot", self.slot),
            ("world_build", self.world_build),
            ("runtime_build", self.runtime_build),
            ("shad_build", self.shad_build),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"seed identity {label} must be a non-empty string")
        if not self.source_hashes:
            raise ValidationError("seed identity requires at least one source hash")
        sources = {}
        for name, digest in sorted(self.source_hashes.items()):
            relative = _safe_relative_path(str(name)).as_posix()
            sources[relative] = _require_sha256(str(digest), f"source hash {relative!r}")
        plan_hash = None
        if self.suppression_plan_sha256 is not None:
            plan_hash = _require_sha256(
                self.suppression_plan_sha256, "suppression_plan_sha256"
            )
        value = {
            "seed": self.seed,
            "slot": self.slot,
            "world_build": self.world_build,
            "runtime_build": self.runtime_build,
            "shad_build": self.shad_build,
            "source_hashes": sources,
            "options": dict(self.options),
            "enemizer_seed": self.enemizer_seed,
            "suppression_plan_sha256": plan_hash,
        }
        canonical_json(value)
        return value

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(canonical_json(self.as_dict())).hexdigest()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SeedIdentity":
        required = ("seed", "slot", "world_build", "runtime_build", "shad_build", "source_hashes")
        missing = [name for name in required if name not in value]
        if missing:
            raise ValidationError(f"seed identity is missing: {', '.join(missing)}")
        sources = value["source_hashes"]
        options = value.get("options", {})
        if not isinstance(sources, dict) or not isinstance(options, dict):
            raise ValidationError("source_hashes and options must be JSON objects")
        identity = cls(
            seed=str(value["seed"]),
            slot=str(value["slot"]),
            world_build=str(value["world_build"]),
            runtime_build=str(value["runtime_build"]),
            shad_build=str(value["shad_build"]),
            source_hashes={str(key): str(digest) for key, digest in sources.items()},
            options=options,
            enemizer_seed=(
                None if value.get("enemizer_seed") is None else str(value["enemizer_seed"])
            ),
            suppression_plan_sha256=(
                None
                if value.get("suppression_plan_sha256") is None
                else str(value["suppression_plan_sha256"])
            ),
        )
        identity.as_dict()
        return identity


@dataclass(frozen=True)
class BuildResult:
    path: Path
    manifest: Mapping[str, Any]
    reused: bool

    @property
    def cache_key(self) -> str:
        return str(self.manifest["cache_key"])


class SeedCache:
    """Hash-addressed overlay builds stored outside the game installation."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()

    def path_for(self, cache_key: str) -> Path:
        _require_sha256(cache_key, "cache key")
        return self.root / cache_key

    def build(
        self,
        identity: SeedIdentity,
        suppression_binder: Path | str,
        map_studio: Path | str | None = None,
    ) -> BuildResult:
        key = identity.cache_key
        destination = self.path_for(key)
        if destination.exists():
            result = self.verify(destination)
            if result.manifest["identity"] != identity.as_dict():
                raise ValidationError(f"cache key collision or identity drift at {destination}")
            return BuildResult(destination, result.manifest, True)

        binder = Path(suppression_binder).expanduser().resolve()
        if not binder.is_file() or binder.is_symlink():
            raise ValidationError(f"suppression binder is not a regular file: {binder}")
        maps: list[Path] = []
        if map_studio is not None:
            map_root = Path(map_studio).expanduser().resolve()
            if not map_root.is_dir() or map_root.is_symlink():
                raise ValidationError(f"MapStudio input is not a directory: {map_root}")
            entries = list(map_root.iterdir())
            invalid_entries = [
                path.name
                for path in entries
                if not path.is_file() or path.is_symlink() or not path.name.lower().endswith(".msb.dcx")
            ]
            if invalid_entries:
                raise ValidationError(
                    "MapStudio contains non-MSB output entries: "
                    + ", ".join(sorted(invalid_entries))
                )
            maps = sorted(
                entries,
                key=lambda path: path.name.lower(),
            )
            if not maps:
                raise ValidationError("MapStudio input contains no *.msb.dcx files")
        if identity.enemizer_seed is not None and not maps:
            raise ValidationError("enemizer_seed is set but no MapStudio outputs were supplied")
        if maps and identity.enemizer_seed is None:
            raise ValidationError("MapStudio outputs require an enemizer_seed in the cache identity")

        self.root.mkdir(parents=True, exist_ok=True)
        stage = self.root / f".{key}.staging-{uuid.uuid4().hex}"
        stage.mkdir()
        try:
            inputs = [(SUPPRESSION_PATH, binder, "suppression")]
            inputs.extend(
                (f"{MAP_PREFIX}{path.name}", path, "enemizer") for path in maps
            )
            records: list[dict[str, Any]] = []
            for relative, source, component in inputs:
                relative = _safe_overlay_path(relative)
                output = stage.joinpath(*PurePosixPath(relative).parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, output)
                source_hash = sha256_file(source)
                output_hash = sha256_file(output)
                if source_hash != output_hash:
                    raise ValidationError(f"copy verification failed for {relative}")
                records.append(
                    {
                        "path": relative,
                        "size": output.stat().st_size,
                        "sha256": output_hash,
                        "component": component,
                    }
                )
            records.sort(key=lambda record: record["path"])
            manifest = {
                "format": SEED_MANIFEST_FORMAT,
                "cache_key": key,
                "identity": identity.as_dict(),
                "files": records,
                "suppression": {
                    "path": SUPPRESSION_PATH,
                    "sha256": next(
                        record["sha256"] for record in records if record["path"] == SUPPRESSION_PATH
                    ),
                    "plan_sha256": identity.suppression_plan_sha256,
                },
                "enemizer": {
                    "enabled": bool(maps),
                    "seed": identity.enemizer_seed,
                    "file_count": len(maps),
                },
            }
            _write_json_atomic(stage / SEED_MANIFEST_NAME, manifest)
            self.verify(stage, expected_key=key)
            try:
                os.replace(stage, destination)
            except FileExistsError:
                existing = self.verify(destination, expected_key=key)
                return BuildResult(destination, existing.manifest, True)
            verified = self.verify(destination, expected_key=key)
            return BuildResult(destination, verified.manifest, False)
        finally:
            if stage.exists():
                # This path is constructed directly beneath the cache root and
                # is never derived from user-supplied relative path data.
                shutil.rmtree(stage)

    def verify(self, path: Path | str, expected_key: str | None = None) -> BuildResult:
        root = Path(path).expanduser().resolve()
        if not root.is_dir() or root.is_symlink():
            raise ValidationError(f"seed build is not a regular directory: {root}")
        manifest_path = root / SEED_MANIFEST_NAME
        manifest = _read_json(manifest_path, "seed manifest")
        if manifest.get("format") != SEED_MANIFEST_FORMAT:
            raise ValidationError(f"unsupported seed manifest format in {manifest_path}")
        identity_value = manifest.get("identity")
        if not isinstance(identity_value, dict):
            raise ValidationError("seed manifest identity is not an object")
        identity = SeedIdentity.from_dict(identity_value)
        key = str(manifest.get("cache_key", ""))
        _require_sha256(key, "seed manifest cache_key")
        if key != identity.cache_key:
            raise ValidationError("seed manifest cache key does not match its identity")
        if expected_key is not None and key != expected_key:
            raise ValidationError(f"expected cache key {expected_key}, got {key}")
        raw_records = manifest.get("files")
        if not isinstance(raw_records, list) or not raw_records:
            raise ValidationError("seed manifest carries no output files")
        expected: dict[str, Mapping[str, Any]] = {}
        for record in raw_records:
            if not isinstance(record, dict):
                raise ValidationError("seed manifest file record is not an object")
            relative = _safe_overlay_path(str(record.get("path", "")))
            if relative in expected:
                raise ValidationError(f"duplicate seed output path: {relative}")
            expected[relative] = record
        if SUPPRESSION_PATH not in expected:
            raise ValidationError("seed build is missing the suppression binder")
        actual = _tree_files(root, ignore=(SEED_MANIFEST_NAME,))
        if set(actual) != set(expected):
            raise ValidationError(
                "seed build file set drift: "
                f"missing={sorted(set(expected) - set(actual))} "
                f"unexpected={sorted(set(actual) - set(expected))}"
            )
        for relative, record in expected.items():
            path_value = actual[relative]
            digest = _require_sha256(str(record.get("sha256", "")), f"output {relative}")
            if path_value.stat().st_size != record.get("size"):
                raise ValidationError(f"seed output size changed: {relative}")
            if sha256_file(path_value) != digest:
                raise ValidationError(f"seed output hash changed: {relative}")
        suppression = manifest.get("suppression")
        if not isinstance(suppression, dict):
            raise ValidationError("seed manifest is missing its suppression witness")
        if suppression.get("path") != SUPPRESSION_PATH:
            raise ValidationError("suppression witness points outside the overlay binder")
        if suppression.get("sha256") != expected[SUPPRESSION_PATH].get("sha256"):
            raise ValidationError("suppression witness hash does not match the binder record")
        return BuildResult(root, manifest, False)


def read_param_sfo(path: Path | str) -> dict[str, str]:
    """Read the string fields needed to validate a PS4 installation."""

    source = Path(path)
    try:
        data = source.read_bytes()
        magic, _version, keys_offset, values_offset, count = struct.unpack_from("<4s4I", data, 0)
    except (OSError, struct.error) as exc:
        raise ValidationError(f"could not read PARAM.SFO {source}: {exc}") from exc
    if magic != b"\x00PSF":
        raise ValidationError(f"invalid PARAM.SFO magic: {source}")
    entries_offset = 20
    result: dict[str, str] = {}
    try:
        for index in range(count):
            key_offset, data_format, length, _maximum, value_offset = struct.unpack_from(
                "<HHIII", data, entries_offset + index * 16
            )
            key_start = keys_offset + key_offset
            key_end = data.index(b"\0", key_start)
            key = data[key_start:key_end].decode("utf-8")
            value = data[values_offset + value_offset:values_offset + value_offset + length]
            if data_format in (0x0204, 0x0004):
                result[key] = value.rstrip(b"\0").decode("utf-8")
    except (IndexError, UnicodeError, ValueError, struct.error) as exc:
        raise ValidationError(f"malformed PARAM.SFO {source}: {exc}") from exc
    return result


def _foreign_serial_dirs(candidate: Path) -> list[str]:
    """Title-ID directories under ``candidate`` that are not the supported install.

    Used to turn a generic "missing base game directory" into a diagnostic that
    names the wrong region (e.g. an EU CUSA00900 install) when one is present.
    """
    if not candidate.is_dir():
        return []
    known = {
        BASE_DIR_NAME.casefold(),
        MODS_DIR_NAME.casefold(),
        USER_MODS_DIR_NAME.casefold(),
        *(name.casefold() for name in PATCH_DIR_NAMES),
    }
    try:
        found = [
            entry.name
            for entry in candidate.iterdir()
            if entry.is_dir()
            and entry.name.upper().startswith("CUSA")
            and entry.name.casefold() not in known
        ]
    except OSError:
        return []
    return sorted(found)


@dataclass(frozen=True)
class GameInstall:
    root: Path
    base: Path
    patch: Path | None
    mods: Path
    serial: str = SERIAL
    app_version: str = APP_VERSION

    @classmethod
    def from_root(cls, root: Path | str) -> "GameInstall":
        candidate = Path(root).expanduser().resolve()
        if candidate.name.casefold() == BASE_DIR_NAME.casefold():
            candidate = candidate.parent
        base = candidate / BASE_DIR_NAME
        patches = [candidate / name for name in PATCH_DIR_NAMES if (candidate / name).is_dir()]
        if not base.is_dir():
            foreign = _foreign_serial_dirs(candidate)
            if foreign:
                raise ValidationError(
                    f"found {', '.join(foreign)} but only {SERIAL} AppVer "
                    f"{APP_VERSION} is supported: {base}"
                )
            raise ValidationError(f"missing base game directory: {base}")
        if len(patches) > 1:
            raise ValidationError(
                f"expected at most one {SERIAL} {APP_VERSION} update directory, "
                f"found {len(patches)}"
            )
        patch = patches[0] if patches else None
        if base.is_symlink() or (patch is not None and patch.is_symlink()):
            raise ValidationError("base and update directories may not be symbolic links")
        base_sfo = read_param_sfo(base / "sce_sys" / "param.sfo")
        # Two valid shapes: a two-layer install (base + official update in a
        # patch directory) or a merged dump whose base is already at 01.09.
        # A patch directory that exists but lacks its param.sfo is an error,
        # not a merged install -- silently ignoring it would mask a corrupt or
        # hand-assembled tree.
        if patch is not None:
            patch_sfo = read_param_sfo(patch / "sce_sys" / "param.sfo")
            serial = patch_sfo.get("TITLE_ID", base_sfo.get("TITLE_ID"))
            version = patch_sfo.get("APP_VER")
            version_source = "update"
        else:
            serial = base_sfo.get("TITLE_ID")
            version = base_sfo.get("APP_VER")
            version_source = "merged base"
        if serial != SERIAL:
            raise ValidationError(f"expected serial {SERIAL}, installation reports {serial!r}")
        if version != APP_VERSION:
            raise ValidationError(
                f"expected {SERIAL} AppVer {APP_VERSION}, {version_source} reports {version!r}"
            )
        return cls(candidate, base, patch, candidate / MODS_DIR_NAME)

    @property
    def user_mods(self) -> Path:
        """Player-owned mods directory. Read-only to the launcher, always."""

        return self.root / USER_MODS_DIR_NAME

    def content_backends(self) -> list[tuple[str, Path]]:
        """Patch-then-base layers holding source game content (never mods)."""
        backends: list[tuple[str, Path]] = []
        if self.patch is not None:
            backends.append(("patch", self.patch))
        backends.append(("base", self.base))
        return backends

    def resolve_file(self, relative: str, *, include_mods: bool = True) -> tuple[str, Path]:
        path = _safe_relative_path(relative)
        backends: list[tuple[str, Path]] = []
        if include_mods:
            backends.append(("mods", self.mods))
        backends.extend(self.content_backends())
        for name, root in backends:
            candidate = root.joinpath(*path.parts)
            if candidate.is_file():
                return name, candidate
        raise ValidationError(f"game file is absent from every backend: {path.as_posix()}")

    def source_hashes(self, relative_paths: Iterable[str]) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for relative in relative_paths:
            normalized = _safe_relative_path(relative).as_posix()
            _backend, path = self.resolve_file(normalized, include_mods=False)
            hashes[normalized] = sha256_file(path)
        return hashes

    def verify_source_hashes(self, expected: Mapping[str, str]) -> dict[str, str]:
        if not expected:
            raise ValidationError("source validation requires at least one expected hash")
        actual = self.source_hashes(expected)
        mismatches = []
        for relative, digest in expected.items():
            normalized = _safe_relative_path(relative).as_posix()
            wanted = _require_sha256(str(digest), f"source hash {normalized!r}")
            if actual[normalized] != wanted:
                mismatches.append(
                    f"{normalized}: expected {wanted}, found {actual[normalized]}"
                )
        if mismatches:
            raise ValidationError("source game hash mismatch: " + "; ".join(mismatches))
        return actual


def _candidate_game_roots(search_roots: Iterable[Path | str], max_depth: int = 4) -> set[Path]:
    candidates: set[Path] = set()
    for raw in search_roots:
        root = Path(raw).expanduser()
        if not root.exists() or not root.is_dir():
            continue
        root = root.resolve()
        if root.name.casefold() == BASE_DIR_NAME.casefold():
            candidates.add(root.parent)
        if (root / BASE_DIR_NAME).is_dir():
            candidates.add(root)
        for current, directories, _files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.relative_to(root).parts)
            if depth >= max_depth:
                directories[:] = []
                continue
            matching = next(
                (name for name in directories if name.casefold() == BASE_DIR_NAME.casefold()),
                None,
            )
            if matching is not None:
                candidates.add(current_path)
                directories.remove(matching)
    return candidates


def discover_game_install(search_roots: Iterable[Path | str]) -> GameInstall:
    valid: list[GameInstall] = []
    failures: list[str] = []
    for root in sorted(_candidate_game_roots(search_roots), key=lambda path: str(path).lower()):
        try:
            valid.append(GameInstall.from_root(root))
        except ValidationError as exc:
            failures.append(f"{root}: {exc}")
    unique = {str(install.root).casefold(): install for install in valid}
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        choices = ", ".join(str(install.root) for install in unique.values())
        raise DiscoveryError(f"multiple valid Bloodborne installations found: {choices}")
    detail = f" Candidates failed validation: {'; '.join(failures)}" if failures else ""
    raise DiscoveryError(f"no {SERIAL} {APP_VERSION} installation was found.{detail}")


def discover_shad_executable(search_roots: Iterable[Path | str], max_depth: int = 4) -> Path:
    matches: dict[str, Path] = {}
    for raw in search_roots:
        root = Path(raw).expanduser()
        if root.is_file() and root.name.casefold() == "shadps4.exe":
            resolved = root.resolve()
            matches[str(resolved).casefold()] = resolved
            continue
        if not root.is_dir():
            continue
        root = root.resolve()
        direct = root / "shadPS4.exe"
        if direct.is_file():
            matches[str(direct).casefold()] = direct
        for current, directories, files in os.walk(root):
            current_path = Path(current)
            if len(current_path.relative_to(root).parts) >= max_depth:
                directories[:] = []
                continue
            for name in files:
                if name.casefold() == "shadps4.exe":
                    found = (current_path / name).resolve()
                    matches[str(found).casefold()] = found
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        raise DiscoveryError(
            "multiple shadPS4 executables found: " + ", ".join(str(path) for path in matches.values())
        )
    raise DiscoveryError("no shadPS4.exe was found in the selected search roots")


def _user_merge_records(owner: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    section = owner.get("user_merge")
    if section is None:
        return []
    if not isinstance(section, dict):
        raise ValidationError("overlay user_merge section is not an object")
    if section.get("format") != USER_MERGE_FORMAT:
        raise ValidationError("overlay user_merge section has an unknown format")
    records = section.get("files", [])
    if not isinstance(records, list):
        raise ValidationError("overlay user_merge files is not a list")
    for record in records:
        if not isinstance(record, dict):
            raise ValidationError("overlay user_merge file record is not an object")
    return records


def user_merge_summary(owner: Mapping[str, Any]) -> tuple[int, tuple[UserModExclusion, ...]]:
    """Merged-file count and reported exclusions recorded on an active overlay."""

    section = owner.get("user_merge")
    if not isinstance(section, dict):
        return 0, ()
    exclusions = tuple(
        UserModExclusion(str(entry.get("path", "")), str(entry.get("reason", "")))
        for entry in section.get("excluded", [])
        if isinstance(entry, dict)
    )
    return len(_user_merge_records(owner)), exclusions


def dead_path_warnings(owner: Mapping[str, Any]) -> tuple[str, ...]:
    """Player-facing lines for every wrapper folder that merged nothing.

    An activation that excluded dead paths still succeeds -- nothing was going
    to load either way -- but it must never be reported as a plain success:
    that silence is the whole of bb-archipelago#173.
    """

    _, exclusions = user_merge_summary(owner)
    lines = []
    for wrapper, count in dead_path_wrappers(exclusions):
        lines.append(
            f"WARNING: {count} file(s) under {USER_MODS_DIR_NAME}/{wrapper} were "
            f"NOT merged and that mod will do nothing: their paths do not start "
            f"with {DVDROOT_PREFIX}. To fix it, {dead_path_remedy(wrapper)}."
        )
    return tuple(lines)


def _load_owner(root: Path, *, expected_key: str | None = None) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ConflictError(f"mods path is not a regular directory: {root}")
    owner_path = root / OWNER_NAME
    if not owner_path.is_file():
        raise ConflictError(
            f"{root} already exists without a Bloodborne AP ownership manifest; it was not changed"
        )
    owner = _read_json(owner_path, "overlay ownership manifest")
    if owner.get("format") != OWNER_FORMAT or owner.get("launcher") != "bloodborne-archipelago":
        raise ConflictError(f"{root} is not owned by this launcher")
    key = str(owner.get("cache_key", ""))
    _require_sha256(key, "overlay cache_key")
    if expected_key is not None and key != expected_key:
        raise ValidationError(f"active overlay key is {key}, expected {expected_key}")
    records = owner.get("files")
    if not isinstance(records, list) or not records:
        raise ValidationError("overlay ownership manifest has no files")
    expected: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValidationError("overlay ownership file record is not an object")
        relative = _safe_overlay_path(str(record.get("path", "")))
        if relative in expected:
            raise ValidationError(f"duplicate owned overlay path: {relative}")
        expected[relative] = record
    # Merged player files are owned by the same manifest, but they are outside
    # the param/map contract by definition, so they are validated as ordinary
    # game-relative paths.  An overlay written before user merging existed has
    # no such section and stays exactly as strict as it was.
    protected = {relative.casefold() for relative in expected}
    for record in _user_merge_records(owner):
        relative = _safe_relative_path(str(record.get("path", ""))).as_posix()
        if relative in expected or relative.casefold() in protected:
            raise ValidationError(f"merged user file collides with an owned path: {relative}")
        expected[relative] = record
    actual = _tree_files(root, ignore=(OWNER_NAME,))
    if set(actual) != set(expected):
        raise ConflictError(
            "managed overlay contains unowned or missing files; "
            f"missing={sorted(set(expected) - set(actual))} "
            f"unowned={sorted(set(actual) - set(expected))}"
        )
    for relative, record in expected.items():
        digest = _require_sha256(str(record.get("sha256", "")), f"owned file {relative}")
        if actual[relative].stat().st_size != record.get("size"):
            raise ValidationError(f"owned overlay file size changed: {relative}")
        if sha256_file(actual[relative]) != digest:
            raise ValidationError(f"owned overlay file hash changed: {relative}")
    return owner


def _shad_is_running() -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq shadPS4.exe", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "shadps4.exe" in result.stdout.casefold()
    proc = Path("/proc")
    if proc.is_dir():
        for command in proc.glob("[0-9]*/comm"):
            try:
                if command.read_text(encoding="utf-8").strip().casefold() == "shadps4.exe":
                    return True
            except OSError:
                pass
    return False


def _require_shad_stopped(check: Callable[[], bool] | None) -> None:
    running = (check or _shad_is_running)()
    if running:
        raise ConflictError(
            "shadPS4 is running. Close it before activating, restoring, or disabling an overlay."
        )


ELEVATED_SPAWNERS = ("bblauncher.exe", "bb-launcher.exe")


def launcher_is_elevated() -> bool:
    """False only when we positively know the launcher lacks an admin token."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 -- uncertainty must never nag the player
        return True


def _runasadmin_flagged(executable: Path) -> bool:
    """Windows AppCompat 'Run as administrator' marker for an executable."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False
    layers = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, layers) as key:
                value, _kind = winreg.QueryValueEx(key, str(executable))
        except OSError:
            continue
        if "RUNASADMIN" in str(value).upper():
            return True
    return False


def elevation_risks(
    shad_executable: Path | None, process_running: Callable[[str], bool]
) -> list[str]:
    """Reasons shadPS4 may spawn elevated while the launcher is not.

    An unelevated AP client cannot open an elevated shadPS4 process, so the
    Doctor and the launch button both surface these before the client spends
    the session polling a process it will never attach to.
    """
    reasons = [
        f"{name} is running (it starts shadPS4 elevated)"
        for name in ELEVATED_SPAWNERS
        if process_running(name)
    ]
    if shad_executable is not None and _runasadmin_flagged(shad_executable):
        reasons.append(f"{shad_executable} has the 'Run as administrator' compatibility flag")
    return reasons


# The plan entry that opens the packaged grant table (bb_launcher/plan.py).
CE_BRIDGE_PROCESS_NAME = "CE bridge"

# Cheat Engine ships under several image names; the launcher pins one of them,
# but any of them holding the .CT association produces the same handoff.
CHEAT_ENGINE_PROCESSES = (
    "cheatengine.exe",
    "cheatengine-x86_64.exe",
    "cheatengine-x86_64-SSE4-AVX2.exe",
    "cheatengine-i386.exe",
)


def process_is_running_by_name(name: str) -> bool:
    """Is a process with this image name running? The one process probe.

    Windows uses tasklist; elsewhere (and in CI) it reads /proc, so callers
    stay testable on Linux. Every caller can inject a replacement.
    """

    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return name.casefold() in result.stdout.casefold()
    proc = Path("/proc")
    if proc.is_dir():
        for command in proc.glob("[0-9]*/comm"):
            try:
                if command.read_text(encoding="utf-8").strip().casefold() == name.casefold():
                    return True
            except OSError:
                pass
    return False


def stray_cheat_engine_names(
    process_running: Callable[[str], bool] | None = None
) -> list[str]:
    """Cheat Engine image names already running before we spawn the bridge."""

    check = process_running or process_is_running_by_name
    return [name for name in CHEAT_ENGINE_PROCESSES if check(name)]


def stray_cheat_engine_refusal(names: Sequence[str]) -> str:
    """The player-facing refusal, remedy first. ASCII only for any console."""

    listed = ", ".join(names)
    elevation = (
        "this launcher is running as administrator"
        if launcher_is_elevated()
        else "this launcher is NOT running as administrator, so an already-open "
        "Cheat Engine may also hold the wrong privilege token"
    )
    return (
        f"Cheat Engine is already running ({listed}). Close Cheat Engine and press "
        "Launch again. Windows hands the grant table to the instance that is "
        "already open instead of the one this launch pins, and that instance does "
        "not arm the grant bridge: your checks would still reach the server, but "
        f"no items could be delivered into your game. ({elevation}.)"
    )


def require_no_stray_cheat_engine(
    processes: Sequence["ProcessSpec"],
    process_running: Callable[[str], bool] | None = None,
) -> None:
    """Fail closed rather than launch a CE bridge that cannot arm (#137).

    Only a plan that actually spawns the bridge is affected; a plan with no CE
    bridge entry has nothing to hand off and is left alone.
    """

    if not any(spec.name == CE_BRIDGE_PROCESS_NAME for spec in processes):
        return
    names = stray_cheat_engine_names(process_running)
    if not names:
        return
    raise ConflictError(stray_cheat_engine_refusal(names))


def _transaction_path(install: GameInstall) -> Path:
    return install.root / TRANSACTION_NAME


def _transaction_child(install: GameInstall, raw: Any, label: str) -> Path | None:
    if raw is None:
        return None
    name = str(raw)
    if not name or Path(name).name != name or name in (".", ".."):
        raise RecoveryError(f"transaction {label} is not a safe sibling name")
    return install.root / name


def _set_phase(path: Path, journal: dict[str, Any], phase: str) -> None:
    journal["phase"] = phase
    _write_json_atomic(path, journal)


def _stage_overlay(
    install: GameInstall,
    build: BuildResult,
    stage: Path,
    previous_cache_key: str | None,
    user_sources: Mapping[str, Path] | None = None,
    merge: UserModMerge | None = None,
) -> dict[str, Any]:
    stage.mkdir()
    for record in build.manifest["files"]:
        relative = _safe_overlay_path(str(record["path"]))
        source = build.path.joinpath(*PurePosixPath(relative).parts)
        destination = stage.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256_file(destination) != record["sha256"]:
            raise ValidationError(f"staged activation copy failed verification: {relative}")
    user_records: list[dict[str, Any]] = []
    if merge is not None and merge.merged:
        sources = user_sources or {}
        # Copied after the generated files and never over one of them: the
        # merge plan already excluded every Archipelago-owned path.
        for relative, digest in sorted(merge.merged.items()):
            source = sources[relative]
            destination = stage.joinpath(*PurePosixPath(relative).parts)
            if destination.exists():
                raise ValidationError(f"user mod file would overwrite an owned path: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if sha256_file(destination) != digest:
                raise ValidationError(f"staged user mod copy failed verification: {relative}")
            user_records.append(
                {"path": relative, "size": destination.stat().st_size, "sha256": digest}
            )
    owner = {
        "format": OWNER_FORMAT,
        "launcher": "bloodborne-archipelago",
        "serial": SERIAL,
        "app_version": APP_VERSION,
        "cache_key": build.cache_key,
        "previous_cache_key": previous_cache_key,
        "identity": build.manifest["identity"],
        "build_manifest_sha256": sha256_file(build.path / SEED_MANIFEST_NAME),
        "files": build.manifest["files"],
        "suppression": build.manifest["suppression"],
        "enemizer": build.manifest["enemizer"],
        "user_merge": {
            "format": USER_MERGE_FORMAT,
            "source": USER_MODS_DIR_NAME,
            "fingerprint": (merge or UserModMerge({}, ())).fingerprint,
            "files": user_records,
            "excluded": [
                exclusion.as_dict() for exclusion in (merge.excluded if merge else ())
            ],
        },
    }
    _write_json_atomic(stage / OWNER_NAME, owner)
    _load_owner(stage, expected_key=build.cache_key)
    return owner


def plan_activation_merge(
    install: GameInstall, build: "BuildResult"
) -> tuple[dict[str, Path], UserModMerge]:
    """Read the player's mods directory and decide the merge for this build."""

    sources = collect_user_mod_files(install.user_mods)
    hashes = {relative: sha256_file(path) for relative, path in sources.items()}
    owned = [_safe_overlay_path(str(record["path"])) for record in build.manifest["files"]]
    merge = plan_user_merge(hashes, owned)
    return {relative: sources[relative] for relative in merge.merged}, merge


def activate_build(
    install: GameInstall,
    build_path: Path | str,
    *,
    process_is_running: Callable[[], bool] | None = None,
    failpoint: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Atomically activate a verified build, preserving any owned predecessor."""

    _require_shad_stopped(process_is_running)
    recover_activation(install, process_is_running=process_is_running)
    build = SeedCache(Path(build_path).resolve().parent).verify(build_path)
    user_sources, merge = plan_activation_merge(install, build)
    previous_owner = None
    if install.mods.exists():
        previous_owner = _load_owner(install.mods)
        active_fingerprint = ""
        section = previous_owner.get("user_merge")
        if isinstance(section, dict):
            active_fingerprint = str(section.get("fingerprint", ""))
        elif not merge.merged and not merge.excluded:
            # Pre-merge overlay with nothing to merge: unchanged by definition.
            active_fingerprint = merge.fingerprint
        # A changed user mods directory changes the overlay even when the seed
        # build is identical, so it must run a full transaction, not short out.
        if (
            previous_owner["cache_key"] == build.cache_key
            and active_fingerprint == merge.fingerprint
        ):
            return previous_owner
    transaction_id = uuid.uuid4().hex
    stage = install.root / f".{MODS_DIR_NAME}.bb-ap-stage-{transaction_id}"
    backup = (
        install.root / f".{MODS_DIR_NAME}.bb-ap-previous-{transaction_id}"
        if previous_owner is not None
        else None
    )
    if stage.exists() or (backup is not None and backup.exists()):
        raise ConflictError("launcher transaction sibling already exists")
    try:
        owner = _stage_overlay(
            install,
            build,
            stage,
            None if previous_owner is None else str(previous_owner["cache_key"]),
            user_sources,
            merge,
        )
    except Exception:
        if stage.exists():
            failed = install.root / f".{MODS_DIR_NAME}.bb-ap-failed-{transaction_id}"
            os.replace(stage, failed)
        raise
    journal = {
        "format": TRANSACTION_FORMAT,
        "mode": "activate",
        "id": transaction_id,
        "phase": "staged",
        "target": MODS_DIR_NAME,
        "stage": stage.name,
        "backup": None if backup is None else backup.name,
        "new_cache_key": build.cache_key,
        "previous_cache_key": (
            None if previous_owner is None else str(previous_owner["cache_key"])
        ),
    }
    transaction = _transaction_path(install)
    _write_json_atomic(transaction, journal)
    if failpoint is not None:
        failpoint("staged")
    if backup is not None:
        os.replace(install.mods, backup)
    _set_phase(transaction, journal, "previous_moved")
    if failpoint is not None:
        failpoint("previous_moved")
    os.replace(stage, install.mods)
    _set_phase(transaction, journal, "activated")
    if failpoint is not None:
        failpoint("activated")
    _load_owner(install.mods, expected_key=build.cache_key)
    _set_phase(transaction, journal, "completed")
    return owner


def _preserve_failed(path: Path, install: GameInstall, transaction_id: str) -> Path:
    destination = install.root / f".{MODS_DIR_NAME}.bb-ap-failed-{transaction_id}-{uuid.uuid4().hex}"
    os.replace(path, destination)
    return destination


def _rollback_activation(
    install: GameInstall,
    journal: dict[str, Any],
    stage: Path | None,
    backup: Path | None,
) -> None:
    transaction = _transaction_path(install)
    transaction_id = str(journal.get("id", "unknown"))
    phase = str(journal.get("phase", ""))
    previous_key = journal.get("previous_cache_key")
    if install.mods.exists():
        if phase == "staged" and previous_key is not None:
            # The previous overlay has not moved yet.  Verify and leave it in
            # place; rollback must not turn a healthy active seed into vanilla.
            _load_owner(install.mods, expected_key=str(previous_key))
        elif phase == "staged" and previous_key is None:
            # Something outside the transaction appeared at the target.  It is
            # not ours to rename merely to make rollback convenient.
            raise RecoveryError(
                "an unexpected mods directory appeared before activation; it was not changed"
            )
        else:
            # Only preserve a directory that still proves launcher ownership.
            # Arbitrary user content is never renamed during recovery.
            _load_owner(install.mods)
            _preserve_failed(install.mods, install, transaction_id)
    if backup is not None and backup.exists():
        if previous_key is not None:
            _load_owner(backup, expected_key=str(previous_key))
        if not install.mods.exists():
            os.replace(backup, install.mods)
    if stage is not None and stage.exists():
        _preserve_failed(stage, install, transaction_id)
    _set_phase(transaction, journal, "rolled_back")


def recover_activation(
    install: GameInstall,
    *,
    process_is_running: Callable[[], bool] | None = None,
) -> str:
    """Finish or roll back the one durable activation transaction."""

    transaction = _transaction_path(install)
    if not transaction.exists():
        return "none"
    _require_shad_stopped(process_is_running)
    journal = _read_json(transaction, "activation transaction")
    if journal.get("format") != TRANSACTION_FORMAT:
        raise RecoveryError(f"unsupported transaction format in {transaction}")
    phase = str(journal.get("phase", ""))
    if phase in ("completed", "rolled_back"):
        return phase
    mode = journal.get("mode")
    if mode == "deactivate":
        disabled = _transaction_child(install, journal.get("disabled"), "disabled")
        if disabled is None:
            raise RecoveryError("deactivation transaction has no disabled path")
        if install.mods.exists() and disabled.exists():
            raise RecoveryError("both active and disabled overlays exist after interrupted deactivation")
        if install.mods.exists():
            _load_owner(install.mods, expected_key=str(journal["cache_key"]))
            os.replace(install.mods, disabled)
        elif not disabled.exists():
            raise RecoveryError("interrupted deactivation lost both overlay names")
        _load_owner(disabled, expected_key=str(journal["cache_key"]))
        _set_phase(transaction, journal, "completed")
        return "completed"
    if mode != "activate":
        raise RecoveryError(f"unknown transaction mode: {mode!r}")
    stage = _transaction_child(install, journal.get("stage"), "stage")
    backup = _transaction_child(install, journal.get("backup"), "backup")
    new_key = str(journal.get("new_cache_key", ""))
    _require_sha256(new_key, "transaction new_cache_key")
    try:
        if phase == "staged":
            if stage is None or not stage.exists():
                raise RecoveryError("staged transaction is missing its verified staging directory")
            _load_owner(stage, expected_key=new_key)
            if journal.get("previous_cache_key") is not None:
                if not install.mods.exists() or backup is None:
                    raise RecoveryError("staged transaction lost its previous overlay")
                _load_owner(install.mods, expected_key=str(journal["previous_cache_key"]))
                os.replace(install.mods, backup)
            elif install.mods.exists():
                raise ConflictError("an unexpected mods directory appeared during recovery")
            _set_phase(transaction, journal, "previous_moved")
            phase = "previous_moved"
        if phase == "previous_moved":
            if install.mods.exists():
                raise RecoveryError("target unexpectedly exists before staged activation")
            if stage is None or not stage.exists():
                raise RecoveryError("transaction is missing its staged overlay")
            _load_owner(stage, expected_key=new_key)
            os.replace(stage, install.mods)
            _set_phase(transaction, journal, "activated")
            phase = "activated"
        if phase == "activated":
            if not install.mods.exists():
                raise RecoveryError("activated transaction is missing the target overlay")
            _load_owner(install.mods, expected_key=new_key)
            _set_phase(transaction, journal, "completed")
            return "completed"
        raise RecoveryError(f"unknown activation phase: {phase!r}")
    except (ConflictError, RecoveryError, ValidationError) as exc:
        try:
            _rollback_activation(install, journal, stage, backup)
        except LauncherError as rollback_exc:
            raise RecoveryError(
                f"transaction recovery failed ({exc}); rollback also failed ({rollback_exc})"
            ) from rollback_exc
        raise RecoveryError(f"transaction was rolled back after recovery failed: {exc}") from exc


def deactivate_overlay(
    install: GameInstall,
    *,
    process_is_running: Callable[[], bool] | None = None,
) -> Path | None:
    """Remove only a verified launcher-owned overlay from shad's search path."""

    _require_shad_stopped(process_is_running)
    recover_activation(install, process_is_running=process_is_running)
    if not install.mods.exists():
        return None
    owner = _load_owner(install.mods)
    transaction_id = uuid.uuid4().hex
    disabled = install.root / f".{MODS_DIR_NAME}.bb-ap-disabled-{transaction_id}"
    journal = {
        "format": TRANSACTION_FORMAT,
        "mode": "deactivate",
        "id": transaction_id,
        "phase": "prepared",
        "target": MODS_DIR_NAME,
        "disabled": disabled.name,
        "cache_key": owner["cache_key"],
    }
    transaction = _transaction_path(install)
    _write_json_atomic(transaction, journal)
    os.replace(install.mods, disabled)
    _load_owner(disabled, expected_key=str(owner["cache_key"]))
    _set_phase(transaction, journal, "completed")
    return disabled


def restore_previous_build(
    install: GameInstall,
    cache: SeedCache,
    *,
    process_is_running: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Reactivate the previous seed from its independently verified cache."""

    _require_shad_stopped(process_is_running)
    recover_activation(install, process_is_running=process_is_running)
    if not install.mods.exists():
        raise ValidationError("there is no active launcher overlay to restore from")
    owner = _load_owner(install.mods)
    previous = owner.get("previous_cache_key")
    if previous is None:
        raise ValidationError("the active overlay has no previous seed build")
    previous_path = cache.path_for(str(previous))
    cache.verify(previous_path, expected_key=str(previous))
    return activate_build(
        install,
        previous_path,
        process_is_running=process_is_running,
    )


SESSION_HEADER_PREFIX = "=== SESSION START"
# Enough of the tail to carry a startup refusal and its context, bounded so a
# long-running client's log can never fill a dialog.
LOG_TAIL_BYTES = 4000


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    executable: Path
    arguments: Sequence[str] = ()
    working_directory: Path | None = None
    expected_sha256: str | None = None
    # When set, this process's stdout and stderr are appended to the file so a
    # startup refusal survives the console window closing (bb-archipelago#171).
    log_path: Path | None = None


@dataclass(frozen=True)
class EarlyExit:
    """A launched component that stopped before the watch window ended."""

    name: str
    returncode: int | None
    log_path: Path | None
    log_tail: str

    def describe(self) -> str:
        code = "an unknown exit code" if self.returncode is None else f"exit code {self.returncode}"
        lines = [f"{self.name} exited with {code} immediately after launch."]
        if self.log_tail:
            lines.append("")
            lines.append(self.log_tail)
        if self.log_path is not None:
            lines.append("")
            lines.append(f"Full log: {self.log_path}")
        return "\n".join(lines)


def _open_process_log(path: Path) -> Any:
    """Open a per-process log for append and stamp this session's header."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "ab")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    handle.write(f"\n{SESSION_HEADER_PREFIX} {stamp} ===\n".encode("utf-8"))
    handle.flush()
    return handle


# Attribute under which a launched child carries the daemon thread that tees its
# output.  ``wait_for_early_exit`` joins it before reading the tail so the file
# is complete even when the child dies immediately (bb-archipelago#179).
_OUTPUT_PUMP_ATTR = "_bb_output_pump"


def _pump_output(source: Any, log_handle: Any, console: TextIO | None) -> None:
    """Tee each line the child writes to BOTH the console and the log file.

    Windows ``Popen`` cannot tee natively, so the launcher owns the split: the
    child speaks over a pipe, and this pump duplicates every line onto the live
    console window (so the player sees the client#422 banner and diagnostics)
    and onto ``log_handle`` (so a startup refusal survives the window closing,
    preserving bb-archipelago#171).  The pump owns ``log_handle`` and closes it
    when the pipe reaches EOF, so the tail-reader opens its own handle only
    after the pump has flushed and released the file.
    """

    try:
        for line in source:
            data = line if isinstance(line, bytes) else line.encode("utf-8", "replace")
            try:
                log_handle.write(data)
                log_handle.flush()
            except (OSError, ValueError):
                pass
            if console is not None:
                text = line if isinstance(line, str) else line.decode("utf-8", "replace")
                try:
                    console.write(text)
                    console.flush()
                except (OSError, ValueError):
                    pass
    finally:
        try:
            source.close()
        except Exception:
            pass
        try:
            log_handle.close()
        except Exception:
            pass


def _start_output_pump(child: Any, log_handle: Any, console: TextIO | None) -> Any:
    """Spawn a daemon pump for ``child`` and record it for later joining."""

    source = getattr(child, "stdout", None)
    if source is None:
        # Nothing to read (e.g. an injected fake process with no pipe): the
        # caller still owns the log handle, so close it rather than leak it.
        log_handle.close()
        return None
    thread = threading.Thread(
        target=_pump_output,
        args=(source, log_handle, console),
        name="bb-launcher-output-pump",
        daemon=True,
    )
    setattr(child, _OUTPUT_PUMP_ATTR, thread)
    thread.start()
    return thread


def _join_output_pump(child: Any, *, timeout: float = 5.0) -> None:
    """Drain a child's pump so its log file is complete before the tail read."""

    thread = getattr(child, _OUTPUT_PUMP_ATTR, None)
    if thread is not None:
        thread.join(timeout)


def read_session_log_tail(path: Path | None, *, limit: int = LOG_TAIL_BYTES) -> str:
    """Return this session's output from a process log, bounded to `limit`."""

    if path is None:
        return ""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    marker = text.rfind(SESSION_HEADER_PREFIX)
    if marker != -1:
        newline = text.find("\n", marker)
        text = text[newline + 1 :] if newline != -1 else ""
    text = text.strip()
    if len(text) > limit:
        text = "..." + text[-limit:]
    return text


def wait_for_early_exit(
    started: Sequence[Any],
    processes: Sequence[ProcessSpec],
    *,
    timeout: float = 10.0,
    interval: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> EarlyExit | None:
    """Watch freshly launched children briefly and report the first casualty.

    A component that refuses at startup writes its reason and dies; its console
    dies with it.  Polling for the watch window turns that silence into a
    reportable exit code plus the tail of the log the process just wrote.
    """

    watchable = [
        (index, process)
        for index, process in enumerate(started)
        if callable(getattr(process, "poll", None))
    ]
    if not watchable:
        # Nothing exposes an exit status: there is no observation to wait for,
        # and waiting anyway would only stall the launch.
        return None
    deadline = monotonic() + max(timeout, 0.0)
    while True:
        for index, process in watchable:
            code = process.poll()
            if code is None:
                continue
            spec = processes[index] if index < len(processes) else None
            name = spec.name if spec is not None else f"process {index + 1}"
            log_path = spec.log_path if spec is not None else None
            # Drain the tee so everything the child wrote before dying has been
            # flushed to the file and the handle released before we read it.
            _join_output_pump(process)
            return EarlyExit(name, code, log_path, read_session_log_tail(log_path))
        if monotonic() >= deadline:
            return None
        sleep(interval)


def launch_processes(
    processes: Sequence[ProcessSpec],
    *,
    popen: Callable[..., Any] = subprocess.Popen,
    console: TextIO | None = None,
) -> list[Any]:
    """Start configured components as siblings inheriting one privilege token.

    When a component sets ``log_path`` its output is *teed* rather than
    redirected: the child speaks over a pipe and a daemon pump duplicates every
    line onto ``console`` (the live window; ``sys.stdout`` by default) and into
    the session log.  The player still sees live output while the file keeps the
    evidence a startup refusal needs after the window closes
    (bb-archipelago#179, preserving #171).  With no ``log_path`` the child
    inherits the console exactly as before -- no pipe, no pump, no file.
    """

    if console is None:
        console = sys.stdout
    validated = validate_processes(processes)
    started: list[Any] = []
    for spec in validated:
        command = [str(spec.executable), *[str(argument) for argument in spec.arguments]]
        log_handle = None
        try:
            extra: dict[str, Any] = {}
            if spec.log_path is not None:
                log_handle = _open_process_log(spec.log_path)
                # A pipe (not the file) so the pump can tee; line-buffered text
                # so each line is teed as the child emits it.
                extra = {
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                    "bufsize": 1,
                }
            child = popen(
                command,
                cwd=(str(spec.working_directory) if spec.working_directory else None),
                **extra,
            )
        except OSError as exc:
            if log_handle is not None:
                log_handle.close()
            running = ", ".join(item.name for item in validated[:len(started)]) or "none"
            raise LaunchError(
                f"could not start {spec.name}: {exc}. Already started: {running}"
            ) from exc
        if log_handle is not None:
            # Ownership of the log handle passes to the pump, which closes it at
            # EOF; nothing else may close it here.
            _start_output_pump(child, log_handle, console)
        started.append(child)
    return started


STALE_BARE_SERIAL_REMEDY = (
    "regenerate the launch plan (Generate Launch Plan, or python -m bb_launcher "
    "plan): plans pinned before bb-archipelago#177 invoke shadPS4 with the bare "
    f"{SERIAL} game ID, which shadPS4 can only resolve against its OWN library "
    "config -- empty on a fresh emulator copy, which is why it exits with "
    f"\"Game ID or file path not found: {SERIAL}\". A regenerated plan passes "
    "the game folder by path instead, so no in-emulator setup is needed"
)


def stale_bare_serial_process(processes: Sequence[ProcessSpec]) -> ProcessSpec | None:
    """Find a plan entry that still launches the game by bare game ID.

    Deliberately narrow: only the exact argument the pre-#177 generator emitted
    counts. A host who hand-authored an absolute path, or who passes the serial
    embedded in some other argument, is left alone -- this detects the shape the
    launcher itself used to write, so it can tell the player to regenerate.
    """

    for spec in processes:
        if any(argument == SERIAL for argument in spec.arguments):
            return spec
    return None


def validate_processes(processes: Sequence[ProcessSpec]) -> list[ProcessSpec]:
    """Preflight a complete launch plan without starting any component."""

    if not processes:
        raise LaunchError("launch plan contains no processes")
    validated: list[ProcessSpec] = []
    for spec in processes:
        executable = Path(spec.executable).expanduser().resolve()
        if not executable.is_file() or executable.is_symlink():
            raise LaunchError(f"{spec.name} executable does not exist: {executable}")
        expected_hash = None
        if spec.expected_sha256 is not None:
            expected_hash = _require_sha256(
                spec.expected_sha256, f"{spec.name} executable hash"
            )
            actual_hash = sha256_file(executable)
            if actual_hash != expected_hash:
                raise LaunchError(
                    f"{spec.name} executable hash mismatch: expected {expected_hash}, "
                    f"found {actual_hash}"
                )
        working = None
        if spec.working_directory is not None:
            working = Path(spec.working_directory).expanduser().resolve()
            if not working.is_dir():
                raise LaunchError(f"{spec.name} working directory does not exist: {working}")
        log_path = None
        if spec.log_path is not None:
            log_path = Path(spec.log_path).expanduser()
        validated.append(
            ProcessSpec(
                spec.name,
                executable,
                tuple(spec.arguments),
                working,
                expected_hash,
                log_path,
            )
        )
    return validated
