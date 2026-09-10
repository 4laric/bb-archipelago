"""Launcher identity shared by session logs and enemy reports."""

import json
import sys

from .resources import resource_root


def launcher_version() -> str:
    """Preserve the release suffix that numeric Windows versions discard."""
    if not getattr(sys, "frozen", False):
        return "source checkout"
    try:
        metadata = json.loads(
            (resource_root() / "version-metadata.json").read_text(encoding="utf-8")
        )
        value = metadata.get("product_version")
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    except (OSError, ValueError, AttributeError):
        pass
    return "packaged (release metadata unavailable)"
