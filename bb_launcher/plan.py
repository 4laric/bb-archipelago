"""Hash-pinned process plan generation (bb-archipelago#65 slice 3).

A packaged player should never hand-write the launch plan: the package already
carries the client, the CE table, and the planner tools, and the plan's
per-machine paths are exactly the kind of tester-authored JSON the launcher
exists to retire. This module builds a `bb-launcher-process-plan-v1` document
from discovered or selected components:

- every executable is pinned by SHA-256 at generation time;
- the AP client's config and ledger are the `{runtime_config}` / `{ledger}`
  placeholders the launcher substitutes at launch, so the plan is portable
  across machines and sessions;
- the client entry carries `--assume-correct-save`, the explicitly unsafe MVP
  mode, because real save identity is still #56 -- generating the plan does
  not change that boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import ValidationError, _write_json_atomic, sha256_file
from .workflow import PROCESS_PLAN_FORMAT, load_process_plan


DEFAULT_SHAD_BUILD = "0.18.0"
# 38281 is MultiServer's default port; 38282 only ever existed here.
DEFAULT_SERVER = "localhost:38281"


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
    ce_executable: Path | str | None = None,
    ce_table: Path | str | None = None,
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
            "arguments": ["CUSA03173"],
        }
    ]
    if ce_executable is not None:
        if ce_table is None:
            raise ValidationError("the CE bridge entry requires the grant table path")
        table = Path(ce_table).expanduser().resolve()
        if not table.is_file() or table.is_symlink():
            raise ValidationError(f"CE grant table is not a regular file: {table}")
        bridge = _pinned_executable(ce_executable, "Cheat Engine executable")
        processes.append(
            {
                "name": "CE bridge",
                "executable": str(bridge["path"]),
                "sha256": bridge["sha256"],
                "arguments": [str(table)],
            }
        )
    processes.append(
        {
            "name": "AP client",
            "executable": str(client["path"]),
            "sha256": client["sha256"],
            "arguments": [server, slot, "{runtime_config}", "{ledger}", "--assume-correct-save"],
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
