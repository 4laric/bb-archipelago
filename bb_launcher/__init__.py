"""Bloodborne Archipelago launcher core.

The package deliberately keeps overlay mutation out of the UI layer.  Both the
eventual desktop application and the checked-in CLI call the same fail-closed
cache and activation primitives.
"""

from .core import (
    APP_VERSION,
    MODS_DIR_NAME,
    SERIAL,
    BuildResult,
    ConflictError,
    DiscoveryError,
    GameInstall,
    LaunchError,
    LauncherError,
    ProcessSpec,
    RecoveryError,
    SeedCache,
    SeedIdentity,
    ValidationError,
    activate_build,
    deactivate_overlay,
    discover_game_install,
    discover_shad_executable,
    launch_processes,
    recover_activation,
    restore_previous_build,
    validate_processes,
)

__all__ = [
    "APP_VERSION",
    "MODS_DIR_NAME",
    "SERIAL",
    "BuildResult",
    "ConflictError",
    "DiscoveryError",
    "GameInstall",
    "LaunchError",
    "LauncherError",
    "ProcessSpec",
    "RecoveryError",
    "SeedCache",
    "SeedIdentity",
    "ValidationError",
    "activate_build",
    "deactivate_overlay",
    "discover_game_install",
    "discover_shad_executable",
    "launch_processes",
    "recover_activation",
    "restore_previous_build",
    "validate_processes",
]
