"""Zip-safe resource reads for the shipped world.

The apworld is a zip: once Archipelago imports the world through zipimport,
no data file exists on the filesystem, so resource reads must go through
importlib.resources rather than filesystem paths. Every data file the world
reads at import time comes through here.
"""

from __future__ import annotations

from importlib.resources import files as _files


def read_resource_text(name: str) -> str:
    """Read a data file shipped inside the world package as text."""
    return _files(__package__).joinpath(name).read_text(encoding="utf-8")
