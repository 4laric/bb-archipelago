"""Locate launcher resources in a checkout and in a frozen Windows package."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """Return the root containing bundled research and Python resources."""

    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen).resolve()
    return Path(__file__).resolve().parents[1]

def application_root() -> Path:
    """Return the user-visible folder containing the launcher executable."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
