"""Read-only BBLauncher folder suggestion and setup diagnostics."""
from __future__ import annotations

import os
from pathlib import Path

from .core import MODS_DIR_NAME, SERIAL
from .external import ACTIVE_MODS_DIR_NAME, _inactive_mods_directory


INACTIVE_MODS_RELATIVE = Path("BBLauncher") / "Mods"


def suggest_mods_directory(executable: Path) -> Path:
    """Return BBLauncher's conventional inactive mod library beside its app."""

    candidate = Path(executable)
    try:
        candidate = candidate.expanduser()
    except (OSError, RuntimeError, ValueError):
        pass
    return candidate.parent / INACTIVE_MODS_RELATIVE


def _absolute(path: Path) -> Path | None:
    try:
        return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _same_or_below(path: Path, root: Path) -> bool:
    path_parts = tuple(part.casefold() for part in path.parts)
    root_parts = tuple(part.casefold() for part in root.parts)
    return len(path_parts) >= len(root_parts) and path_parts[:len(root_parts)] == root_parts


def _inside_active_tree(path: Path) -> bool:
    active = ACTIVE_MODS_DIR_NAME.casefold()
    return any(part.casefold() == active for part in path.parts)


def _game_overlay(game_root: Path) -> Path:
    if game_root.name.casefold() == SERIAL.casefold():
        return game_root.with_name(MODS_DIR_NAME)
    return game_root / MODS_DIR_NAME


def setup_problem(
    executable: Path | None,
    mods: Path | None,
    game_root: Path | None,
) -> str | None:
    """Describe the first BBLauncher setup problem without changing the filesystem."""

    if executable is None:
        return (
            "Choose BB_Launcher.exe first. Its inactive mod library is the "
            "BBLauncher\\Mods folder beside the app."
        )
    app = _absolute(executable)
    if app is None:
        return "The BBLauncher app path is invalid. Choose BB_Launcher.exe again."
    try:
        app_ok = app.is_file() and not app.is_symlink()
    except (OSError, RuntimeError, ValueError):
        app_ok = False
    if not app_ok:
        return f"BBLauncher app was not found at {app}. Choose the BB_Launcher.exe file."

    expected = suggest_mods_directory(app)
    if mods is None:
        return (
            f"Choose BBLauncher's inactive mod library: {expected}. "
            f"Do not choose the game's {MODS_DIR_NAME} overlay."
        )
    library = _absolute(mods)
    if library is None:
        return f"The mod library path is invalid. Choose BBLauncher's inactive Mods folder: {expected}."

    if _inside_active_tree(library):
        return (
            "That folder is BBLauncher's active package area. Choose the inactive "
            f"mod library instead: {expected}."
        )

    overlay = None
    if game_root is not None:
        game = _absolute(game_root)
        if game is not None:
            overlay = _game_overlay(game)
    if (library.name.casefold() == MODS_DIR_NAME.casefold()
            or (overlay is not None and
                (_same_or_below(library, overlay) or _same_or_below(overlay, library)))):
        return (
            f"That folder is the game's live {MODS_DIR_NAME} overlay. BBLauncher writes "
            f"there during activation; choose its inactive mod library instead: {expected}."
        )

    try:
        _inactive_mods_directory(library)
        library_ok = True
    except (OSError, RuntimeError, ValueError):
        library_ok = False
    if not library_ok:
        return (
            f"The inactive mod library is unavailable or unsafe at {library}. Choose {expected}; "
            "check that BBLauncher and its inactive Mods folder are regular directories."
        )
    return None
