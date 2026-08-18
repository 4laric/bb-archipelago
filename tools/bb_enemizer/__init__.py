"""Bloodborne enemy-randomizer planning tools.

The package deliberately stops at a swap manifest.  Applying that manifest to
MSBB files is a separate, game-facing boundary so the pure planner remains
host-testable and cannot accidentally modify a game dump.
"""

from .planner import EnemizerConfig, plan_swaps

__all__ = ["EnemizerConfig", "plan_swaps"]
