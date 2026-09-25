"""Validated integrated protocol representation of workflow enemizer choices."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from .protocol import ProtocolError


_BOOLEAN_FIELDS = (
    "enabled", "allow_tier_mixing", "preserve_locomotion", "normalize_scaling",
    "boss_canary", "release_contracts", "release_spawns", "release_chara",
)
_OPTIONAL_TEXT_FIELDS = ("seed", "boss_pool")


def parse_enemizer_options(params: Mapping[str, Any]):
    """Parse the prepare request; integrated launches default to no randomization."""

    from ..workflow import EnemizerOptions

    raw = params.get("enemizer", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ProtocolError("bad-request", "enemizer must be an object")
    allowed = set(_BOOLEAN_FIELDS) | set(_OPTIONAL_TEXT_FIELDS)
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ProtocolError("bad-request", "unknown enemizer option(s): " + ", ".join(unknown))
    values: dict[str, Any] = {name: False for name in _BOOLEAN_FIELDS}
    values["normalize_scaling"] = True
    values.update({name: None for name in _OPTIONAL_TEXT_FIELDS})
    for name in _BOOLEAN_FIELDS:
        if name in raw:
            if not isinstance(raw[name], bool):
                raise ProtocolError("bad-request", f"enemizer.{name} must be a boolean")
            values[name] = raw[name]
    for name in _OPTIONAL_TEXT_FIELDS:
        if name in raw and raw[name] is not None and not isinstance(raw[name], str):
            raise ProtocolError("bad-request", f"enemizer.{name} must be a string or null")
        values[name] = raw.get(name)
    # Player-facing presets own these policies; stale settings must not
    # silently reintroduce controls removed from the launcher.
    values["preserve_locomotion"] = False
    values["boss_pool"] = "reviewed" if values["enabled"] else None
    return EnemizerOptions(**values)


def enemizer_options_record(options: Any) -> dict[str, Any]:
    return asdict(options)
