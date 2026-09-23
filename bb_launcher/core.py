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

import copy
import hashlib
import json
import os
import re
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

from .version import launcher_version


SERIAL = "CUSA03173"
APP_VERSION = "01.09"
BASE_DIR_NAME = SERIAL
PATCH_DIR_NAMES = (f"{SERIAL}-patch", f"{SERIAL}-UPDATE")
MODS_DIR_NAME = f"{SERIAL}-mods"
USER_MODS_DIR_NAME = f"{SERIAL}-mods-user"
SEED_MANIFEST_NAME = "seed-manifest.json"
# This format is also part of ``SeedIdentity.cache_material``.  Bump it for
# any launcher-side generator change that can alter overlay bytes, even when
# the AP world/runtime build strings in an existing seed request are unchanged.
# v2 invalidated overlays made by the shared category-8 award event; those
# overlays could strand a completed delivery token after the client upgraded.
# v3 invalidates Cathedral overlays whose Laurence event could implicitly set
# the shuffled Forbidden Woods password flag after the altar interaction.
# v5 includes seed-owned item-name archives and pickup-plan cache material.
SEED_MANIFEST_FORMAT = "bb-launcher-seed-build-v5"
OWNER_NAME = ".bb-ap-owner.json"
OWNER_FORMAT = "bb-launcher-overlay-owner-v1"
TRANSACTION_NAME = ".bb-ap-launcher-transaction.json"
TRANSACTION_FORMAT = "bb-launcher-activation-transaction-v1"
DVDROOT_PREFIX = "dvdroot_ps4/"
SUPPRESSION_PATH = f"{DVDROOT_PREFIX}param/gameparam/gameparam.parambnd.dcx"
ITEM_NAMES_PATH = f"{DVDROOT_PREFIX}msg/engus/item.msgbnd.dcx"
ITEM_NAMES_PATHS = {ITEM_NAMES_PATH, f"{DVDROOT_PREFIX}msg/enggb/item.msgbnd.dcx"}
CATHEDRAL_EVENT_PATH = f"{DVDROOT_PREFIX}event/m24_00_00_00.emevd.dcx"
HEMWICK_EVENT_PATH = f"{DVDROOT_PREFIX}event/m22_00_00_00.emevd.dcx"
COMMON_EVENT_PATH = f"{DVDROOT_PREFIX}event/common.emevd.dcx"
BOSS_EVENT_PATH = f"{DVDROOT_PREFIX}event/m24_01_00_00.emevd.dcx"
BOSS_ENCOUNTER_REPORT_NAME = "boss-encounters-report.json"
# Native encounter outputs include plans and diagnostic receipts alongside
# loose game files.  They are retained under this cache-only path, never
# copied into the live shadPS4 overlay.
BOSS_ENCOUNTER_AUDIT_PREFIX = ".bb-boss-encounters/"
MAP_PREFIX = f"{DVDROOT_PREFIX}map/MapStudio/"
# The enemizer plan is retained beside the seed manifest, outside the overlay
# file set, so a bad swap can be named after the fact (bb-archipelago#321).
ENEMIZER_PLAN_NAME = "bb-enemizer-plan.json"
AI_PREFIX = f"{DVDROOT_PREFIX}script/"
AI_FILE_PATTERN = r"m\d{2}_\d{2}_\d{2}_00\.luabnd\.dcx"
SFX_PREFIX = f"{DVDROOT_PREFIX}sfx/"
SFX_FILE_PATTERN = r"frpg_sfxbnd_m\d{2}\.ffxbnd\.dcx"
BOSS_EVENT_FILE_PATTERN = r"m\d{2}_\d{2}_\d{2}_\d{2}\.emevd\.dcx"
USER_MERGE_FORMAT = "bb-launcher-user-merge-v1"
# The one operator escape hatch over suppression-binder hash skew
# (bb-archipelago#183).  Modeled on the delivery tool's
# --unvalidated-descriptor: opt-in per invocation, never persisted, and loud on
# every individual check it bypasses.  It covers *skew* only -- a binder built
# from a different seed plan or from a different source gameparam.  It never
# covers the binder-vs-its-own-manifest hash or the byte-identical-to-vanilla
# refusal: those are corruption, not skew, and no operator wants them anyway.
SUPPRESSION_OVERRIDE_KNOB = "--allow-suppression-mismatch"
SUPPRESSION_OVERRIDE_FORMAT = "bb-launcher-suppression-override-v1"
# The two bypassable checks, named for the manifest keys they compare, so the
# emitted line, the doctor finding and the recorded owner field say one word.
SUPPRESSION_CHECK_PLAN = "plan_sha256"
SUPPRESSION_CHECK_SOURCE = "source_gameparam_sha256"


def _short_hash(value: object) -> str:
    text = str(value)
    if value is None:
        return "(absent)"
    if len(text) == 64 and all(character in "0123456789abcdef" for character in text.lower()):
        return f"{text[:12]}..."
    return text


def suppression_override_line(
    check: str, expected: object, found: object, context: str | None = None
) -> str:
    """One loud ASCII line per bypassed suppression check.

    Every bypass gets its own line, naming the check, what was expected, what
    was actually there, and the knob that let it through -- so a log tail from
    a playtest tells you which of the two skews the operator waved past.
    """

    line = (
        f"*** {SUPPRESSION_OVERRIDE_KNOB}: {check} mismatch BYPASSED -- "
        f"expected {_short_hash(expected)}, found {_short_hash(found)}"
    )
    if context:
        line += f" ({context})"
    return line + " ***"
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
# A directory the launcher wrote, and is about to rewrite, is healed rather
# than policed (bb-archipelago#408): a player who copied mods into both
# CUSA03173-mods and CUSA03173-mods-user should not be stuck behind a refusal
# about a file the next activation overwrites anyway.  The damaged tree is
# moved aside under this name -- never deleted -- and the new ownership
# manifest records what happened, the same way ``suppression_override`` makes
# an overridden activation attributable.
OVERLAY_HEAL_PREFIX = f"{MODS_DIR_NAME}.bb-ap-foreign-"
OVERLAY_HEAL_FORMAT = "bb-launcher-overlay-heal-v1"
# The other half of the same policy: a directory with no ownership manifest at
# all, or one written by a different launcher, may be a player's hand-made mod
# folder.  Moving that is a bigger decision than the launcher gets to make, so
# it stays a refusal -- with the one instruction that resolves it.
FOREIGN_OVERLAY_ADVICE = (
    f"If this folder is yours, rename it; the launcher rebuilds {MODS_DIR_NAME} itself. "
    f"Player mods go in {USER_MODS_DIR_NAME}."
)
# Every strict caller guards what shadPS4 is about to load, so it must not
# heal -- but it can say which button rebuilds the overlay.
REBUILD_OVERLAY_HINT = " Run Randomize & Launch again to rebuild the overlay."


class LauncherError(RuntimeError):
    """Base class for actionable launcher failures."""


class ValidationError(LauncherError):
    """An input, build, or installed overlay failed closed."""


class DiscoveryError(LauncherError):
    """Automatic setup discovery was missing or ambiguous."""


class ConflictError(LauncherError):
    """Unowned content would be affected by an operation."""


class OverlayIntegrityError(ValidationError, ConflictError):
    """A launcher-owned overlay no longer matches the manifest it wrote.

    The directory still proves it was written by *this* launcher -- the
    ownership manifest is present, well formed, and ours -- but its files have
    since changed, gained an intruder, lost one, or collided by case.

    ``activate_build`` is about to rebuild that directory from a verified seed,
    so it heals the damage (moves the directory aside, never deletes) instead
    of refusing.  Every other caller guards what shadPS4 actually loads, or
    must never move user data, and stays strict.

    It derives from both ``ValidationError`` and ``ConflictError`` because the
    reasons it now unifies used to be raised as one or the other, and every
    existing caller and message must keep behaving exactly as before.
    """


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
    value = canonical_overlay_case(raw)
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
    is_owned_event = normalized in {CATHEDRAL_EVENT_PATH, HEMWICK_EVENT_PATH, COMMON_EVENT_PATH, BOSS_EVENT_PATH}
    is_boss_encounter_event = (
        normalized.startswith(f"{DVDROOT_PREFIX}event/")
        and re.fullmatch(BOSS_EVENT_FILE_PATTERN, normalized.removeprefix(f"{DVDROOT_PREFIX}event/")) is not None
    )
    is_ai = normalized.startswith(AI_PREFIX) and re.fullmatch(
        AI_FILE_PATTERN, normalized[len(AI_PREFIX):]) is not None
    is_sfx = normalized.startswith(SFX_PREFIX) and re.fullmatch(
        SFX_FILE_PATTERN, normalized[len(SFX_PREFIX):]) is not None
    if (not is_suppression and not is_map and not is_owned_event and not is_boss_encounter_event
            and not is_ai and not is_sfx and normalized not in ITEM_NAMES_PATHS):
        raise ValidationError(
            f"overlay path is outside the param/map/event/AI/SFX contract: {normalized}"
        )
    return normalized


def _safe_boss_receipt_path(raw: object) -> str:
    """Validate a native receipt-relative path without making it an overlay path."""
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw:
        raise ValidationError("boss encounter receipt has an invalid file path")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.as_posix() != raw or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError("boss encounter receipt has an unsafe file path")
    return path.as_posix()


def _is_boss_encounter_overlay_path(relative: str) -> bool:
    if relative == SUPPRESSION_PATH:
        return True
    if relative.startswith(MAP_PREFIX):
        return "/" not in relative[len(MAP_PREFIX):] and relative.endswith(".msb.dcx")
    if relative.startswith(AI_PREFIX):
        return re.fullmatch(AI_FILE_PATTERN, relative[len(AI_PREFIX):]) is not None
    if relative.startswith(SFX_PREFIX):
        return re.fullmatch(SFX_FILE_PATTERN, relative[len(SFX_PREFIX):]) is not None
    event_prefix = f"{DVDROOT_PREFIX}event/"
    return (relative.startswith(event_prefix)
            and re.fullmatch(BOSS_EVENT_FILE_PATTERN, relative[len(event_prefix):]) is not None)


@dataclass(frozen=True)
class BossEncounterIngress:
    """Receipt-verified generic encounter output before it enters a seed cache."""

    root: Path
    receipt: Mapping[str, Any]
    entries: tuple[dict[str, Any], ...]
    overlay_files: Mapping[str, Path]
    auxiliary_files: Mapping[str, Path]
    plan: Path
    source_plan: Path
    scaling: Mapping[str, Any]
    ai: Mapping[str, Any]
    input_event_overrides: Mapping[str, str]


def _read_boss_encounter_ingress(overlay: Path | str, source_binder: Path) -> BossEncounterIngress:
    """Validate native output as one closed file set before cache staging.

    The native report is the authority for both game files and diagnostics.
    Only the former may be activated; plans and reports remain cache-local
    evidence beneath :data:`BOSS_ENCOUNTER_AUDIT_PREFIX`.
    """
    root = Path(overlay).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValidationError("boss encounter overlay is not a regular directory")
    report_path = root / BOSS_ENCOUNTER_REPORT_NAME
    report = _read_json(report_path, "boss encounter receipt")
    if report.get("format") != "bb-boss-encounters-v1" or report.get("applied") is not True:
        raise ValidationError("boss encounter receipt is not an applied bb-boss-encounters-v1 report")
    if not isinstance(report.get("encounters"), list) or not report["encounters"]:
        raise ValidationError("boss encounter receipt carries no encounter records")
    rows = report.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValidationError("boss encounter receipt carries no files")
    entries: list[dict[str, Any]] = []
    overlay_files: dict[str, Path] = {}
    auxiliary_files: dict[str, Path] = {}
    receipt_paths: set[str] = set()
    folded_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError("boss encounter receipt file record is not an object")
        raw = _safe_boss_receipt_path(row.get("path"))
        size = row.get("size")
        if not isinstance(size, int) or size < 0:
            raise ValidationError(f"boss encounter receipt has an invalid size for {raw}")
        digest = _require_sha256(str(row.get("sha256", "")), f"boss encounter receipt {raw}")
        if raw.casefold() in folded_paths:
            raise ValidationError(f"boss encounter receipt repeats {raw}")
        receipt_paths.add(raw)
        folded_paths.add(raw.casefold())
        path = root.joinpath(*PurePosixPath(raw).parts)
        if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root)
                or path.stat().st_size != size or sha256_file(path) != digest):
            raise ValidationError(f"boss encounter receipt does not match {raw}")
        if _is_boss_encounter_overlay_path(raw):
            normalized = _safe_overlay_path(raw)
            if normalized != raw or normalized in overlay_files:
                raise ValidationError(f"boss encounter receipt has a noncanonical overlay file {raw}")
            overlay_files[normalized] = path
        else:
            auxiliary_files[raw] = path
        entries.append({"path": raw, "size": size, "sha256": digest})
    actual = _tree_files(root)
    if set(actual) != receipt_paths | {BOSS_ENCOUNTER_REPORT_NAME}:
        raise ValidationError("boss encounter output file set differs from its receipt")
    required_auxiliary = {
        ENEMIZER_PLAN_NAME, "source-enemizer-plan.json", "scaling-report.json",
        f"{DVDROOT_PREFIX}script.json",
    }
    if not required_auxiliary.issubset(auxiliary_files):
        raise ValidationError("boss encounter output is missing retained plan or diagnostic receipts")
    if SUPPRESSION_PATH not in overlay_files:
        raise ValidationError("boss encounter output is missing its gameparam binder")
    if not any(path.startswith(MAP_PREFIX) for path in overlay_files):
        raise ValidationError("boss encounter output is missing MapStudio files")
    if not any(path.startswith(AI_PREFIX) for path in overlay_files):
        raise ValidationError("boss encounter output is missing AI binders")
    plan_document = _read_json(auxiliary_files[ENEMIZER_PLAN_NAME], "boss encounter adjusted plan")
    override_rows = plan_document.get("input_event_overrides", [])
    if not isinstance(override_rows, list):
        raise ValidationError("boss encounter adjusted plan has invalid AP event overrides")
    input_event_overrides: dict[str, str] = {}
    for row in override_rows:
        if not isinstance(row, dict) or set(row) != {"file", "sha256"}:
            raise ValidationError("boss encounter adjusted plan has malformed AP event override")
        filename = row["file"]
        if not isinstance(filename, str) or re.fullmatch(BOSS_EVENT_FILE_PATTERN, filename) is None:
            raise ValidationError("boss encounter adjusted plan has unsupported AP event override")
        relative = f"{DVDROOT_PREFIX}event/{filename}"
        digest = _require_sha256(str(row["sha256"]), f"boss AP event override {filename}")
        if relative in input_event_overrides:
            raise ValidationError("boss encounter adjusted plan repeats an AP event override")
        input_event_overrides[relative] = digest
    scaling = _read_json(auxiliary_files["scaling-report.json"], "boss encounter scaling report")
    ai = _read_json(auxiliary_files[f"{DVDROOT_PREFIX}script.json"], "boss encounter AI report")
    if scaling.get("format") != "bb-enemizer-scaling-v1":
        raise ValidationError("boss encounter scaling report has an unsupported format")
    if scaling.get("source_gameparam_sha256") != sha256_file(source_binder):
        raise ValidationError("boss encounter scaling report does not start from the composed AP binder")
    if scaling.get("output_gameparam_sha256") != sha256_file(overlay_files[SUPPRESSION_PATH]):
        raise ValidationError("boss encounter scaling report does not match its output binder")
    if (scaling.get("source_plan_sha256") != sha256_file(auxiliary_files["source-enemizer-plan.json"])
            or scaling.get("output_plan_sha256") != sha256_file(auxiliary_files[ENEMIZER_PLAN_NAME])):
        raise ValidationError("boss encounter scaling report does not match its retained plans")
    if ai.get("format") != "bb-enemizer-ai-v1" or ai.get("plan_sha256") != sha256_file(auxiliary_files[ENEMIZER_PLAN_NAME]):
        raise ValidationError("boss encounter AI report does not match its adjusted plan")
    return BossEncounterIngress(
        root, report, tuple(entries), overlay_files, auxiliary_files,
        auxiliary_files[ENEMIZER_PLAN_NAME], auxiliary_files["source-enemizer-plan.json"], scaling, ai,
        input_event_overrides,
    )


def canonical_overlay_case(value: str) -> str:
    """Spell an overlay-relative path the one way the launcher records it.

    The overlay is consumed on case-insensitive filesystems, so
    ``map/mapstudio`` and ``map/MapStudio`` are one directory on disk but two
    different strings in a manifest.  Recording is pinned to the constants
    (``SUPPRESSION_PATH``, ``MAP_PREFIX``) so a spelling picked up from disk --
    the player's mods tree, the configured source MapStudio -- cannot fork the
    name of a file the launcher owns.
    """

    normalized = value.replace("\\", "/")
    if normalized.casefold() == SUPPRESSION_PATH.casefold():
        return SUPPRESSION_PATH
    for names_path in ITEM_NAMES_PATHS:
        if normalized.casefold() == names_path.casefold():
            return names_path
    if normalized.casefold() == CATHEDRAL_EVENT_PATH.casefold():
        return CATHEDRAL_EVENT_PATH
    if normalized.casefold() == HEMWICK_EVENT_PATH.casefold():
        return HEMWICK_EVENT_PATH
    if normalized.casefold() == COMMON_EVENT_PATH.casefold():
        return COMMON_EVENT_PATH
    if normalized.casefold() == BOSS_EVENT_PATH.casefold():
        return BOSS_EVENT_PATH
    if normalized.casefold().startswith(MAP_PREFIX.casefold()):
        return MAP_PREFIX + normalized[len(MAP_PREFIX) :]
    if normalized.casefold().startswith(AI_PREFIX.casefold()):
        return AI_PREFIX + normalized[len(AI_PREFIX) :]
    return normalized


def _safe_relative_path(raw: str) -> PurePosixPath:
    value = canonical_overlay_case(raw)
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError(f"unsafe game-relative path: {raw!r}")
    return path


def _tree_files(
    root: Path,
    *,
    ignore: Iterable[str] = (),
    allow_file_links: bool = False,
) -> dict[str, Path]:
    ignored = set(ignore)
    found: dict[str, Path] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() and not (allow_file_links and path.is_file()):
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
    suppression_binder_sha256: str | None = None

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
        binder_hash = None
        if self.suppression_binder_sha256 is not None:
            binder_hash = _require_sha256(
                self.suppression_binder_sha256, "suppression_binder_sha256"
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
            "suppression_binder_sha256": binder_hash,
        }
        canonical_json(value)
        return value

    @property
    def cache_key(self) -> str:
        return hashlib.sha256(canonical_json(self.cache_material())).hexdigest()

    def cache_material(self) -> dict[str, Any]:
        """Inputs that can change overlay bytes, excluding AP session identity."""
        value = self.as_dict()
        value.pop("seed")
        value.pop("slot")
        value["overlay_build_format"] = SEED_MANIFEST_FORMAT
        return value

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
            suppression_binder_sha256=(
                None
                if value.get("suppression_binder_sha256") is None
                else str(value["suppression_binder_sha256"])
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
        cathedral_event: Path | str | None = None,
        common_event: Path | str | None = None,
        hemwick_event: Path | str | None = None,
        enemizer_plan: Path | str | None = None,
        enemizer_options: Mapping[str, Any] | None = None,
        enemy_scripts: Path | str | None = None,
        enemy_ai_report: Mapping[str, Any] | None = None,
        boss_event: Path | str | None = None,
        boss_report: Mapping[str, Any] | None = None,
        scaling_report: Mapping[str, Any] | None = None,
        boss_encounter_overlay: Path | str | None = None,
        item_names: Path | str | Mapping[str, Path | str] | None = None,
        item_names_path: str = ITEM_NAMES_PATH,
        enemy_events: Mapping[str, Path | str] | None = None,
        enemy_event_report: Mapping[str, Any] | None = None,
    ) -> BuildResult:
        key = identity.cache_key
        destination = self.path_for(key)
        if destination.exists():
            result = self.verify(destination)
            existing_identity = SeedIdentity.from_dict(result.manifest["identity"])
            if existing_identity.cache_material() != identity.cache_material():
                raise ValidationError(f"cache key collision or identity drift at {destination}")
            return BuildResult(destination, result.manifest, True)

        source_binder = Path(suppression_binder).expanduser().resolve()
        if not source_binder.is_file() or source_binder.is_symlink():
            raise ValidationError(f"suppression binder is not a regular file: {source_binder}")
        encounter: BossEncounterIngress | None = None
        binder = source_binder
        if boss_encounter_overlay is not None:
            if not bool(identity.options.get("boss_encounters")):
                raise ValidationError("boss encounter overlay requires the boss_encounters cache option")
            if any(value is not None for value in (
                map_studio, enemizer_plan, enemy_scripts, enemy_ai_report, boss_event,
                boss_report, scaling_report,
            )):
                raise ValidationError("boss encounter overlay cannot be mixed with individual enemizer outputs")
            encounter = _read_boss_encounter_ingress(boss_encounter_overlay, source_binder)
            binder = encounter.overlay_files[SUPPRESSION_PATH]
            scaling_report = encounter.scaling
            enemy_ai_report = encounter.ai
        # An AP event that the generic native builder has composed cannot be
        # copied a second time.  The retained adjusted plan pins the original
        # AP input; replace it only after that hash check with the receipt-pinned
        # final event, which is what the player will activate.
        generic_event_inputs: dict[str, str] = {}
        if encounter is not None:
            def composed_event(relative: str, source: Path | str | None) -> Path | str | None:
                if source is None:
                    return None
                expected = encounter.input_event_overrides.get(relative)
                final = encounter.overlay_files.get(relative)
                if expected is None or final is None:
                    raise ValidationError(
                        f"boss encounter receipt did not compose the supplied AP event {relative}"
                    )
                original = Path(source).expanduser().resolve()
                if (not original.is_file() or original.is_symlink()
                        or sha256_file(original) != expected):
                    raise ValidationError(
                        f"boss encounter AP event input does not match its retained plan: {relative}"
                    )
                generic_event_inputs[relative] = expected
                return final
            cathedral_event = composed_event(CATHEDRAL_EVENT_PATH, cathedral_event)
            hemwick_event = composed_event(HEMWICK_EVENT_PATH, hemwick_event)
            if set(generic_event_inputs) != set(encounter.input_event_overrides):
                raise ValidationError("boss encounter retained plan has an unstaged AP event override")
        maps: list[Path] = []
        if encounter is not None:
            maps = sorted(
                (path for relative, path in encounter.overlay_files.items() if relative.startswith(MAP_PREFIX)),
                key=lambda path: path.name.lower(),
            )
        elif map_studio is not None:
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
        plan_source: Path | None = encounter.plan if encounter is not None else None
        plan_document: dict[str, Any] | None = (
            _read_json(encounter.plan, "boss encounter adjusted plan") if encounter is not None else None
        )
        if encounter is not None:
            if not isinstance(plan_document.get("swaps"), list):
                raise ValidationError("boss encounter adjusted plan carries no swap list")
        elif enemizer_plan is not None:
            if not maps:
                raise ValidationError("an enemizer plan was supplied without MapStudio outputs")
            plan_source = Path(enemizer_plan).expanduser().resolve()
            if not plan_source.is_file() or plan_source.is_symlink():
                raise ValidationError(f"enemizer plan is not a regular file: {plan_source}")
            plan_document = _read_json(plan_source, "enemizer plan")
            if not isinstance(plan_document.get("swaps"), list):
                raise ValidationError("enemizer plan carries no swap list")
        elif maps:
            raise ValidationError("MapStudio outputs require the enemizer plan that produced them")
        enemy_events = dict(enemy_events or {})
        if enemy_events and set(enemy_events) != {BOSS_EVENT_PATH}:
            raise ValidationError("wakeup fallback may only supply the managed m24_01 event")
        wakeup_fallbacks = [] if plan_document is None else plan_document.get("wakeup_fallbacks", [])
        wakeup_output_hash: str | None = None
        if not isinstance(wakeup_fallbacks, list):
            raise ValidationError("enemizer plan wakeup_fallbacks must be a list")
        if wakeup_fallbacks:
            for row in wakeup_fallbacks:
                if (not isinstance(row, dict)
                        or set(row) != {"logical_key", "entity_id", "map", "event_id"}
                        or not isinstance(row.get("logical_key"), str)
                        or not row["logical_key"]
                        or not isinstance(row.get("entity_id"), int)
                        or isinstance(row.get("entity_id"), bool)
                        or row.get("map") != "m24_01_00_00"
                        or row.get("event_id") != 12415130):
                    raise ValidationError("enemizer plan carries an invalid wakeup fallback row")
            if encounter is not None or boss_event is not None:
                raise ValidationError("wakeup fallback cannot be combined with a boss event overlay")
            if set(enemy_events) != {BOSS_EVENT_PATH} or enemy_event_report is None:
                raise ValidationError("enemizer plan wakeup fallbacks require the composed event and receipt")
            if identity.options.get("wakeup_fallback_version") != 1:
                raise ValidationError("wakeup fallback requires its versioned cache identity")
            if plan_source is None:
                raise ValidationError("wakeup fallback requires its retained enemizer plan")
            report = dict(enemy_event_report)
            if (report.get("format") != "bb-enemizer-wakeup-fallback-v1"
                    or report.get("applied") is not True
                    or report.get("plan_sha256") != sha256_file(plan_source)
                    or report.get("wakeup_fallbacks") != wakeup_fallbacks):
                raise ValidationError("wakeup fallback receipt does not match its plan")
            source_hash = _require_sha256(
                str(report.get("source_event_sha256", "")), "wakeup source event")
            if identity.source_hashes.get(BOSS_EVENT_PATH) != source_hash:
                raise ValidationError("wakeup fallback source event differs from the cache identity")
            wakeup_output_hash = _require_sha256(
                str(report.get("output_event_sha256", "")), "wakeup output event")
            event_source = Path(enemy_events[BOSS_EVENT_PATH]).expanduser().resolve()
            if (not event_source.is_file() or event_source.is_symlink()
                    or sha256_file(event_source) != wakeup_output_hash):
                raise ValidationError("wakeup fallback output differs from its receipt")
        elif enemy_events or enemy_event_report is not None:
            raise ValidationError("wakeup fallback output was supplied without planned fallback rows")
        scripts: list[Path] = []
        if encounter is not None:
            scripts = sorted(
                (path for relative, path in encounter.overlay_files.items() if relative.startswith(AI_PREFIX)),
                key=lambda path: path.name.lower(),
            )
        elif enemy_scripts is not None:
            script_root = Path(enemy_scripts)
            if not script_root.is_dir() or script_root.is_symlink():
                raise ValidationError("enemy AI scripts must be a regular directory")
            scripts = sorted(script_root.iterdir())
            if not scripts or any(not p.is_file() or p.is_symlink()
                    or re.fullmatch(AI_FILE_PATTERN, p.name) is None for p in scripts):
                raise ValidationError("enemy AI output contains no scripts or unexpected files")
            if not maps:
                raise ValidationError("enemy AI scripts require randomized maps")
        if identity.options.get("enemy_ai_version"):
            wanted = {p.name.split(".")[0][:-2] + "00.luabnd.dcx" for p in maps}
            if not wanted or {p.name for p in scripts} != wanted:
                raise ValidationError("randomized maps require matching enemy AI binders")

        self.root.mkdir(parents=True, exist_ok=True)
        stage = self.root / f".{key}.staging-{uuid.uuid4().hex}"
        stage.mkdir()
        try:
            inputs = [(SUPPRESSION_PATH, binder, "suppression")]
            if encounter is not None:
                inputs.extend(
                    (relative, path, "enemizer")
                    for relative, path in encounter.overlay_files.items()
                    if relative.startswith(MAP_PREFIX)
                )
                inputs.extend(
                    (relative, path, "enemizer-ai")
                    for relative, path in encounter.overlay_files.items()
                    if relative.startswith(AI_PREFIX)
                )
                inputs.extend(
                    (relative, path, "boss-encounter-sfx")
                    for relative, path in encounter.overlay_files.items()
                    if relative.startswith(SFX_PREFIX)
                )
                inputs.extend(
                    (relative, path, "boss-encounter-event")
                    for relative, path in encounter.overlay_files.items()
                    if (relative.startswith(f"{DVDROOT_PREFIX}event/")
                        and relative not in generic_event_inputs)
                )
            if item_names is not None:
                archives = item_names if isinstance(item_names, Mapping) else {item_names_path: item_names}
                for relative, source in archives.items():
                    if relative not in ITEM_NAMES_PATHS:
                        raise ValidationError("unsupported pickup-name language")
                    names = Path(source).expanduser().resolve()
                    if not names.is_file() or names.is_symlink():
                        raise ValidationError("item names archive is not a regular file")
                    inputs.append((relative, names, "pickup-names"))
            if wakeup_fallbacks:
                inputs.append((BOSS_EVENT_PATH, event_source, "enemizer-wakeup-fallback"))
            if boss_event is not None:
                event = Path(boss_event).expanduser().resolve()
                if not event.is_file() or event.is_symlink():
                    raise ValidationError('boss event is not a regular file')
                inputs.append((BOSS_EVENT_PATH, event, 'boss-event'))
            if cathedral_event is not None:
                event = Path(cathedral_event).expanduser().resolve()
                if not event.is_file() or event.is_symlink():
                    raise ValidationError(f"Cathedral event is not a regular file: {event}")
                inputs.append((CATHEDRAL_EVENT_PATH, event, "cathedral-event"))
            if common_event is not None:
                event = Path(common_event).expanduser().resolve()
                if not event.is_file() or event.is_symlink():
                    raise ValidationError(f"Common event is not a regular file: {event}")
                inputs.append((COMMON_EVENT_PATH, event, "common-event"))
            if hemwick_event is not None:
                event = Path(hemwick_event).expanduser().resolve()
                if not event.is_file() or event.is_symlink():
                    raise ValidationError(f"Hemwick event is not a regular file: {event}")
                inputs.append((HEMWICK_EVENT_PATH, event, "hemwick-event"))
            if encounter is None:
                inputs.extend(
                    (f"{MAP_PREFIX}{path.name}", path, "enemizer") for path in maps
                )
                inputs.extend((f"{AI_PREFIX}{path.name}", path, "enemizer-ai") for path in scripts)
            records: list[dict[str, Any]] = []
            recorded_paths: set[str] = set()
            for relative, source, component in inputs:
                relative = _safe_overlay_path(relative)
                if relative in recorded_paths:
                    raise ValidationError(f"seed inputs overlap at {relative}")
                recorded_paths.add(relative)
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
            plan_record: dict[str, Any] | None = None
            if plan_source is not None and plan_document is not None:
                retained = stage / ENEMIZER_PLAN_NAME
                shutil.copyfile(plan_source, retained)
                plan_hash = sha256_file(retained)
                if plan_hash != sha256_file(plan_source):
                    raise ValidationError("copy verification failed for the enemizer plan")
                plan_record = {
                    "name": ENEMIZER_PLAN_NAME,
                    "sha256": plan_hash,
                    "size": retained.stat().st_size,
                    "swap_count": len(plan_document["swaps"]),
                    "stress": plan_document.get("stress"),
                    "options": dict(enemizer_options or plan_document.get("options") or {}),
                }
            boss_encounter_record: dict[str, Any] | None = None
            if encounter is not None:
                audit_root = stage / BOSS_ENCOUNTER_AUDIT_PREFIX.rstrip("/")
                retained_auxiliary = []
                for row in encounter.entries:
                    relative = row["path"]
                    if relative == ENEMIZER_PLAN_NAME or relative in encounter.overlay_files:
                        continue
                    source = encounter.auxiliary_files[relative]
                    retained_path = audit_root.joinpath("files", *PurePosixPath(relative).parts)
                    retained_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, retained_path)
                    if sha256_file(retained_path) != row["sha256"]:
                        raise ValidationError(f"copy verification failed for boss encounter artifact {relative}")
                    retained_auxiliary.append({
                        **row,
                        "retained_path": (BOSS_ENCOUNTER_AUDIT_PREFIX + "files/" + relative),
                    })
                retained_report = audit_root / BOSS_ENCOUNTER_REPORT_NAME
                retained_report.parent.mkdir(parents=True, exist_ok=True)
                source_report = encounter.root / BOSS_ENCOUNTER_REPORT_NAME
                shutil.copyfile(source_report, retained_report)
                report_hash = sha256_file(source_report)
                if sha256_file(retained_report) != report_hash:
                    raise ValidationError("copy verification failed for boss encounter receipt")
                boss_encounter_record = {
                    "format": "bb-boss-encounters-v1",
                    "applied": True,
                    "receipt": {
                        "path": BOSS_ENCOUNTER_AUDIT_PREFIX + BOSS_ENCOUNTER_REPORT_NAME,
                        "size": retained_report.stat().st_size,
                        "sha256": report_hash,
                    },
                    "files": list(encounter.entries),
                    "auxiliary_files": retained_auxiliary,
                    "encounters": copy.deepcopy(encounter.receipt.get("encounters")),
                    "external_references": copy.deepcopy(encounter.receipt.get("external_references", [])),
                    "input_event_overrides": [
                        {"path": relative, "sha256": digest}
                        for relative, digest in sorted(generic_event_inputs.items())
                    ],
                }
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
                "cathedral_event": (
                    None if cathedral_event is None else {
                        "path": CATHEDRAL_EVENT_PATH,
                        "sha256": next(
                            record["sha256"] for record in records
                            if record["path"] == CATHEDRAL_EVENT_PATH
                        ),
                        "events": ([12400760, 12401803, 12405710, 12409990]
                                   if hemwick_event is not None
                                   else [12400760, 12401803, 12405710]),
                        "workshop_door_object": 2401202,
                        "workshop_badge_goods": 4114,
                        "laurence_witness_flag": 12401898,
                        "suppressed_password_flag": 12401803,
                        "input_sha256": generic_event_inputs.get(CATHEDRAL_EVENT_PATH),
                        "hemwick_gate": (None if hemwick_event is None else {
                            "event": 12409990, "access_flag": 12201898,
                            "object": 2401995, "sfx": 2403995,
                        }),
                    }
                ),
                "common_event": (
                    None if common_event is None else {
                        "path": COMMON_EVENT_PATH,
                        "sha256": next(record["sha256"] for record in records
                                       if record["path"] == COMMON_EVENT_PATH),
                        "event": 98000000,
                    }
                ),
                "hemwick_event": (
                    None if hemwick_event is None else {
                        "path": HEMWICK_EVENT_PATH,
                        "sha256": next(record["sha256"] for record in records
                                       if record["path"] == HEMWICK_EVENT_PATH),
                        "event": 12209990,
                        "access_flag": 12201898,
                        "object": 2201999,
                        "sfx": 2203999,
                        "input_sha256": generic_event_inputs.get(HEMWICK_EVENT_PATH),
                    }
                ),
                "enemizer": {
                    "enabled": bool(maps),
                    "seed": identity.enemizer_seed,
                    "file_count": len(maps),
                    "plan": plan_record,
                    "ai_file_count": len(scripts),
                    "ai": enemy_ai_report,
                    "boss": boss_report,
                    "boss_encounters": boss_encounter_record,
                    "scaling": scaling_report,
                },
            }
            if wakeup_fallbacks:
                report_hash = hashlib.sha256(canonical_json(report)).hexdigest()
                manifest["enemizer"]["wakeup_fallback"] = {
                    "path": BOSS_EVENT_PATH,
                    "sha256": wakeup_output_hash,
                    "report": report,
                    "report_sha256": report_hash,
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
        names_paths = identity.options.get("item_names_paths", [identity.options.get("item_names_path", ITEM_NAMES_PATH)])
        wanted_names = set(names_paths) if identity.options.get("toast_placeholders") else set()
        if wanted_names != ITEM_NAMES_PATHS.intersection(expected):
            raise ValidationError("pickup-name plan and item names archive must be installed together")
        all_actual = _tree_files(root, ignore=(SEED_MANIFEST_NAME, ENEMIZER_PLAN_NAME))
        actual = {
            relative: file for relative, file in all_actual.items()
            if not relative.startswith(BOSS_ENCOUNTER_AUDIT_PREFIX)
        }
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
        enemizer = manifest.get("enemizer")
        plan_record = enemizer.get("plan") if isinstance(enemizer, dict) else None
        retained_plan = root / ENEMIZER_PLAN_NAME
        if plan_record is not None:
            if not isinstance(plan_record, dict) or plan_record.get("name") != ENEMIZER_PLAN_NAME:
                raise ValidationError("seed manifest enemizer plan record is malformed")
            if not retained_plan.is_file() or retained_plan.is_symlink():
                raise ValidationError("seed build is missing its retained enemizer plan")
            plan_hash = _require_sha256(str(plan_record.get("sha256", "")), "enemizer plan")
            if sha256_file(retained_plan) != plan_hash:
                raise ValidationError("retained enemizer plan hash changed")
        elif retained_plan.exists():
            raise ValidationError("seed build carries an enemizer plan its manifest does not record")
        enemizer_manifest = manifest.get("enemizer")
        if not isinstance(enemizer_manifest, dict):
            raise ValidationError("seed manifest enemizer record is malformed")
        retained_plan_document = (
            _read_json(retained_plan, "enemizer plan") if plan_record is not None else None
        )
        planned_wakeup = ([] if retained_plan_document is None
                          else retained_plan_document.get("wakeup_fallbacks", []))
        if not isinstance(planned_wakeup, list):
            raise ValidationError("retained enemizer wakeup_fallbacks must be a list")
        wakeup_record = enemizer_manifest.get("wakeup_fallback")
        wakeup_event_record = expected.get(BOSS_EVENT_PATH)
        if wakeup_record is None:
            if planned_wakeup or (wakeup_event_record is not None
                                  and wakeup_event_record.get("component") == "enemizer-wakeup-fallback"):
                raise ValidationError("planned wakeup fallback has no manifest receipt")
        else:
            if (not isinstance(wakeup_record, dict)
                    or wakeup_record.get("path") != BOSS_EVENT_PATH
                    or identity.options.get("wakeup_fallback_version") != 1
                    or not planned_wakeup
                    or wakeup_event_record is None
                    or wakeup_event_record.get("component") != "enemizer-wakeup-fallback"):
                raise ValidationError("wakeup fallback manifest record is invalid")
            report = wakeup_record.get("report")
            if (not isinstance(report, dict)
                    or report.get("format") != "bb-enemizer-wakeup-fallback-v1"
                    or report.get("applied") is not True
                    or report.get("wakeup_fallbacks") != planned_wakeup
                    or report.get("plan_sha256") != plan_record.get("sha256")
                    or report.get("output_event_sha256") != wakeup_record.get("sha256")
                    or identity.source_hashes.get(BOSS_EVENT_PATH) != report.get("source_event_sha256")
                    or wakeup_event_record.get("sha256") != wakeup_record.get("sha256")
                    or wakeup_record.get("report_sha256") != hashlib.sha256(canonical_json(report)).hexdigest()):
                raise ValidationError("wakeup fallback receipt does not match the retained build")
        suppression = manifest.get("suppression")
        if not isinstance(suppression, dict):
            raise ValidationError("seed manifest is missing its suppression witness")
        if suppression.get("path") != SUPPRESSION_PATH:
            raise ValidationError("suppression witness points outside the overlay binder")
        if suppression.get("sha256") != expected[SUPPRESSION_PATH].get("sha256"):
            raise ValidationError("suppression witness hash does not match the binder record")
        cathedral = manifest.get("cathedral_event")
        cathedral_record = expected.get(CATHEDRAL_EVENT_PATH)
        hemwick_record = expected.get(HEMWICK_EVENT_PATH)
        if (cathedral is None) != (cathedral_record is None):
            raise ValidationError(
                "Cathedral event file and witness metadata must either both be present or both be absent"
            )
        if cathedral is not None:
            if not isinstance(cathedral, dict):
                raise ValidationError("Cathedral event witness is not an object")
            if cathedral.get("path") != CATHEDRAL_EVENT_PATH:
                raise ValidationError("Cathedral event witness points outside the managed event")
            assert cathedral_record is not None
            if cathedral_record.get("component") != "cathedral-event":
                raise ValidationError("Cathedral event output has the wrong component")
            if cathedral.get("sha256") != cathedral_record.get("sha256"):
                raise ValidationError("Cathedral event witness hash does not match its record")
            expected_cathedral_events = ([12400760, 12401803, 12405710, 12409990]
                                         if hemwick_record is not None
                                         else [12400760, 12401803, 12405710])
            if cathedral.get("events") != expected_cathedral_events:
                raise ValidationError("Cathedral event witness has unexpected owned events")
            if cathedral.get("workshop_door_object") != 2401202:
                raise ValidationError("Cathedral event witness has the wrong Workshop door")
            if cathedral.get("workshop_badge_goods") != 4114:
                raise ValidationError("Cathedral event witness has the wrong Workshop badge")
            if cathedral.get("laurence_witness_flag") != 12401898:
                raise ValidationError("Cathedral event witness has the wrong Laurence flag")
            if cathedral.get("suppressed_password_flag") != 12401803:
                raise ValidationError("Cathedral event witness has the wrong password flag")
            expected_gate = (None if hemwick_record is None else {
                "event": 12409990, "access_flag": 12201898,
                "object": 2401995, "sfx": 2403995,
            })
            if cathedral.get("hemwick_gate") != expected_gate:
                raise ValidationError("Cathedral event witness has the wrong Hemwick gate")
        common = manifest.get("common_event")
        common_record = expected.get(COMMON_EVENT_PATH)
        if (common is None) != (common_record is None):
            raise ValidationError("Common event file and witness must both be present or absent")
        if common is not None:
            if not isinstance(common, dict) or common.get("path") != COMMON_EVENT_PATH:
                raise ValidationError("Common event witness points outside the managed event")
            assert common_record is not None
            if (common_record.get("component") != "common-event"
                    or common.get("sha256") != common_record.get("sha256")
                    or common.get("event") != 98000000):
                raise ValidationError("Common category-8 event witness is invalid")
        hemwick = manifest.get("hemwick_event")
        if (hemwick is None) != (hemwick_record is None):
            raise ValidationError("Hemwick event file and witness must both be present or absent")
        if hemwick is not None:
            if not isinstance(hemwick, dict) or hemwick.get("path") != HEMWICK_EVENT_PATH:
                raise ValidationError("Hemwick event witness points outside the managed event")
            assert hemwick_record is not None
            if (hemwick_record.get("component") != "hemwick-event"
                    or hemwick.get("sha256") != hemwick_record.get("sha256")
                    or hemwick.get("event") != 12209990
                    or hemwick.get("access_flag") != 12201898
                    or hemwick.get("object") != 2201999
                    or hemwick.get("sfx") != 2203999):
                raise ValidationError("Hemwick gate event witness is invalid")
        boss = enemizer_manifest.get('boss')
        boss_encounters = manifest.get('enemizer', {}).get('boss_encounters')
        boss_file_record = expected.get(BOSS_EVENT_PATH)
        boss_record = (boss_file_record if boss_file_record is not None
                       and boss_file_record.get("component") == "boss-event" else None)
        boss_enabled = bool(identity.options.get('boss_canary'))
        boss_encounters_enabled = bool(identity.options.get('boss_encounters'))
        if boss_enabled and boss_encounters_enabled:
            raise ValidationError('legacy and generic boss encounter options cannot be combined')
        if boss_encounters_enabled != (boss_encounters is not None):
            raise ValidationError('boss encounter option and receipt must agree')
        if boss_encounters_enabled and boss is not None:
            raise ValidationError('generic boss encounter build cannot carry a legacy boss receipt')
        if not boss_encounters_enabled and any(
                relative.startswith(BOSS_ENCOUNTER_AUDIT_PREFIX) for relative in all_actual):
            raise ValidationError('seed build carries boss encounter audit files without its receipt')
        if not boss_encounters_enabled and (boss_enabled != (boss_record is not None) or boss_enabled != (boss is not None)):
            raise ValidationError('boss option, event and receipt must agree')
        if boss_enabled and not boss_encounters_enabled:
            if (not isinstance(boss, dict) or boss.get('adapter') != 'bsb-at-cleric-v1'
                    or boss.get('applied') is not True or boss.get('completion_event') != 12411700
                    or boss_record.get('component') != 'boss-event'
                    or boss.get('output_event_sha256') != boss_record.get('sha256')):
                raise ValidationError('boss encounter receipt mismatch')
            boss_files = {r['path']: r['sha256'] for r in boss.get('files', [])}
            for relative, record in expected.items():
                if relative in {SUPPRESSION_PATH, BOSS_EVENT_PATH} or relative.startswith((MAP_PREFIX, AI_PREFIX)):
                    if boss_files.get(relative) != record.get('sha256'):
                        raise ValidationError('boss receipt does not match composed overlay')
            if not plan_record or boss_files.get(ENEMIZER_PLAN_NAME) != plan_record.get('sha256'):
                raise ValidationError('boss receipt does not match retained plan')
        if boss_encounters_enabled:
            if not isinstance(boss_encounters, dict):
                raise ValidationError('boss encounter receipt is malformed')
            if boss_encounters.get('format') != 'bb-boss-encounters-v1' or boss_encounters.get('applied') is not True:
                raise ValidationError('boss encounter receipt has an unsupported format')
            receipt = boss_encounters.get('receipt')
            rows = boss_encounters.get('files')
            retained_auxiliary = boss_encounters.get('auxiliary_files')
            if (not isinstance(receipt, dict) or not isinstance(rows, list)
                    or not isinstance(retained_auxiliary, list) or not plan_record):
                raise ValidationError('boss encounter receipt has incomplete audit records')
            receipt_relative = BOSS_ENCOUNTER_AUDIT_PREFIX + BOSS_ENCOUNTER_REPORT_NAME
            if receipt.get('path') != receipt_relative:
                raise ValidationError('boss encounter receipt is retained at an unexpected path')
            receipt_path = root / receipt_relative
            if (not receipt_path.is_file() or receipt_path.is_symlink()
                    or receipt_path.stat().st_size != receipt.get('size')
                    or sha256_file(receipt_path) != _require_sha256(str(receipt.get('sha256', '')), 'boss encounter receipt')):
                raise ValidationError('retained boss encounter receipt changed')
            receipt_document = _read_json(receipt_path, 'retained boss encounter receipt')
            if (receipt_document.get('format') != 'bb-boss-encounters-v1'
                    or receipt_document.get('applied') is not True):
                raise ValidationError('retained boss encounter receipt is invalid')
            normalized_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValidationError('boss encounter audit file record is malformed')
                relative = _safe_boss_receipt_path(row.get('path'))
                size = row.get('size')
                if not isinstance(size, int) or size < 0:
                    raise ValidationError('boss encounter audit file size is malformed')
                normalized_rows.append({
                    'path': relative, 'size': size,
                    'sha256': _require_sha256(str(row.get('sha256', '')), f'boss encounter audit {relative}'),
                })
            if receipt_document.get('files') != normalized_rows:
                raise ValidationError('retained boss encounter receipt file list changed')
            if boss_encounters.get('encounters') != receipt_document.get('encounters'):
                raise ValidationError('boss encounter summary differs from its retained receipt')
            if boss_encounters.get('external_references') != receipt_document.get('external_references', []):
                raise ValidationError('boss external-reference summary differs from its retained receipt')
            by_path = {row['path']: row for row in normalized_rows}
            if len(by_path) != len(normalized_rows):
                raise ValidationError('boss encounter audit repeats a file path')
            expected_overlay = {
                relative: record for relative, record in expected.items()
                if record.get('component') in {
                    'suppression', 'enemizer', 'enemizer-ai', 'boss-encounter-event',
                    'boss-encounter-sfx',
                    'cathedral-event', 'hemwick-event',
                }
            }
            receipt_overlay = {
                relative: row for relative, row in by_path.items()
                if _is_boss_encounter_overlay_path(relative)
            }
            if set(expected_overlay) != set(receipt_overlay):
                raise ValidationError('boss encounter receipt and cached overlay file sets differ')
            for relative, row in receipt_overlay.items():
                record = expected_overlay[relative]
                if record.get('size') != row['size'] or record.get('sha256') != row['sha256']:
                    raise ValidationError(f'boss encounter receipt does not match cached {relative}')
            overrides = boss_encounters.get('input_event_overrides')
            if not isinstance(overrides, list):
                raise ValidationError('boss encounter AP event override record is malformed')
            normalized_overrides: dict[str, str] = {}
            for row in overrides:
                if not isinstance(row, dict) or set(row) != {'path', 'sha256'}:
                    raise ValidationError('boss encounter AP event override record is malformed')
                relative = _safe_overlay_path(str(row['path']))
                if relative not in {CATHEDRAL_EVENT_PATH, HEMWICK_EVENT_PATH}:
                    raise ValidationError('boss encounter AP event override path is unsupported')
                if relative in normalized_overrides:
                    raise ValidationError('boss encounter AP event override repeats a path')
                normalized_overrides[relative] = _require_sha256(
                    str(row['sha256']), f'boss encounter AP event override {relative}'
                )
            adjusted = _read_json(retained_plan, 'retained boss encounter adjusted plan')
            plan_overrides: dict[str, str] = {}
            raw_plan_overrides = adjusted.get('input_event_overrides', [])
            if not isinstance(raw_plan_overrides, list):
                raise ValidationError('retained boss encounter plan has invalid AP event overrides')
            for row in raw_plan_overrides:
                if not isinstance(row, dict) or set(row) != {'file', 'sha256'}:
                    raise ValidationError('retained boss encounter plan has malformed AP event override')
                filename = row['file']
                if not isinstance(filename, str) or re.fullmatch(BOSS_EVENT_FILE_PATTERN, filename) is None:
                    raise ValidationError('retained boss encounter plan has unsupported AP event override')
                relative = f'{DVDROOT_PREFIX}event/{filename}'
                if relative in plan_overrides:
                    raise ValidationError('retained boss encounter plan repeats an AP event override')
                plan_overrides[relative] = _require_sha256(
                    str(row['sha256']), f'retained boss AP event override {filename}'
                )
            if normalized_overrides != plan_overrides:
                raise ValidationError('boss encounter AP event override record differs from retained plan')
            for relative, digest in normalized_overrides.items():
                record = expected.get(relative)
                witness = cathedral if relative == CATHEDRAL_EVENT_PATH else hemwick
                component = 'cathedral-event' if relative == CATHEDRAL_EVENT_PATH else 'hemwick-event'
                if (record is None or record.get('component') != component
                        or not isinstance(witness, dict) or witness.get('input_sha256') != digest):
                    raise ValidationError('boss encounter AP event override is not bound to its final event')
            auxiliary_by_source = {}
            for row in retained_auxiliary:
                if not isinstance(row, dict):
                    raise ValidationError('boss encounter auxiliary record is malformed')
                source = _safe_boss_receipt_path(row.get('path'))
                retained = row.get('retained_path')
                expected_retained = BOSS_ENCOUNTER_AUDIT_PREFIX + 'files/' + source
                if retained != expected_retained or source in auxiliary_by_source:
                    raise ValidationError('boss encounter auxiliary path is malformed')
                if source not in by_path or _is_boss_encounter_overlay_path(source) or source == ENEMIZER_PLAN_NAME:
                    raise ValidationError('boss encounter auxiliary record names the wrong file')
                if row.get('size') != by_path[source]['size'] or row.get('sha256') != by_path[source]['sha256']:
                    raise ValidationError('boss encounter auxiliary record differs from its receipt')
                retained_path = root / retained
                if (not retained_path.is_file() or retained_path.is_symlink()
                        or retained_path.stat().st_size != row['size'] or sha256_file(retained_path) != row['sha256']):
                    raise ValidationError(f'boss encounter auxiliary file changed: {source}')
                auxiliary_by_source[source] = row
            expected_auxiliary = set(by_path) - set(receipt_overlay) - {ENEMIZER_PLAN_NAME}
            if set(auxiliary_by_source) != expected_auxiliary:
                raise ValidationError('boss encounter auxiliary file set differs from its receipt')
            actual_audit = {
                relative for relative in all_actual if relative.startswith(BOSS_ENCOUNTER_AUDIT_PREFIX)
            }
            expected_audit = {receipt_relative} | {
                str(row['retained_path']) for row in retained_auxiliary
            }
            if actual_audit != expected_audit:
                raise ValidationError('boss encounter retained audit file set drifted')
            if (by_path.get(ENEMIZER_PLAN_NAME, {}).get('sha256') != plan_record.get('sha256')
                    or by_path.get(ENEMIZER_PLAN_NAME, {}).get('size') != plan_record.get('size')):
                raise ValidationError('boss encounter receipt does not match the retained adjusted plan')
            scaling_path = root / auxiliary_by_source['scaling-report.json']['retained_path']
            source_plan_path = root / auxiliary_by_source['source-enemizer-plan.json']['retained_path']
            ai_path = root / auxiliary_by_source[f'{DVDROOT_PREFIX}script.json']['retained_path']
            scaling = manifest.get('enemizer', {}).get('scaling')
            ai = manifest.get('enemizer', {}).get('ai')
            if (not isinstance(scaling, dict) or scaling != _read_json(scaling_path, 'retained boss scaling report')
                    or scaling.get('source_plan_sha256') != sha256_file(source_plan_path)
                    or scaling.get('output_plan_sha256') != plan_record.get('sha256')
                    or scaling.get('output_gameparam_sha256') != expected[SUPPRESSION_PATH].get('sha256')):
                raise ValidationError('boss encounter scaling receipt mismatch')
            if (not isinstance(ai, dict) or ai != _read_json(ai_path, 'retained boss AI report')
                    or ai.get('format') != 'bb-enemizer-ai-v1'
                    or ai.get('plan_sha256') != plan_record.get('sha256')):
                raise ValidationError('boss encounter AI receipt mismatch')
            ai_maps = ai.get('maps')
            if not isinstance(ai_maps, list) or not ai_maps:
                raise ValidationError('boss encounter AI receipt carries no map records')
            named_ai = {
                AI_PREFIX + str(row.get('map', '')): row
                for row in ai_maps if isinstance(row, dict)
            }
            expected_ai = {
                relative: record for relative, record in expected.items()
                if record.get('component') == 'enemizer-ai'
            }
            if len(named_ai) != len(ai_maps) or set(named_ai) != set(expected_ai):
                raise ValidationError('boss encounter AI receipt file set mismatch')
            for relative, record in expected_ai.items():
                row = named_ai[relative]
                if row.get('missing_goals_after') != 0 or row.get('output_sha256') != record.get('sha256'):
                    raise ValidationError('boss encounter AI output mismatch or missing goals')
        scaling = manifest.get('enemizer', {}).get('scaling')
        scaling_enabled = bool(identity.options.get('normalize_scaling')) or boss_enabled
        if not boss_encounters_enabled and scaling_enabled != (scaling is not None):
            raise ValidationError('normalization option and receipt must agree')
        if scaling_enabled and not boss_encounters_enabled:
            if (not isinstance(scaling, dict) or scaling.get('applied') is not True or not plan_record
                    or scaling.get('output_plan_sha256') != plan_record.get('sha256')
                    or scaling.get('output_gameparam_sha256') != expected[SUPPRESSION_PATH].get('sha256')):
                raise ValidationError('normalization receipt mismatch')
        ai_records = {p: r for p, r in expected.items() if p.startswith(AI_PREFIX)}
        if scaling_enabled and not boss_encounters_enabled:
            ai = manifest.get('enemizer', {}).get('ai') or {}
            if ai.get('applied') is not True or ai.get('plan_sha256') != plan_record.get('sha256'):
                raise ValidationError('experimental AI receipt does not match plan')
            ai_maps = ai.get('maps', [])
            named = {AI_PREFIX + row.get('map', ''): row for row in ai_maps}
            if len(named) != len(ai_maps) or set(named) != set(ai_records):
                raise ValidationError('experimental AI receipt file set mismatch')
            for relative, record in ai_records.items():
                row = named[relative]
                if row.get('missing_goals_after') != 0 or row.get('output_sha256') != record.get('sha256'):
                    raise ValidationError('experimental AI output mismatch or missing goals')
        if any(r.get("component") != "enemizer-ai" for r in ai_records.values()):
            raise ValidationError("enemy AI output has the wrong component")
        if ai_records and identity.enemizer_seed is None:
            raise ValidationError("enemy AI outputs require an enemizer seed")
        if manifest.get("enemizer", {}).get("ai_file_count", 0) != len(ai_records):
            raise ValidationError("enemy AI binder count does not match the manifest")
        if identity.options.get("enemy_ai_version"):
            wanted_ai = {AI_PREFIX + p[len(MAP_PREFIX):].split(".")[0][:-2] + "00.luabnd.dcx"
                         for p in expected if p.startswith(MAP_PREFIX)}
            if not wanted_ai or set(ai_records) != wanted_ai:
                raise ValidationError("randomized maps require matching enemy AI binders")
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
    if not owner_path.is_file() or owner_path.is_symlink():
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
    # The set comparison is case-insensitive for the same reason the user-merge
    # ap-owned rule is: the overlay is consumed on a case-insensitive
    # filesystem, where "map/mapstudio/x" and "map/MapStudio/x" are one file.
    # Recording is canonical now, but manifests written before that are already
    # in the wild, and one of them must still verify against its own disk tree
    # rather than reporting the same file as both missing and unowned.
    # Some shadPS4 game managers deduplicate ordinary files in an activated
    # mods tree by replacing them with file symlinks.  Reading through such a
    # link is safe here because the ownership checks below still require its
    # resolved bytes and size to match the recorded manifest.  Directory,
    # broken, and user-source links remain forbidden.
    actual = _tree_files(root, ignore=(OWNER_NAME,), allow_file_links=True)
    actual_by_key: dict[str, str] = {}
    for relative in actual:
        key = relative.casefold()
        if key in actual_by_key:
            raise OverlayIntegrityError(
                "managed overlay holds two files differing only by case: "
                f"{actual_by_key[key]} and {relative}"
            )
        actual_by_key[key] = relative
    expected_keys = {relative.casefold() for relative in expected}
    if set(actual_by_key) != expected_keys:
        missing = sorted(
            relative for relative in expected if relative.casefold() not in actual_by_key
        )
        unowned = sorted(
            relative for relative in actual if relative.casefold() not in expected_keys
        )
        raise OverlayIntegrityError(
            "managed overlay contains unowned or missing files; "
            f"missing={missing} "
            f"unowned={unowned}"
        )
    for relative, record in expected.items():
        digest = _require_sha256(str(record.get("sha256", "")), f"owned file {relative}")
        found = actual[actual_by_key[relative.casefold()]]
        if found.stat().st_size != record.get("size"):
            raise OverlayIntegrityError(f"owned overlay file size changed: {relative}")
        if sha256_file(found) != digest:
            raise OverlayIntegrityError(f"owned overlay file hash changed: {relative}")
    return owner


def _move_overlay_aside(install: GameInstall, reason: str) -> dict[str, Any]:
    """Carry a damaged launcher-owned overlay out of the way, keeping its bytes.

    shadPS4 resolves exactly one mods directory, so the overlay cannot simply
    be rebuilt around the intruder.  It is renamed -- never deleted, never
    merged -- to a timestamped sibling, and the returned note goes into the new
    ownership manifest so a later bug report against that seed says where the
    displaced files went and why they were displaced.
    """

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    destination = install.root / f"{OVERLAY_HEAL_PREFIX}{stamp}"
    suffix = 1
    while destination.exists():
        destination = install.root / f"{OVERLAY_HEAL_PREFIX}{stamp}-{suffix}"
        suffix += 1
    os.replace(install.mods, destination)
    return {
        "format": OVERLAY_HEAL_FORMAT,
        "reason": reason,
        "moved_to": destination.name,
    }


def overlay_heal_line(note: Mapping[str, Any]) -> str:
    """The one player-facing sentence for a healed overlay."""

    return (
        f"The launcher-owned overlay {MODS_DIR_NAME} had been modified "
        f"({note.get('reason')}). It was moved to {note.get('moved_to')} and rebuilt "
        f"from the verified seed. Player mods belong in {USER_MODS_DIR_NAME} only."
    )


def _windows_process_is_running(name: str) -> bool:
    """Query tasklist without decoding its locale-dependent output.

    CPython's subprocess reader can leave ``stdout`` as ``None`` when decoding
    tasklist output fails. Process image names used by the launcher are ASCII,
    so comparing bytes avoids that failure and works in every Windows locale.
    An incomplete scan must stop activation instead of being mistaken for an
    all-clear result.
    """

    try:
        encoded_name = name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValidationError(
            f"cannot check whether {name!r} is running: process names must be ASCII"
        ) from exc
    if not encoded_name or any(character in encoded_name for character in b'\r\n"'):
        raise ValidationError(f"cannot check whether {name!r} is running: invalid process name")

    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise ValidationError(
            f"could not check whether {name} is running: tasklist could not start; "
            "close shadPS4 manually and retry"
        ) from exc
    if result.returncode != 0:
        raise ValidationError(
            f"could not check whether {name} is running: tasklist exited with "
            f"code {result.returncode}; close shadPS4 manually and retry"
        )
    if not isinstance(result.stdout, bytes) or not result.stdout.strip():
        raise ValidationError(
            f"could not check whether {name} is running: tasklist returned no output; "
            "close shadPS4 manually and retry"
        )
    expected_field = b'"' + encoded_name.lower() + b'",'
    return any(
        line.lstrip().lower().startswith(expected_field)
        for line in result.stdout.splitlines()
    )


def _shad_is_running() -> bool:
    if sys.platform == "win32":
        return _windows_process_is_running("shadPS4.exe")
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
        return _windows_process_is_running(name)
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
    previous_identity: Mapping[str, Any] | None = None,
    user_sources: Mapping[str, Path] | None = None,
    merge: UserModMerge | None = None,
    suppression_override: Sequence[str] | None = None,
    activation_identity: SeedIdentity | None = None,
    heal_notes: Sequence[Mapping[str, Any]] | None = None,
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
        "previous_identity": (
            None if previous_identity is None else dict(previous_identity)
        ),
        "identity": (
            build.manifest["identity"]
            if activation_identity is None
            else activation_identity.as_dict()
        ),
        "build_manifest_sha256": sha256_file(build.path / SEED_MANIFEST_NAME),
        "files": build.manifest["files"],
        "suppression": build.manifest["suppression"],
        "common_event": build.manifest.get("common_event"),
        "cathedral_event": build.manifest.get("cathedral_event"),
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
    # Present only when the operator override actually fired, so an ordinary
    # activation writes byte-identical ownership json to the one it always
    # has, and the presence of the key is itself the attribution
    # (bb-archipelago#183).
    if suppression_override:
        owner["suppression_validation"] = {
            "format": SUPPRESSION_OVERRIDE_FORMAT,
            "overridden": True,
            "knob": SUPPRESSION_OVERRIDE_KNOB,
            "bypassed": list(suppression_override),
        }
    # Same rule as the override above: present only when it actually happened,
    # so the presence of the key is itself the attribution
    # (bb-archipelago#408).
    if heal_notes:
        owner["healed_from"] = [dict(note) for note in heal_notes]
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
    suppression_override: Sequence[str] | None = None,
    identity: SeedIdentity | None = None,
    adopt_foreign_overlay: bool = False,
) -> dict[str, Any]:
    """Atomically activate a verified build, preserving any owned predecessor.

    ``suppression_override`` names the suppression checks an operator bypassed
    for this build (bb-archipelago#183); it is recorded in the ownership
    manifest so a later bug report against this overlay is attributable.

    This is the one operation that *heals* rather than polices the directory it
    owns: an overlay that still proves launcher ownership but whose files were
    modified is moved aside and rebuilt, and the resulting owner dict carries a
    ``healed_from`` note for the caller to report (bb-archipelago#408).  A
    directory with no ownership manifest, or one from another launcher, is
    still refused by default -- it may be the player's own work, and moving it
    is a bigger decision than the launcher gets to make on its own.  A caller
    that has gotten the player's explicit confirmation that the folder is not
    theirs to keep may pass ``adopt_foreign_overlay=True`` to have it moved
    aside (never deleted), the same way a damaged owned overlay is healed,
    instead of leaving the player to rename it outside the app.
    """

    _require_shad_stopped(process_is_running)
    heal_notes: list[dict[str, Any]] = []
    recover_activation(
        install, process_is_running=process_is_running, heal_notes=heal_notes
    )
    build = SeedCache(Path(build_path).resolve().parent).verify(build_path)
    if identity is not None:
        built_identity = SeedIdentity.from_dict(build.manifest["identity"])
        if identity.cache_material() != built_identity.cache_material():
            raise ValidationError("activation identity does not describe the cached overlay")
    user_sources, merge = plan_activation_merge(install, build)
    previous_owner = None
    if install.mods.exists():
        try:
            previous_owner = _load_owner(install.mods)
        except OverlayIntegrityError as exc:
            # Ours, and damaged.  We are about to rewrite this directory from a
            # verified seed, so refusing only strands the player.
            heal_notes.append(_move_overlay_aside(install, str(exc)))
        except ConflictError as exc:
            # No manifest at all, or another launcher's: possibly the player's
            # own mod folder.  Moving it is not the launcher's call, unless the
            # player has explicitly said otherwise via adopt_foreign_overlay.
            # A symlinked or non-directory path is a different problem and
            # keeps its own message regardless.
            if not install.mods.is_dir() or install.mods.is_symlink():
                raise
            if not adopt_foreign_overlay:
                raise ConflictError(f"{exc} {FOREIGN_OVERLAY_ADVICE}") from exc
            heal_notes.append(_move_overlay_aside(install, str(exc)))
    if previous_owner is not None:
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
            # A heal earlier in this call must reach the ownership manifest, so
            # it always runs the full transaction rather than short-circuiting
            # on an overlay whose recovery just carried a damaged predecessor
            # aside (bb-archipelago#408).
            not heal_notes
            and previous_owner["cache_key"] == build.cache_key
            and (identity is None or previous_owner.get("identity") == identity.as_dict())
            and active_fingerprint == merge.fingerprint
        ):
            # The manifest on disk keeps its ``healed_from`` attribution
            # forever, but a heal is news exactly once: the run that did it.
            # Re-reporting it on every later launch of the same seed would read
            # as a fresh problem.
            unchanged = dict(previous_owner)
            unchanged.pop("healed_from", None)
            return unchanged
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
            None if previous_owner is None else previous_owner.get("identity"),
            user_sources,
            merge,
            suppression_override,
            identity,
            heal_notes,
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
            # A damaged but still launcher-owned overlay is also left where it
            # is: the next activation heals it, and rollback reporting a
            # failure about it would bury the real one.
            try:
                _load_owner(install.mods, expected_key=str(previous_key))
            except OverlayIntegrityError:
                pass
        elif phase == "staged" and previous_key is None:
            # Something outside the transaction appeared at the target.  It is
            # not ours to rename merely to make rollback convenient.
            raise RecoveryError(
                "an unexpected mods directory appeared before activation; it was not changed"
            )
        else:
            # Only preserve a directory that still proves launcher ownership.
            # Arbitrary user content is never renamed during recovery.  A
            # manifest that is ours but no longer describes the tree still
            # proves ownership, and the tree is preserved with its bytes.
            try:
                _load_owner(install.mods)
            except OverlayIntegrityError:
                pass
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
    heal_notes: list[dict[str, Any]] | None = None,
) -> str:
    """Finish or roll back the one durable activation transaction.

    ``heal_notes`` is appended to when a damaged launcher-owned overlay had to
    be carried aside to make recovery possible, so ``activate_build`` can
    record it in the manifest it is about to write and report it to the player.
    """

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
                try:
                    _load_owner(install.mods, expected_key=str(journal["previous_cache_key"]))
                except OverlayIntegrityError as exc:
                    # The interrupted activation's predecessor is ours but was
                    # modified while the launcher was not looking.  Preserving
                    # it under the transaction's backup name would offer it to
                    # a later rollback as a healthy overlay, so it goes to the
                    # foreign name instead and stops being a restore candidate.
                    note = _move_overlay_aside(install, str(exc))
                    if heal_notes is not None:
                        heal_notes.append(note)
                else:
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
    previous_identity_value = owner.get("previous_identity")
    previous_identity = None
    if previous_identity_value is not None:
        if not isinstance(previous_identity_value, dict):
            raise ValidationError("active overlay previous_identity is not an object")
        previous_identity = SeedIdentity.from_dict(previous_identity_value)
    return activate_build(
        install,
        previous_path,
        process_is_running=process_is_running,
        identity=previous_identity,
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
    # Where this process's output for the session lands (bb-archipelago#171).
    # The early-exit dialog reads its tail from here whoever did the writing.
    log_path: Path | None = None
    # True when the process writes ``log_path`` ITSELF and must keep the console
    # it inherited (bb-archipelago#181). The AP client does: it is handed
    # ``--log-file`` and tees its own output to console and file
    # (clients#425), so the launcher must neither redirect nor pump it -- a pipe
    # here would take away the real console the client-side tee exists to keep.
    # ``log_path`` stays set regardless, because it names the file to READ.
    self_logging: bool = False


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
    handle.write(f"Launcher version: {launcher_version()}\n".encode("utf-8"))
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

    A ``self_logging`` component is left alone entirely: it writes ``log_path``
    itself and keeps the console it inherited (bb-archipelago#181).  Piping it
    would be worse than useless -- it would replace the real console the child's
    own tee exists to preserve, and duplicate every line into the file the child
    is already writing.
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
            if spec.log_path is not None and spec.self_logging:
                # Close before spawning: the client's own append logger retains
                # its console and owns the subsequent SESSION START header.
                spec.log_path.parent.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                with spec.log_path.open("ab") as provenance:
                    provenance.write(
                        f"\nLauncher version: {launcher_version()} | launching {spec.name} | {stamp}\n".encode("utf-8")
                    )
            if spec.log_path is not None and not spec.self_logging:
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
                spec.self_logging,
            )
        )
    return validated
