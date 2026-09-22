"""Immutable BBLauncher exports and read-only external activation proof.

BBLauncher owns both the active-package directory and the game's ``*-mods``
overlay in this mode.  This module writes only a new inactive package and an
out-of-band receipt.  Verification never creates the standalone launcher's
owner file and never adopts or repairs BBLauncher state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .client_config import session_key
from .core import (
    APP_VERSION,
    DVDROOT_PREFIX,
    SEED_MANIFEST_NAME,
    SERIAL,
    SUPPRESSION_PATH,
    BuildResult,
    GameInstall,
    SeedCache,
    SeedIdentity,
    ValidationError,
    _require_sha256,
    _safe_overlay_path,
    canonical_json,
    sha256_file,
)
from .version import launcher_version


EXTERNAL_RECEIPT_FORMAT = "bb-launcher-external-export-v1"
ACTIVE_MODS_DIR_NAME = "Mods-Active (DO NOT DELETE)"
PACKAGE_PREFIX = "Archipelago-"


class ExternalPackageExists(ValidationError):
    """The inactive Mods library already holds this exact package.

    The package name is derived from the slot and the verified cache key, so
    rebuilding the same seed with the same options lands on the same name.
    The UI catches this to offer a replacement instead of a dead end; the
    active package directory never takes this path.
    """

    def __init__(self, path: Path):
        super().__init__(
            f"a prepared mod for this seed already exists in BBLauncher's Mods "
            f"library: {path}"
        )
        self.path = path

# Support remains deliberately empty until a complete Windows live-acceptance
# run has passed.  The source-reviewed local binary below may be used only when
# both the pin and the call explicitly mark it as a live-acceptance candidate.
SUPPORTED_BBLAUNCHER_BUILDS: frozenset[tuple[str, str]] = frozenset()
LIVE_ACCEPTANCE_CANDIDATES = MappingProxyType({
    "f092023f6cdf36a83ce735f7124b7835e9cf03b0": frozenset({
        # Release 16.10 UAC and no-UAC Windows binaries.  They share source
        # paths but exercise BBLauncher's symlink and copy routes respectively.
        "a990d5507f22d8b0590d8b9426519c98de6fe86042a61a32e679e4a1a66b2d0a",
        "2cfa43cf05a16e0c0ebaf87275d295961afff32c91ea57962e83c474358881f0",
    }),
})


@dataclass(frozen=True)
class BBLauncherBuildPin:
    build: str
    commit: str
    executable_sha256: str
    live_acceptance_candidate: bool = False

    def normalized(self) -> "BBLauncherBuildPin":
        build = self.build.strip()
        commit = self.commit.strip().lower()
        if not build:
            raise ValidationError("BBLauncher build pin requires a build name")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValidationError("BBLauncher build pin requires a full lowercase commit")
        digest = _require_sha256(self.executable_sha256.lower(), "BBLauncher executable")
        return BBLauncherBuildPin(build, commit, digest, self.live_acceptance_candidate)


@dataclass(frozen=True)
class ExternalNamespace:
    """Logical references to the existing cache and durable client ledger."""

    cache_key: str
    ledger_key: str

    @classmethod
    def for_identity(cls, identity: SeedIdentity) -> "ExternalNamespace":
        return cls(identity.cache_key, session_key(identity.seed, identity.slot))

    def normalized(self) -> "ExternalNamespace":
        cache = _require_sha256(self.cache_key.lower(), "external cache namespace")
        ledger = _require_sha256(self.ledger_key.lower(), "external ledger namespace")
        return ExternalNamespace(cache, ledger)


@dataclass(frozen=True)
class ExternalFile:
    path: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True)
class ExternalReceipt:
    receipt_id: str
    created_at: str
    package_name: str
    cache_key: str
    identity: SeedIdentity
    namespace: ExternalNamespace
    files: tuple[ExternalFile, ...]
    game_root: Path
    game_serial: str
    app_version: str
    bblauncher: BBLauncherBuildPin
    compatibility: str
    client_version: str
    companion_version: str
    build_manifest_sha256: str
    suppression_manifest_sha256: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": EXTERNAL_RECEIPT_FORMAT,
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "package_name": self.package_name,
            "cache_key": self.cache_key,
            "identity": self.identity.as_dict(),
            "versions": {
                "world": self.identity.world_build,
                "runtime": self.identity.runtime_build,
                "client": self.client_version,
                "companion": self.companion_version,
            },
            "game": {
                "serial": self.game_serial,
                "app_version": self.app_version,
                "root": str(self.game_root),
            },
            "bblauncher": {
                "build": self.bblauncher.build,
                "commit": self.bblauncher.commit,
                "executable_sha256": self.bblauncher.executable_sha256,
                "compatibility": self.compatibility,
            },
            "namespace": {
                "cache_key": self.namespace.cache_key,
                "ledger_key": self.namespace.ledger_key,
            },
            "source_hashes": dict(sorted(self.identity.source_hashes.items())),
            "suppression": {
                "plan_sha256": self.identity.suppression_plan_sha256,
                "binder_sha256": self.identity.suppression_binder_sha256,
                "manifest_sha256": self.suppression_manifest_sha256,
            },
            "seed_options": dict(self.identity.options),
            "enemizer_identity": self.identity.enemizer_seed,
            "files": [record.as_dict() for record in self.files],
            "build_manifest_sha256": self.build_manifest_sha256,
        }


@dataclass(frozen=True)
class ExternalExport:
    package_path: Path
    receipt_path: Path
    receipt: ExternalReceipt


@dataclass(frozen=True)
class VerifiedExternalFile:
    path: str
    installed_path: Path
    active_source: Path
    sha256: str
    installation: str


@dataclass(frozen=True)
class VerifiedExternalActivation:
    receipt: ExternalReceipt
    active_root: Path
    active_package: Path
    overlay_root: Path
    files: tuple[VerifiedExternalFile, ...]
    installed_gameparam: Path
    observed_at: str
    activation_fingerprint: str

    @property
    def identity(self) -> SeedIdentity:
        return self.receipt.identity

    @property
    def exported_files(self) -> tuple[ExternalFile, ...]:
        return self.receipt.files

    @property
    def effective_files(self) -> Mapping[str, Path]:
        return MappingProxyType({record.path: record.installed_path for record in self.files})


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
            raise ValidationError(f"{label} crosses a symbolic link or reparse point: {part}")


def _regular_directory(path: Path | str, label: str) -> Path:
    candidate = _absolute(path)
    _check_existing_ancestors(candidate, label)
    if not candidate.is_dir() or _is_reparse(candidate):
        raise ValidationError(f"{label} is not a regular directory: {candidate}")
    return candidate


def _overlap(left: Path, right: Path) -> bool:
    try:
        common = os.path.commonpath((os.path.normcase(str(left)), os.path.normcase(str(right))))
    except ValueError:
        return False
    return common in {os.path.normcase(str(left)), os.path.normcase(str(right))}


def _inside_named_directory(path: Path, name: str) -> bool:
    wanted = name.casefold()
    return any(part.casefold() == wanted for part in path.parts)


def _require_outside_bblauncher(path: Path, label: str, managed_root: Path) -> None:
    if _overlap(path, managed_root):
        raise ValidationError(
            f"{label} must stay outside the BBLauncher managed root: "
            f"{path} and {managed_root}"
        )


def _require_separate(write_root: Path, protected: Iterable[tuple[str, Path]]) -> None:
    for label, path in protected:
        candidate = _absolute(path)
        if _overlap(write_root, candidate):
            raise ValidationError(f"external write root overlaps {label}: {write_root} and {candidate}")


def _compatibility(pin: BBLauncherBuildPin, *, allow_live_acceptance_candidate: bool) -> str:
    normalized = pin.normalized()
    if (normalized.commit, normalized.executable_sha256) in SUPPORTED_BBLAUNCHER_BUILDS:
        return "supported"
    candidate_hashes = LIVE_ACCEPTANCE_CANDIDATES.get(normalized.commit, frozenset())
    if (allow_live_acceptance_candidate and normalized.live_acceptance_candidate
            and normalized.executable_sha256 in candidate_hashes):
        return "live-acceptance-candidate"
    raise ValidationError(
        "BBLauncher build is not supported; a source-reviewed development build must be "
        "explicitly marked and allowed as a live-acceptance candidate"
    )


def _safe_slot(slot: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", slot.strip()).strip(" .-_")
    if not value:
        value = "Hunter"
    return value[:48]


def _refuse_casefold_child(directory: Path, name: str, label: str) -> None:
    try:
        matches = [entry for entry in directory.iterdir() if entry.name.casefold() == name.casefold()]
    except OSError as exc:
        raise ValidationError(f"could not inspect {label} {directory}: {exc}") from exc
    if matches:
        raise ValidationError(
            f"immutable external target already exists in {label}: {matches[0].name}"
        )


def _replaceable_package(mods: Path, package_name: str, *, replace: bool) -> Path | None:
    """The existing inactive package this export may replace, or None.

    Without ``replace`` any name collision is the typed refusal.  With it, the
    collision must be exactly one regular directory that this companion could
    have written (its own prefix, no reparse point); anything else stays a
    refusal, so a player can never be talked into deleting a foreign mod.
    """
    try:
        matches = [
            entry for entry in mods.iterdir()
            if entry.name.casefold() == package_name.casefold()
        ]
    except OSError as exc:
        raise ValidationError(f"could not inspect BBLauncher Mods directory {mods}: {exc}") from exc
    if not matches:
        return None
    if not replace:
        raise ExternalPackageExists(matches[0])
    if len(matches) != 1:
        raise ValidationError(
            f"more than one entry named like {package_name} in BBLauncher Mods directory"
        )
    existing = matches[0]
    if (
        not existing.name.startswith(PACKAGE_PREFIX)
        or not existing.is_dir()
        or _is_reparse(existing)
    ):
        raise ValidationError(
            f"existing entry in BBLauncher Mods directory is not a replaceable companion "
            f"package: {existing.name}"
        )
    return existing


def _manifest_files(build: BuildResult) -> tuple[ExternalFile, ...]:
    records = build.manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValidationError("verified seed build carries no output files")
    found: dict[str, ExternalFile] = {}
    folded: dict[str, str] = {}
    for raw in records:
        if not isinstance(raw, dict):
            raise ValidationError("seed build file record is not an object")
        relative = _safe_overlay_path(str(raw.get("path", "")))
        prior = folded.get(relative.casefold())
        if prior is not None:
            raise ValidationError(f"case-insensitive duplicate seed output: {prior}, {relative}")
        size = raw.get("size")
        if not isinstance(size, int) or size < 0:
            raise ValidationError(f"seed output has invalid size: {relative}")
        digest = _require_sha256(str(raw.get("sha256", "")), f"seed output {relative}")
        folded[relative.casefold()] = relative
        found[relative] = ExternalFile(relative, size, digest)
    return tuple(found[path] for path in sorted(found, key=str.casefold))


def _receipt_identity_payload(receipt: ExternalReceipt) -> dict[str, Any]:
    value = receipt.as_dict()
    value.pop("receipt_id")
    return value


def _write_immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValidationError(f"immutable external receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_existing_ancestors(path.parent, "external receipt directory")
    temporary = path.with_name(f".{path.name}.staging-{uuid.uuid4().hex}")
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ValidationError(f"immutable external receipt already exists: {path}") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def export_external_package(
    build: BuildResult,
    identity: SeedIdentity,
    *,
    mods_root: Path | str,
    state_root: Path | str,
    install: GameInstall,
    bblauncher: BBLauncherBuildPin,
    client_version: str,
    namespace: ExternalNamespace | None = None,
    suppression_manifest_sha256: str | None = None,
    created_at: datetime | None = None,
    allow_live_acceptance_candidate: bool = False,
    replace_existing: bool = False,
) -> ExternalExport:
    """Publish one data-only inactive package plus its out-of-band receipt.

    ``replace_existing`` lets a rebuild of the same seed replace the inactive
    package this companion exported earlier.  Only a regular directory carrying
    the companion's own package prefix is ever removed, and only from the
    inactive library: an activated copy still refuses, because BBLauncher owns
    deactivation.
    """

    selected = SeedIdentity.from_dict(identity.as_dict())
    verified = SeedCache(build.path.parent).verify(build.path, expected_key=build.cache_key)
    built_identity = SeedIdentity.from_dict(verified.manifest["identity"])
    if selected.cache_key != verified.cache_key or selected.cache_material() != built_identity.cache_material():
        raise ValidationError("selected seed identity does not describe the verified build bytes")
    external_namespace = (namespace or ExternalNamespace.for_identity(selected)).normalized()
    if external_namespace.cache_key != verified.cache_key:
        raise ValidationError("external cache namespace does not match the verified build")
    if external_namespace.ledger_key != session_key(selected.seed, selected.slot):
        raise ValidationError("external ledger namespace does not match the selected seed and slot")

    pin = bblauncher.normalized()
    compatibility = _compatibility(pin, allow_live_acceptance_candidate=allow_live_acceptance_candidate)
    if not client_version.strip():
        raise ValidationError("external export requires a client version")
    mods = _regular_directory(mods_root, "BBLauncher Mods directory")
    if _inside_named_directory(mods, ACTIVE_MODS_DIR_NAME):
        raise ValidationError("selected BBLauncher Mods directory is the active package directory")
    managed_root = mods.parent
    state = _absolute(state_root)
    _check_existing_ancestors(state, "companion state root")
    receipt_root = state / "external" / "receipts"
    build_root = _regular_directory(verified.path, "verified seed build")
    protected = [("game root", install.root), ("base game", install.base),
                 ("active game overlay", install.mods), ("verified seed build", build_root)]
    if install.patch is not None:
        protected.append(("game update", install.patch))
    for label, protected_path in protected:
        _check_existing_ancestors(protected_path, label)
    _require_separate(mods, protected + [("external receipt directory", receipt_root)])
    _require_separate(receipt_root, protected + [("BBLauncher Mods directory", mods)])
    _require_outside_bblauncher(state, "companion state root", managed_root)
    _require_outside_bblauncher(build_root, "verified seed cache", managed_root)

    records = _manifest_files(verified)
    package_name = f"{PACKAGE_PREFIX}{_safe_slot(selected.slot)}-{verified.cache_key[:12]}"
    target = mods / package_name
    stale = _replaceable_package(mods, package_name, replace=replace_existing)
    active_root = mods.with_name(ACTIVE_MODS_DIR_NAME)
    if active_root.exists() or active_root.is_symlink():
        active = _regular_directory(active_root, "BBLauncher active Mods directory")
        _refuse_casefold_child(active, package_name, "BBLauncher active Mods directory")
    stage = mods / f".{package_name}.staging-{uuid.uuid4().hex}"
    if stage.exists() or stage.is_symlink():
        raise ValidationError(f"external package staging path unexpectedly exists: {stage}")

    manifest_digest = None
    if suppression_manifest_sha256 is not None:
        manifest_digest = _require_sha256(
            suppression_manifest_sha256.lower(), "suppression manifest"
        )
    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValidationError("external receipt creation time must be timezone-aware")
    timestamp = timestamp.astimezone(timezone.utc)
    created = timestamp.isoformat().replace("+00:00", "Z")
    provisional = ExternalReceipt(
        "", created, package_name, verified.cache_key, selected, external_namespace, records,
        _absolute(install.root), install.serial, install.app_version, pin, compatibility,
        client_version.strip(), launcher_version(), sha256_file(build_root / SEED_MANIFEST_NAME),
        manifest_digest,
    )
    receipt_id = hashlib.sha256(canonical_json(_receipt_identity_payload(provisional))).hexdigest()
    receipt = ExternalReceipt(
        receipt_id, created, package_name, verified.cache_key, selected, external_namespace, records,
        provisional.game_root, install.serial, install.app_version, pin, compatibility,
        provisional.client_version, provisional.companion_version, provisional.build_manifest_sha256,
        provisional.suppression_manifest_sha256,
    )
    receipt_path = receipt_root / f"{receipt_id}.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValidationError(f"immutable external receipt already exists: {receipt_path}")

    stage.mkdir()
    try:
        for record in records:
            source = build_root.joinpath(*PurePosixPath(record.path).parts)
            if not source.is_file() or _is_reparse(source):
                raise ValidationError(f"seed output is no longer a regular file: {record.path}")
            output = stage.joinpath(*PurePosixPath(record.path).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
            if output.stat().st_size != record.size or sha256_file(output) != record.sha256:
                raise ValidationError(f"external package copy verification failed: {record.path}")
        _write_immutable_json(receipt_path, receipt.as_dict())
        # Receipt first: a crash may leave a harmless orphan receipt, but a
        # published package can never exist without its verification authority.
        stale = _replaceable_package(mods, package_name, replace=replace_existing)
        if stale is not None:
            shutil.rmtree(stale)
        os.rename(stage, target)
    finally:
        if stage.exists() and not _is_reparse(stage):
            shutil.rmtree(stage)
    return ExternalExport(target, receipt_path, receipt)


def load_external_receipt(
    path: Path | str, *, allow_live_acceptance_candidate: bool = False
) -> ExternalReceipt:
    source = _absolute(path)
    if not source.is_file() or _is_reparse(source):
        raise ValidationError(f"external receipt is not a regular file: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read external receipt {source}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("format") != EXTERNAL_RECEIPT_FORMAT:
        raise ValidationError(f"unsupported external receipt format: {source}")
    try:
        identity_raw = raw["identity"]
        namespace_raw = raw["namespace"]
        game = raw["game"]
        launcher = raw["bblauncher"]
        raw_files = raw["files"]
        if not all(isinstance(value, dict) for value in (identity_raw, namespace_raw, game, launcher)):
            raise TypeError
        if not isinstance(raw_files, list):
            raise TypeError
        identity = SeedIdentity.from_dict(identity_raw)
        namespace = ExternalNamespace(
            str(namespace_raw["cache_key"]), str(namespace_raw["ledger_key"])
        ).normalized()
        pin = BBLauncherBuildPin(
            str(launcher["build"]), str(launcher["commit"]),
            str(launcher["executable_sha256"]),
            launcher.get("compatibility") == "live-acceptance-candidate",
        ).normalized()
        files = tuple(
            ExternalFile(
                _safe_overlay_path(str(record["path"])),
                int(record["size"]),
                _require_sha256(str(record["sha256"]), "external file"),
            )
            for record in raw_files if isinstance(record, dict)
        )
        if len(files) != len(raw_files):
            raise TypeError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"external receipt is malformed: {source}") from exc
    cache_key = _require_sha256(str(raw.get("cache_key", "")), "external receipt cache_key")
    if cache_key != identity.cache_key or namespace.cache_key != cache_key:
        raise ValidationError("external receipt cache identity is inconsistent")
    if namespace.ledger_key != session_key(identity.seed, identity.slot):
        raise ValidationError("external receipt ledger namespace is inconsistent")
    versions = raw.get("versions")
    suppression = raw.get("suppression")
    if not isinstance(versions, dict) or not isinstance(suppression, dict):
        raise ValidationError("external receipt version or suppression metadata is malformed")
    if versions.get("world") != identity.world_build or versions.get("runtime") != identity.runtime_build:
        raise ValidationError("external receipt world/runtime metadata is inconsistent")
    if raw.get("source_hashes") != dict(sorted(identity.source_hashes.items())):
        raise ValidationError("external receipt source hashes are inconsistent")
    if (suppression.get("plan_sha256") != identity.suppression_plan_sha256
            or suppression.get("binder_sha256") != identity.suppression_binder_sha256):
        raise ValidationError("external receipt suppression identity is inconsistent")
    if raw.get("seed_options") != dict(identity.options):
        raise ValidationError("external receipt seed options are inconsistent")
    if raw.get("enemizer_identity") != identity.enemizer_seed:
        raise ValidationError("external receipt enemizer identity is inconsistent")
    folded = [record.path.casefold() for record in files]
    if len(set(folded)) != len(folded) or SUPPRESSION_PATH.casefold() not in folded:
        raise ValidationError("external receipt file set is ambiguous or incomplete")
    compatibility = _compatibility(pin, allow_live_acceptance_candidate=allow_live_acceptance_candidate)
    if launcher.get("compatibility") != compatibility:
        raise ValidationError("external receipt BBLauncher compatibility status is inconsistent")
    receipt = ExternalReceipt(
        _require_sha256(str(raw.get("receipt_id", "")), "external receipt id"),
        str(raw.get("created_at", "")), str(raw.get("package_name", "")), cache_key,
        identity, namespace, files, _absolute(str(game["root"])), str(game["serial"]),
        str(game["app_version"]), pin, compatibility,
        str(versions.get("client", "")),
        str(versions.get("companion", "")),
        _require_sha256(str(raw.get("build_manifest_sha256", "")), "build manifest"),
        (None if suppression.get("manifest_sha256") is None else
         _require_sha256(str(suppression["manifest_sha256"]), "suppression manifest")),
    )
    expected_package = f"{PACKAGE_PREFIX}{_safe_slot(identity.slot)}-{cache_key[:12]}"
    if receipt.package_name != expected_package or Path(receipt.package_name).name != receipt.package_name:
        raise ValidationError("external receipt package name is inconsistent or unsafe")
    expected_id = hashlib.sha256(canonical_json(_receipt_identity_payload(receipt))).hexdigest()
    if receipt.receipt_id != expected_id:
        raise ValidationError("external receipt identity digest does not match its contents")
    return receipt


def _validate_receipt_object(receipt: ExternalReceipt) -> None:
    if receipt.cache_key != receipt.identity.cache_key:
        raise ValidationError("external receipt cache identity is inconsistent")
    if (receipt.namespace.cache_key != receipt.cache_key
            or receipt.namespace.ledger_key != session_key(receipt.identity.seed, receipt.identity.slot)):
        raise ValidationError("external receipt namespace is inconsistent")
    expected_package = (
        f"{PACKAGE_PREFIX}{_safe_slot(receipt.identity.slot)}-{receipt.cache_key[:12]}"
    )
    if receipt.package_name != expected_package:
        raise ValidationError("external receipt package name is inconsistent")
    expected_id = hashlib.sha256(canonical_json(_receipt_identity_payload(receipt))).hexdigest()
    if receipt.receipt_id != expected_id:
        raise ValidationError("external receipt identity digest does not match its contents")


def _child_casefold(directory: Path, name: str, label: str) -> Path:
    try:
        matches = [entry for entry in directory.iterdir() if entry.name.casefold() == name.casefold()]
    except OSError as exc:
        raise ValidationError(f"could not enumerate {label} {directory}: {exc}") from exc
    if len(matches) != 1:
        raise ValidationError(
            f"{label} requires exactly one case-insensitive {name!r}; found {len(matches)}"
        )
    return matches[0]


def _resolve_casefold(root: Path, relative: str, label: str) -> Path:
    current = root
    for index, part in enumerate(PurePosixPath(relative).parts):
        current = _child_casefold(current, part, label)
        if index + 1 < len(PurePosixPath(relative).parts):
            if not current.is_dir() or _is_reparse(current):
                raise ValidationError(f"{label} crosses a non-directory or reparse point: {current}")
    return current


def _walk_regular_files(root: Path, label: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    folded: dict[str, str] = {}
    stack = [(root, PurePosixPath())]
    while stack:
        directory, prefix = stack.pop()
        if _is_reparse(directory):
            raise ValidationError(f"{label} contains a directory reparse point: {directory}")
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            raise ValidationError(f"could not enumerate {label} {directory}: {exc}") from exc
        local: dict[str, str] = {}
        for entry in entries:
            folded_name = entry.name.casefold()
            if folded_name in local:
                raise ValidationError(
                    f"{label} contains duplicate-case entries: {local[folded_name]}, {entry.name}"
                )
            local[folded_name] = entry.name
            relative = (prefix / entry.name).as_posix()
            if entry.is_dir() and not _is_reparse(entry):
                stack.append((entry, prefix / entry.name))
                continue
            if _is_reparse(entry):
                raise ValidationError(f"{label} contains an unexpected reparse point: {entry}")
            if not entry.is_file():
                raise ValidationError(f"{label} contains a non-file entry: {entry}")
            prior = folded.get(relative.casefold())
            if prior is not None:
                raise ValidationError(f"{label} contains duplicate-case paths: {prior}, {relative}")
            folded[relative.casefold()] = relative
            found[relative] = entry
    return found


def _stat_identity(path: Path) -> dict[str, Any]:
    """Best available filesystem generation evidence for boot arming.

    Bytes alone cannot distinguish BBLauncher restoring an old package with
    identical content.  File IDs and change timestamps make that transition
    observable on the supported Windows filesystem when the filesystem
    exposes them.  They supplement, rather than replace, complete hashes.
    """

    value = path.lstat()
    result: dict[str, Any] = {
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }
    if path.is_symlink():
        result["link_target"] = os.readlink(path)
    return result


def verify_external_activation(
    receipt: ExternalReceipt | Path | str,
    *,
    install: GameInstall,
    mods_root: Path | str,
    observed_at: datetime | None = None,
    allow_live_acceptance_candidate: bool = False,
) -> VerifiedExternalActivation:
    """Prove BBLauncher's complete effective AP file set without changing it."""

    document = (load_external_receipt(receipt,
                allow_live_acceptance_candidate=allow_live_acceptance_candidate)
                if not isinstance(receipt, ExternalReceipt) else receipt)
    _validate_receipt_object(document)
    compatibility = _compatibility(
        document.bblauncher,
        allow_live_acceptance_candidate=allow_live_acceptance_candidate,
    )
    if document.compatibility != compatibility:
        raise ValidationError("external receipt compatibility is no longer accepted")
    if (_absolute(install.root) != document.game_root or install.serial != document.game_serial
            or install.app_version != document.app_version
            or install.serial != SERIAL or install.app_version != APP_VERSION):
        raise ValidationError("external receipt belongs to a different game installation")

    mods = _regular_directory(mods_root, "BBLauncher Mods directory")
    if _inside_named_directory(mods, ACTIVE_MODS_DIR_NAME):
        raise ValidationError("selected BBLauncher Mods directory is the active package directory")
    active_root = _regular_directory(mods.with_name(ACTIVE_MODS_DIR_NAME), "BBLauncher active Mods directory")
    overlay = _regular_directory(install.mods, "BBLauncher game overlay")
    if any(entry.name.casefold() == ".bb-ap-owner.json" for entry in overlay.iterdir()):
        raise ValidationError(
            "BBLauncher-managed overlay contains a standalone Archipelago owner manifest"
        )
    packages = [entry for entry in active_root.iterdir() if entry.is_dir() and not _is_reparse(entry)]
    invalid = [entry for entry in active_root.iterdir() if not entry.is_dir() or _is_reparse(entry)]
    if invalid:
        raise ValidationError(f"BBLauncher active Mods directory contains an invalid entry: {invalid[0]}")
    folded_names: dict[str, Path] = {}
    for package in packages:
        if package.name.casefold() in folded_names:
            raise ValidationError("BBLauncher active package names collide case-insensitively")
        folded_names[package.name.casefold()] = package
    selected = folded_names.get(document.package_name.casefold())
    if selected is None:
        raise ValidationError(f"selected Archipelago package is not active: {document.package_name}")
    ap_packages = [package for package in packages if package.name.casefold().startswith(PACKAGE_PREFIX.casefold())]
    if len(ap_packages) != 1:
        raise ValidationError("exactly one Archipelago package must be active")

    expected = {record.path.casefold(): record for record in document.files}
    package_files: dict[Path, dict[str, Path]] = {}
    for package in packages:
        package_files[package] = _walk_regular_files(package, f"active package {package.name}")
    selected_files = package_files[selected]
    selected_canonical = {f"{DVDROOT_PREFIX}{path}".casefold(): path for path in selected_files}
    if set(selected_canonical) != set(expected):
        missing = sorted(set(expected) - set(selected_canonical))
        unexpected = sorted(set(selected_canonical) - set(expected))
        raise ValidationError(
            f"active Archipelago package file set drift: missing={missing} unexpected={unexpected}"
        )
    for package, files in package_files.items():
        if package == selected:
            continue
        collisions = sorted(
            f"{DVDROOT_PREFIX}{relative}" for relative in files
            if f"{DVDROOT_PREFIX}{relative}".casefold() in expected
        )
        if collisions:
            raise ValidationError(
                f"active package {package.name} collides with Archipelago-owned paths: "
                + ", ".join(collisions)
            )

    verified_files: list[VerifiedExternalFile] = []
    for record in document.files:
        stripped = record.path[len(DVDROOT_PREFIX):]
        source_relative = selected_canonical[record.path.casefold()]
        source = selected_files[source_relative]
        if source_relative.casefold() != stripped.casefold():
            raise ValidationError(f"active package path has an invalid wrapper shape: {source_relative}")
        if source.stat().st_size != record.size or sha256_file(source) != record.sha256:
            raise ValidationError(f"active package file changed: {record.path}")
        installed = _resolve_casefold(overlay, record.path, "effective game overlay")
        if installed.is_symlink():
            try:
                resolved = installed.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ValidationError(f"effective AP link is dangling or cyclic: {installed}") from exc
            try:
                expected_source = source.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ValidationError(f"active AP source cannot be resolved: {source}") from exc
            if os.path.normcase(str(resolved)) != os.path.normcase(str(expected_source)):
                raise ValidationError(
                    f"effective AP link escapes the selected active package: {installed} -> {resolved}"
                )
            mode = "symlink"
        else:
            if _is_reparse(installed) or not installed.is_file():
                raise ValidationError(f"effective AP path is not a regular file: {installed}")
            mode = "copy"
        if installed.stat().st_size != record.size or sha256_file(installed) != record.sha256:
            raise ValidationError(f"effective AP file hash changed: {record.path}")
        verified_files.append(
            VerifiedExternalFile(record.path, installed, source, record.sha256, mode)
        )

    timestamp = observed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValidationError("external verification observation must be timezone-aware")
    observed = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    fingerprint_material = {
        "receipt_id": document.receipt_id,
        "package": str(selected),
        "overlay": str(overlay),
        "active_packages": [
            {"name": package.name, "metadata": _stat_identity(package)}
            for package in sorted(packages, key=lambda item: item.name.casefold())
        ],
        "files": [
            {"path": item.path, "sha256": item.sha256, "installation": item.installation,
             "source": str(item.active_source), "installed": str(item.installed_path),
             "source_metadata": _stat_identity(item.active_source),
             "installed_metadata": _stat_identity(item.installed_path)}
            for item in verified_files
        ],
    }
    fingerprint = hashlib.sha256(canonical_json(fingerprint_material)).hexdigest()
    binder = next(item.installed_path for item in verified_files if item.path == SUPPRESSION_PATH)
    return VerifiedExternalActivation(
        document, active_root, selected, overlay, tuple(verified_files), binder, observed, fingerprint
    )
