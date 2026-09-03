"""Resolve the player's chosen seed file to one Bloodborne request document.

Archipelago generation emits a single ``AP_<seed>.zip`` holding every slot's
output file, and hosts hand players that zip.  Before bb-archipelago#194 the
launcher took only the extracted ``*.bbseed.json``, so a Bloodborne player had
an unzip-and-pick step no other Archipelago game asks for -- and picking the
wrong member connects them as somebody else's slot.

Everything in here funnels a *chosen path* (a loose request, or a zip) down to
one request file on disk.  Selection is by the request payload's own
``player_name``, the same identity the Doctor validates against the player-name
field; filenames are never parsed for it.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import ValidationError


REQUEST_SUFFIXES = (".bbseed.json", ".bbenemizer.json")
ARCHIVE_SUFFIXES = (".zip", ".apbb")
# Where an extracted member lands: launcher-owned, content-keyed, and stable
# across restarts.  A temp directory would vanish under the seed cache and the
# Doctor, both of which key off the request file's identity.
EXTRACTION_DIRECTORY = "seed-requests"


@dataclass(frozen=True)
class ResolvedRequest:
    """One request document on disk, plus where it came from."""

    path: Path
    # None when the player picked a loose request file directly.
    archive: Path | None = None
    member: str | None = None
    player_name: str | None = None

    @property
    def from_archive(self) -> bool:
        return self.archive is not None

    def describe(self) -> str:
        if self.archive is None:
            return str(self.path)
        return f"{self.member} in {self.archive}"


def is_request_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in REQUEST_SUFFIXES)


def looks_like_archive(path: Path | str) -> bool:
    return Path(path).name.lower().endswith(ARCHIVE_SUFFIXES)


def _request_formats() -> tuple[str, ...]:
    # Imported lazily so this module can be imported from workflow's own
    # callers without a cycle through workflow.
    from .workflow import REQUEST_FORMATS

    return REQUEST_FORMATS


def _payload_player_name(raw: bytes) -> str | None:
    """The slot name of a Bloodborne request, or None if this isn't one."""
    try:
        value: Any = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("format") not in _request_formats():
        return None
    name = value.get("player_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def archive_slots(archive: Path) -> tuple[tuple[str, str], ...]:
    """Every Bloodborne request in the zip, as ``(member, player_name)``.

    A member whose payload is not a Bloodborne request -- another game's
    output, a spoiler log -- is not a slot, whatever it is named.
    """
    try:
        with zipfile.ZipFile(archive) as bundle:
            found: list[tuple[str, str]] = []
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                raw = bundle.read(info)
                if is_request_name(info.filename):
                    name = _payload_player_name(raw)
                    if name is not None:
                        found.append((info.filename, name))
                elif info.filename.lower().endswith(".apbb"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(raw)) as player_file:
                            for nested in player_file.infolist():
                                if nested.is_dir() or not is_request_name(nested.filename):
                                    continue
                                name = _payload_player_name(player_file.read(nested))
                                if name is not None:
                                    found.append((f"{info.filename}!{nested.filename}", name))
                    except zipfile.BadZipFile:
                        continue
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"could not read the AP seed zip {archive}: {exc}") from exc
    return tuple(sorted(found))


def _select(archive: Path, slots: tuple[tuple[str, str], ...], wanted: str) -> tuple[str, str]:
    names = ", ".join(sorted({name for _member, name in slots}))
    if not slots:
        raise ValidationError(
            f"{archive.name} has no Bloodborne slot: nothing inside it is a "
            "Bloodborne seed request (*.bbseed.json; older seeds "
            "*.bbenemizer.json). Check you were sent the right seed, and that "
            "the multiworld actually has a Bloodborne player"
        )
    if not wanted:
        if len(slots) == 1:
            return slots[0]
        raise ValidationError(
            f"{archive.name} has {len(slots)} Bloodborne slots ({names}); enter your "
            "AP player name so the launcher picks yours -- guessing would connect "
            "you as another player and steal their checks"
        )
    matches = [entry for entry in slots if entry[1] == wanted]
    if not matches:
        raise ValidationError(
            f"{archive.name} has no Bloodborne slot named {wanted!r}; it holds: {names}"
        )
    if len(matches) > 1:
        members = ", ".join(member for member, _name in matches)
        raise ValidationError(
            f"{archive.name} holds more than one request for slot {wanted!r} "
            f"({members}); the launcher will not guess between them"
        )
    return matches[0]


def _extraction_target(archive: Path, member: str, state_root: Path) -> Path:
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(member.encode("utf-8"))
    return state_root / EXTRACTION_DIRECTORY / digest.hexdigest()[:16] / Path(member.rsplit("!", 1)[-1]).name


def resolve_request_source(
    path: Path | str,
    *,
    player_name: str = "",
    state_root: Path | None = None,
) -> ResolvedRequest:
    """Turn the chosen seed file into one request document on disk.

    A loose ``*.bbseed.json`` (or legacy ``*.bbenemizer.json``) is returned
    untouched -- this is exactly the pre-#194 path.  An ``AP_*.zip`` is
    searched for Bloodborne slots, one is selected by ``player_name``, and that
    member is extracted under ``state_root`` at a content-keyed location, so
    re-selecting the same zip reuses the same file instead of writing a new one.
    """
    source = Path(path).expanduser()
    if not looks_like_archive(source):
        return ResolvedRequest(source)
    if not source.is_file():
        raise ValidationError(f"the AP seed zip {source} does not exist")
    if state_root is None:
        from .client_config import default_state_root

        state_root = default_state_root()
    slots = archive_slots(source)
    member, slot = _select(source, slots, player_name.strip())
    target = _extraction_target(source, member, Path(state_root).expanduser())
    if not target.is_file():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(source) as bundle:
                if "!" in member:
                    outer, inner = member.split("!", 1)
                    with zipfile.ZipFile(io.BytesIO(bundle.read(outer))) as player_file:
                        payload = player_file.read(inner)
                else:
                    payload = bundle.read(member)
            # Write beside, then replace: a half-written request must never be
            # mistaken for a cached one on the next run.
            staging = target.with_name(target.name + ".partial")
            staging.write_bytes(payload)
            staging.replace(target)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValidationError(f"could not extract {member} from {source}: {exc}") from exc
    return ResolvedRequest(target, archive=source, member=member, player_name=slot)


def archive_player_name(path: Path | str) -> str | None:
    """The slot name a zip would resolve to on its own, or None if ambiguous.

    Used to prefill the player-name field and to filter auto-discovered zip
    candidates; never raises, because both callers are best-effort.
    """
    source = Path(path).expanduser()
    try:
        slots = archive_slots(source)
    except ValidationError:
        return None
    if len(slots) != 1:
        return None
    return slots[0][1]
