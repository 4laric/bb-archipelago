"""Safe seed caching, shadPS4 overlay activation, and process launch.

Only launcher-owned files may enter ``CUSA03173-mods``.  Base and update trees
are read-only inputs and never appear as mutation targets in this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence


SERIAL = "CUSA03173"
APP_VERSION = "01.09"
BASE_DIR_NAME = SERIAL
PATCH_DIR_NAMES = (f"{SERIAL}-patch", f"{SERIAL}-UPDATE")
MODS_DIR_NAME = f"{SERIAL}-mods"
SEED_MANIFEST_NAME = "seed-manifest.json"
SEED_MANIFEST_FORMAT = "bb-launcher-seed-build-v1"
OWNER_NAME = ".bb-ap-owner.json"
OWNER_FORMAT = "bb-launcher-overlay-owner-v1"
TRANSACTION_NAME = ".bb-ap-launcher-transaction.json"
TRANSACTION_FORMAT = "bb-launcher-activation-transaction-v1"
SUPPRESSION_PATH = "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"
MAP_PREFIX = "dvdroot_ps4/map/MapStudio/"


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


@dataclass(frozen=True)
class GameInstall:
    root: Path
    base: Path
    patch: Path
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
            raise ValidationError(f"missing base game directory: {base}")
        if len(patches) != 1:
            raise ValidationError(
                f"expected exactly one CUSA03173 01.09 update directory, found {len(patches)}"
            )
        if base.is_symlink() or patches[0].is_symlink():
            raise ValidationError("base and update directories may not be symbolic links")
        base_sfo = read_param_sfo(base / "sce_sys" / "param.sfo")
        patch_sfo = read_param_sfo(patches[0] / "sce_sys" / "param.sfo")
        serial = patch_sfo.get("TITLE_ID", base_sfo.get("TITLE_ID"))
        version = patch_sfo.get("APP_VER")
        if serial != SERIAL:
            raise ValidationError(f"expected serial {SERIAL}, installation reports {serial!r}")
        if version != APP_VERSION:
            raise ValidationError(
                f"expected {SERIAL} AppVer {APP_VERSION}, update reports {version!r}"
            )
        return cls(candidate, base, patches[0], candidate / MODS_DIR_NAME)

    def resolve_file(self, relative: str, *, include_mods: bool = True) -> tuple[str, Path]:
        path = _safe_relative_path(relative)
        backends: list[tuple[str, Path]] = []
        if include_mods:
            backends.append(("mods", self.mods))
        backends.extend((("patch", self.patch), ("base", self.base)))
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
    }
    _write_json_atomic(stage / OWNER_NAME, owner)
    _load_owner(stage, expected_key=build.cache_key)
    return owner


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
    previous_owner = None
    if install.mods.exists():
        previous_owner = _load_owner(install.mods)
        if previous_owner["cache_key"] == build.cache_key:
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


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    executable: Path
    arguments: Sequence[str] = ()
    working_directory: Path | None = None
    expected_sha256: str | None = None


def launch_processes(
    processes: Sequence[ProcessSpec],
    *,
    popen: Callable[..., Any] = subprocess.Popen,
) -> list[Any]:
    """Start configured components as siblings inheriting one privilege token."""

    validated = validate_processes(processes)
    started: list[Any] = []
    for spec in validated:
        command = [str(spec.executable), *[str(argument) for argument in spec.arguments]]
        try:
            started.append(
                popen(
                    command,
                    cwd=(str(spec.working_directory) if spec.working_directory else None),
                )
            )
        except OSError as exc:
            running = ", ".join(item.name for item in validated[:len(started)]) or "none"
            raise LaunchError(
                f"could not start {spec.name}: {exc}. Already started: {running}"
            ) from exc
    return started


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
        validated.append(
            ProcessSpec(spec.name, executable, tuple(spec.arguments), working, expected_hash)
        )
    return validated
