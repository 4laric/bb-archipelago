"""Hash-pinned process plan generation (bb-archipelago#65 slice 3).

A packaged player should never hand-write the launch plan: the package already
carries the client and the planner tools, and the plan's
per-machine paths are exactly the kind of tester-authored JSON the launcher
exists to retire. This module builds a `bb-launcher-process-plan-v1` document
from discovered or selected components:

- every executable is pinned by SHA-256 at generation time;
- the AP client's config and ledger are the `{runtime_config}` / `{ledger}`
  placeholders the launcher substitutes at launch, so the plan is portable
  across machines and sessions;
- shadPS4 is told to boot the game by PATH, through the same mechanism: the
  `{game_path}` placeholder resolves at launch to the game directory the
  launcher settings already name (bb-archipelago#177). The bare `CUSA03173`
  game ID it used to pass could only be resolved against shadPS4's own
  `install_dirs` config, which is empty on any never-configured emulator copy,
  so a correct launcher setup still died with "Game ID or file path not
  found". Passing the directory keeps shadPS4's `CUSA03173-patch` and
  `CUSA03173-mods` overlay resolution intact: the emulator derives both from
  the booted eboot's own parent folder, not from its library config;
- the client entry carries `--assume-correct-save`, the explicitly unsafe MVP
  mode, because real save identity is still #56 -- generating the plan does
  not change that boundary.

A generated plan has exactly two children: shadPS4 and the AP client
(bb-archipelago#153). Item delivery is the client's own native path, which is
its default; the Cheat Engine bridge is no longer part of the packaged shape.
It survives only as a host-directed fallback (`--delivery=ce-bridge`, Cheat
Engine opened by hand), because the bridge can mark a backlog of items as
delivered when none arrived and lose them for the run (#163). A dead lane the
launcher keeps arming is a lane players end up on silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .client_config import CLIENT_LOG_FLAG, CLIENT_LOG_PLACEHOLDER, GAME_PATH_PLACEHOLDER
from .core import ValidationError, _write_json_atomic, sha256_file
from .workflow import PROCESS_PLAN_FORMAT, load_process_plan


DEFAULT_SHAD_BUILD = "0.18.0"
# What a generated plan hands shadPS4 as its positional game argument. shadPS4
# 0.18's CLI takes "Game path or ID" positionally and only falls back to its
# library config when the argument is not an existing path, so a real directory
# needs no in-emulator setup at all.
GAME_PATH_ARGUMENT = "{" + GAME_PATH_PLACEHOLDER + "}"
# 38281 is MultiServer's default port; 38282 only ever existed here.
DEFAULT_SERVER = "localhost:38281"
# Where the AP client writes its own session log. Resolved at launch to this
# session's ``client.log``, the same file the early-exit dialog reads
# (bb-archipelago#181).
CLIENT_LOG_ARGUMENT = "{" + CLIENT_LOG_PLACEHOLDER + "}"


def _pinned_executable(raw: Path | str, label: str) -> dict[str, Any]:
    path = Path(raw).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise ValidationError(f"{label} is not a regular file: {path}")
    return {"path": path, "sha256": sha256_file(path)}


def generate_process_plan(
    *,
    shad_executable: Path | str,
    runtime_build: str,
    slot: str,
    client_executable: Path | str,
    shad_build: str = DEFAULT_SHAD_BUILD,
    server: str = DEFAULT_SERVER,
) -> dict[str, Any]:
    """Build the plan document. Pure I/O: reads only the pinned executables."""

    if not runtime_build.strip():
        raise ValidationError("process plan generation requires a runtime build")
    if not shad_build.strip():
        raise ValidationError("process plan generation requires a shadPS4 build")
    if not slot.strip():
        raise ValidationError("process plan generation requires the AP slot name")
    if not server.strip() or any(character.isspace() for character in server):
        raise ValidationError(f"invalid AP server address: {server!r}")
    shad = _pinned_executable(shad_executable, "shadPS4 executable")
    client = _pinned_executable(client_executable, "AP client executable")
    processes: list[dict[str, Any]] = [
        {
            "name": "shadPS4",
            "executable": str(shad["path"]),
            "sha256": shad["sha256"],
            "arguments": [GAME_PATH_ARGUMENT],
        }
    ]
    processes.append(
        {
            "name": "AP client",
            "executable": str(client["path"]),
            "sha256": client["sha256"],
            "arguments": [
                server,
                slot,
                "{runtime_config}",
                "{ledger}",
                "--assume-correct-save",
                # The client tees its own output to the console AND this file
                # (clients#425): the console stays live for the player while
                # client.log keeps the evidence a startup refusal needs. The
                # launcher does not redirect this entry -- see
                # `resolve_process_plan` (bb-archipelago#181).
                CLIENT_LOG_FLAG,
                CLIENT_LOG_ARGUMENT,
            ],
        }
    )
    return {
        "format": PROCESS_PLAN_FORMAT,
        "shad_build": shad_build,
        "runtime_build": runtime_build,
        "processes": processes,
    }


def write_process_plan(path: Path | str, plan: dict[str, Any], *, force: bool = False) -> Path:
    """Publish a generated plan atomically, then prove it loads.

    An existing plan is never overwritten without `force`: a player may have
    hand-validated their launch arguments, and regeneration must not silently
    replace them.
    """

    destination = Path(path).expanduser().resolve()
    if destination.exists() and not force:
        raise ValidationError(
            f"process plan already exists: {destination} (use force to regenerate it)"
        )
    _write_json_atomic(destination, plan)
    loaded = load_process_plan(destination)
    if len(loaded.processes) != len(plan["processes"]):
        raise ValidationError(f"generated process plan {destination} did not round-trip")
    return destination
