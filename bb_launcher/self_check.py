"""Packaging self-check: the launcher consuming its own files, no game needed.

Run from the frozen package (``BloodborneAPLauncher.exe --self-check report.json``)
this proves what CI could not see before beta 2 shipped: that every apworld
table the launcher imports is bundled, that the seed contract can be built,
and that every native tool the seed build calls is next to the executable.
It never touches game files or the network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .resources import application_root, resource_root
from .workflow import EnemizerToolchain

BUNDLED_TOOLS = (
    "BBEnemizerWriter.exe",
    "BBSuppressionWriter.exe",
    "BBEventWriter.exe",
    "MSBBMiner.exe",
    "bb-ap-client.exe",
)


def run_self_check(report: Path | None, *, require_bundled_tools: bool | None = None) -> int:
    """Return 0 when everything the packaged launcher needs is present.

    ``require_bundled_tools`` defaults to "am I frozen"; a source checkout has
    no native executables beside it and is not expected to.
    """
    frozen = bool(getattr(sys, "frozen", False))
    if require_bundled_tools is None:
        require_bundled_tools = frozen
    result: dict[str, Any] = {
        "format": "bb-launcher-self-check-v1",
        "frozen": frozen,
        "resource_root": str(resource_root()),
        "application_root": str(application_root()),
        "problems": [],
    }

    try:
        from worlds.bloodborne import (
            ALL_NETWORK_LOCATIONS, FULL_POOL_ITEM_KEYS, STARTING_TOOL_KEYS,
            build_runtime_slot_data,
        )
        from worlds.bloodborne.attire import ATTIRE_CATALOG
        from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS
        from worlds.bloodborne.data import ATTIRE_ITEM_KEYS, UNCANNY_ITEM_KEYS
        from worlds.bloodborne.fixed_locations import FIXED_LOCATIONS
        from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS

        widest = FULL_POOL_ITEM_KEYS | UNCANNY_ITEM_KEYS | ATTIRE_ITEM_KEYS | STARTING_TOOL_KEYS
        slot_data = build_runtime_slot_data(widest)
        result["world"] = {
            "fixed_locations": len(FIXED_LOCATIONS),
            "network_locations": len(ALL_NETWORK_LOCATIONS),
            "attire_catalog": len(ATTIRE_CATALOG),
            "category8_awards": len(CATEGORY8_AWARDS),
            "item_bindings": len(ITEM_BINDINGS),
            "runtime_items": len(slot_data["runtime_items"]),
            "runtime_locations": len(slot_data["runtime_locations"]),
            "sustain_item": slot_data.get("sustain_item") is not None,
        }
        for name, count in result["world"].items():
            if count in (0, False):
                result["problems"].append(f"world table {name} is empty")
    except Exception as error:  # noqa: BLE001 - the report is the point
        result["problems"].append(f"apworld import failed: {error!r}")

    toolchain = EnemizerToolchain(resource_root(), app_root=application_root())
    tools_dir = toolchain.app_root / "tools"
    result["tools"] = {
        name: (tools_dir / name).is_file() for name in BUNDLED_TOOLS
    }
    result["tools"]["BBEnemizerPlanner/BBEnemizerPlanner.exe"] = toolchain.planner_executable.is_file()
    if require_bundled_tools:
        for name, present in result["tools"].items():
            if not present:
                result["problems"].append(f"bundled tool missing: {name}")

    result["ok"] = not result["problems"]
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0 if result["ok"] else 1
