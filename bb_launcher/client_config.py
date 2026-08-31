"""Launcher-authored native client runtime configuration (bb-archipelago#65).

The native AP client takes its runtime config and durable ledger as command
line paths.  Until now both were tester-authored JSON, which is exactly the
cross-machine onboarding failure the launcher exists to retire: a hand-copied
config can embed a developer's paths, point ``installed_gameparam`` at a build
artifact instead of the binder the game actually loads, or reuse another
seed's ledger.

This module derives all three launch-time paths from verified launcher state:

- the session directory is keyed by AP seed and slot, so switching cached
  seeds can never reuse the wrong ledger, while rebuilding the same seed and
  slot reuses the same one;
- ``installed_gameparam`` names the *active overlay's* binder, re-hashed
  against the activation ownership manifest before it is written;
- the file is emitted as BOM-free UTF-8 (the native client rejects a BOM at
  line 1 column 1) through the same atomic write the manifests use.

Process plans stay portable by naming placeholders (``{runtime_config}``,
``{ledger}``, ``{bridge_root}``) instead of per-machine paths; the launcher
substitutes them at launch and refuses any placeholder it cannot satisfy.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .core import (
    SUPPRESSION_PATH,
    GameInstall,
    ValidationError,
    _load_owner,
    _require_sha256,
    _write_json_atomic,
    sha256_file,
)


# Same separator the client's receive ledger uses for its seed/slot key, so
# the launcher's session naming and the ledger's slot namespacing agree about
# what "one AP session" means.
SESSION_KEY_SEPARATOR = "\x1f"
CLIENT_LOG_NAME = "client.log"
# shadPS4's own captured stdout/stderr, beside the client's, so an emulator
# boot crash carries evidence the way a client refusal does
# (bb-archipelago#175).  Distinct from ``shad_log``, the emulator's internal
# log file that the client config points at.
SHAD_LOG_NAME = "shadps4.log"
CLIENT_HEALTH_NAME = "client-health.json"

# Placeholders that only a randomized launch can satisfy: they name files the
# client runtime configuration writer produces.
CLIENT_LOG_PLACEHOLDER = "client_log"
# The argument that tells a component to write its own session log. Its presence
# in a plan entry is what marks that entry self-logging, so the launcher leaves
# its output alone (bb-archipelago#181, clients#425).
CLIENT_LOG_FLAG = "--log-file"
CLIENT_PLACEHOLDERS = ("runtime_config", "ledger", "bridge_root", CLIENT_LOG_PLACEHOLDER)
# The game directory shadPS4 is told to boot (bb-archipelago#177). Unlike the
# client placeholders this one is satisfiable on a vanilla launch too, because
# the game folder comes from the launcher settings, not from the AP session.
GAME_PATH_PLACEHOLDER = "game_path"
KNOWN_PLACEHOLDERS = CLIENT_PLACEHOLDERS + (GAME_PATH_PLACEHOLDER,)
_PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class ClientRuntimePaths:
    """The three launch-time paths the native client and bridge consume."""

    session: Path
    config: Path
    ledger: Path
    bridge_root: Path
    # Where the AP client's own stdout/stderr is appended, beside the ledger,
    # so Open Diagnostics picks it up (bb-archipelago#171).
    client_log: Path
    # Where shadPS4's own stdout/stderr is appended for this session.
    shad_process_log: Path
    client_health: Path


def default_state_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "BloodborneArchipelago"


def default_shad_log() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".roaming"
    return root / "shadPS4" / "log" / "shad_log.txt"


def session_key(seed: str, slot: str) -> str:
    if not seed.strip() or not slot.strip():
        raise ValidationError("client session requires a non-empty seed and slot")
    return hashlib.sha256(f"{seed}{SESSION_KEY_SEPARATOR}{slot}".encode("utf-8")).hexdigest()


def session_paths(state_root: Path | str, *, seed: str, slot: str) -> ClientRuntimePaths:
    root = Path(state_root).expanduser().resolve()
    session = root / "sessions" / session_key(seed, slot)
    return ClientRuntimePaths(
        session=session,
        config=session / "runtime-config.json",
        ledger=session / "ledger.json",
        bridge_root=root / "bridge",
        client_log=session / CLIENT_LOG_NAME,
        shad_process_log=session / SHAD_LOG_NAME,
        client_health=session / CLIENT_HEALTH_NAME,
    )


def write_client_runtime_config(
    state_root: Path | str,
    *,
    seed: str,
    slot: str,
    install: GameInstall,
    owner: Mapping[str, Any],
    suppression_manifest: Path | None,
    shad_log: Path | None,
    auto_upgrade: bool = False,
    auto_equip: bool = False,
) -> ClientRuntimePaths:
    """Write the native client's runtime config for the *active* overlay.

    ``owner`` must be the ownership manifest returned by the activation that
    just completed; the active overlay is re-verified against it before any
    path is written, so the config can never point the client at an overlay
    the launcher did not just prove.
    """

    owner_key = _require_sha256(str(owner.get("cache_key", "")), "activated overlay cache_key")
    active = _load_owner(install.mods, expected_key=owner_key)
    installed = install.mods.joinpath(*PurePosixPath(SUPPRESSION_PATH).parts)
    expected_hash = _require_sha256(
        str(active["suppression"]["sha256"]), "active overlay suppression witness"
    )
    if sha256_file(installed) != expected_hash:
        raise ValidationError(
            f"active overlay binder {installed} does not match its ownership manifest"
        )
    manifest_path = None
    if suppression_manifest is not None:
        manifest_path = Path(suppression_manifest).expanduser().resolve()
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValidationError(f"suppression manifest is not a regular file: {manifest_path}")
    log_path = None
    if shad_log is not None:
        log_path = str(Path(shad_log).expanduser().resolve())

    paths = session_paths(state_root, seed=seed, slot=slot)
    # Exactly the native client's RuntimeConfig shape.  Locations, items, and
    # the seed-owned suppression requirement are deliberately empty/default:
    # the client replaces them from slot_data when it connects, and local
    # configuration cannot weaken the seed's terms.  expected_save_identity
    # stays unset here; --assume-correct-save overrides it explicitly.
    config = {
        "bridge_root": str(paths.bridge_root),
        "shad_log": log_path,
        "locations": [],
        "items": {},
        "auto_upgrade": bool(auto_upgrade),
        "auto_equip": bool(auto_equip),
        "expected_save_identity": None,
        "suppression_manifest": None if manifest_path is None else str(manifest_path),
        "installed_gameparam": str(installed),
        "location_check_debounce": 3,
        "mock_set_flags": [],
        "goal_location": None,
    }
    # BOM-free UTF-8, atomically published: the native client rejects a BOM.
    _write_json_atomic(paths.config, config)
    # The ledger file itself is intentionally not created: the client treats a
    # missing ledger as an empty one, and an empty file would not parse.
    return paths


def substitute_plan_arguments(
    arguments: Sequence[str],
    paths: ClientRuntimePaths | None,
    *,
    game_path: Path | str | None = None,
) -> tuple[str, ...]:
    """Resolve launch-time placeholders in one process argument list.

    Placeholders keep the plan file portable: the machine-specific paths are
    filled in at launch from the launcher's own settings, so a plan can be
    copied between machines and still boot the right game.

    With ``paths=None`` (a vanilla launch) no client placeholder can be
    satisfied, so any client placeholder at all fails closed.  ``{game_path}``
    is separate: it resolves on every launch, vanilla included, and only fails
    closed when the caller had no game installation to name.  Anything
    unrecognized is refused -- a typo'd token must never reach a process as a
    literal path.
    """

    tokens = {}
    if paths is not None:
        tokens = {
            "runtime_config": str(paths.config),
            "ledger": str(paths.ledger),
            "bridge_root": str(paths.bridge_root),
            # Where the client writes its own session log (bb-archipelago#181):
            # a generated plan passes it as ``--log-file {client_log}`` and the
            # client tees console and file itself (clients#425).
            "client_log": str(paths.client_log),
        }
    if game_path is not None:
        tokens[GAME_PATH_PLACEHOLDER] = str(game_path)
    resolved: list[str] = []
    for argument in arguments:
        for name, value in tokens.items():
            argument = argument.replace("{" + name + "}", value)
        remaining = sorted(set(_PLACEHOLDER_PATTERN.findall(argument)))
        if remaining:
            if GAME_PATH_PLACEHOLDER in remaining and game_path is None:
                raise ValidationError(
                    "this launch has no game installation to substitute for the "
                    "{game_path} placeholder; set the shadPS4 game folder in the "
                    "launcher settings"
                )
            if paths is None and all(name in CLIENT_PLACEHOLDERS for name in remaining):
                raise ValidationError(
                    "a vanilla launch has no client runtime configuration; remove the "
                    + ", ".join(f"{{{name}}}" for name in remaining)
                    + " placeholder(s) or the client process from this plan"
                )
            raise ValidationError(
                "process plan argument uses unknown placeholder(s): "
                + ", ".join(f"{{{name}}}" for name in remaining)
            )
        resolved.append(argument)
    return tuple(resolved)
