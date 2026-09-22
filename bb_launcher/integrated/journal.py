"""Activation journal with crash recovery at every mutation boundary.

A multi-file activation is never described as one atomic filesystem swap:
renames within a filesystem may be atomic, cross-filesystem copies are
not.  The coordinator therefore journals outside movable mod folders
(``<state>/integrated/journal/<install-hash>.jsonl``), recording the full
plan -- selected and prior AP packages, third-party conflicts, backup
space and reverse restoration order -- plus the expected before/after
bytes of each committed mutation.

Recovery rules:

- A failed/cancelled build keeps the previous usable package.
- Failed activation restores only files with established ownership and
  expected bytes.  If the user changed a file since interruption, the
  conflict is reported rather than overwritten -- never a whole-install
  reset as generic repair, never touching unrelated mods or base/update
  files.
- A crash after activation does not authorize connection: the backend
  replays verification and recovers persisted arm/process proof, or
  requires a fresh boot when it cannot be established.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..core import ValidationError, _write_json_atomic
from .sessions import install_hash, integrated_root

JOURNAL_FORMAT = "bb-integrated-journal-v1"


@dataclass
class JournalEntry:
    seq: int
    kind: str  # plan | commit | done | abort | recover
    play_id: str
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": JOURNAL_FORMAT,
            "seq": self.seq,
            "kind": self.kind,
            "play_id": self.play_id,
            "detail": dict(self.detail),
            "created_at": self.created_at,
        }


def journal_path(state_root: Path | str, game_root: Path | str) -> Path:
    directory = integrated_root(state_root) / "journal"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"install-{install_hash(game_root)}.jsonl"


def append_entry(state_root: Path | str, game_root: Path | str, kind: str,
                 play_id: str, detail: Mapping[str, Any] | None = None) -> JournalEntry:
    path = journal_path(state_root, game_root)
    seq = 0
    if path.is_file() and not path.is_symlink():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            seq = len([line for line in lines if line.strip()])
        except OSError as exc:
            raise ValidationError(f"could not read activation journal {path}: {exc}") from exc
    entry = JournalEntry(seq=seq + 1, kind=kind, play_id=play_id, detail=dict(detail or {}))
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(entry.as_dict(), sort_keys=True) + "\n")
    return entry


def read_journal(state_root: Path | str, game_root: Path | str) -> list[dict[str, Any]]:
    path = journal_path(state_root, game_root)
    if not path.is_file() or path.is_symlink():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"activation journal is corrupt: {path}") from exc
        if not isinstance(raw, dict) or raw.get("format") != JOURNAL_FORMAT:
            raise ValidationError(f"activation journal has an unsupported entry: {path}")
        entries.append(raw)
    return entries


@dataclass
class ActivationPlan:
    """Reversible plan: every mutation lists its reverse restoration."""

    play_id: str
    package_name: str
    prior_package: str | None
    conflicts: tuple[dict[str, Any], ...]
    mutations: tuple[dict[str, Any], ...]
    backup_space_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "play_id": self.play_id,
            "package_name": self.package_name,
            "prior_package": self.prior_package,
            "conflicts": [dict(item) for item in self.conflicts],
            "mutations": [dict(item) for item in self.mutations],
            "backup_space_bytes": self.backup_space_bytes,
        }


def plan_activation(*, play_id: str, package_name: str, prior_package: str | None,
                    owned_paths: Iterable[Mapping[str, Any]],
                    third_party_collisions: Iterable[Mapping[str, Any]],
                    backup_free_bytes: int) -> ActivationPlan:
    """Plan the entire change before mutating: conflicts, backups, reverse order.

    ``owned_paths`` are AP-owned relative paths with expected ``before`` /
    ``after`` digests; ``third_party_collisions`` name exact conflicting
    third-party mods with a reversible disable plan.  Raises instead of
    planning an ambiguous or destructive change.
    """

    mutations: list[dict[str, Any]] = []
    for record in owned_paths:
        relative = str(record.get("relative", ""))
        before = record.get("before")
        after = record.get("after")
        if not relative or not after:
            raise ValidationError("activation plan mutation needs relative + after digest")
        mutations.append({"relative": relative, "before": before, "after": after,
                          "reverse": {"relative": relative, "restore": before}})
    conflicts = [dict(item) for item in third_party_collisions]
    for conflict in conflicts:
        if not conflict.get("mod") or not conflict.get("path"):
            raise ValidationError("conflict plan needs the exact mod name and path")
        if "reversible_disable" not in conflict:
            raise ValidationError(
                f"conflicting mod {conflict.get('mod')}: refusing without an exact "
                "reversible disable plan"
            )
    needed = sum(int(record.get("size", 0)) for record in owned_paths)
    if backup_free_bytes < needed:
        raise ValidationError(
            f"insufficient backup space: need {needed} bytes, have {backup_free_bytes}"
        )
    # Reverse restoration order is recorded by construction: recovery walks
    # committed mutations back-to-front (see recover_journal).
    return ActivationPlan(play_id=play_id, package_name=package_name,
                          prior_package=prior_package, conflicts=tuple(conflicts),
                          mutations=tuple(mutations), backup_space_bytes=backup_free_bytes)


@dataclass
class RecoveryDecision:
    action: str  # resume | restore-owned | report-conflict | require-fresh-boot
    restored: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    detail: str = ""


def decide_recovery(entries: list[dict[str, Any]],
                    current_bytes: Mapping[str, str | None]) -> RecoveryDecision:
    """Decide recovery from the journal without touching the filesystem.

    ``current_bytes`` maps each planned relative path to its current digest
    (or None when absent).  Files whose current bytes differ from both the
    journaled before *and* after values are user changes: report, never
    overwrite.
    """

    planned: dict[str, dict[str, Any]] = {}
    committed: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("kind") == "plan":
            for mutation in entry.get("detail", {}).get("mutations", []):
                planned[str(mutation.get("relative"))] = dict(mutation)
        elif entry.get("kind") == "commit":
            committed.append(dict(entry.get("detail", {})))
        elif entry.get("kind") in ("done", "abort"):
            committed.clear()
    if not committed and not any(e.get("kind") == "plan" for e in entries):
        return RecoveryDecision(action="resume", detail="no interrupted activation")
    unexpected = sorted(
        relative for relative in planned
        if relative in current_bytes
        and current_bytes[relative] != planned[relative].get("before")
        and current_bytes[relative] != planned[relative].get("after")
    )
    if unexpected:
        return RecoveryDecision(
            action="report-conflict",
            conflicts=tuple(unexpected),
            detail="user changed file(s) since interruption; refusing to overwrite: "
                   + ", ".join(unexpected),
        )
    # Reverse-order restoration of committed mutations only.
    committed_paths = [str(item.get("relative")) for item in committed if item.get("relative")]
    if committed_paths and all(
        current_bytes.get(relative) == planned.get(relative, {}).get("after")
        for relative in committed_paths
    ):
        return RecoveryDecision(action="resume", detail="interrupted tail can resume")
    if committed_paths:
        return RecoveryDecision(
            action="restore-owned",
            restored=tuple(reversed(committed_paths)),
            detail="restore committed AP-owned files in reverse order",
        )
    return RecoveryDecision(action="require-fresh-boot",
                            detail="activation state cannot be established")


def journal_fingerprint(material: Mapping[str, Any]) -> str:
    from ..core import canonical_json

    return hashlib.sha256(canonical_json(dict(material))).hexdigest()
