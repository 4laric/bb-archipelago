"""Non-blocking fork build validation diagnostics.

Fork provenance is reported to the player as a warning until an exact build
has passed live acceptance. Provenance reporting does not replace receipt,
activation fingerprint, or installed-byte integrity checks.
"""

from __future__ import annotations

from .fork_identity import is_supported_fork_build


def fork_build_warning(commit: str, executable_sha256: str) -> str | None:
    if not is_supported_fork_build(commit, executable_sha256):
        if not commit or not executable_sha256:
            return "Fork build provenance is unavailable; this build has not been validated."
        return (f"Fork build {commit} (SHA-256 {executable_sha256}) has not been "
                "validated by a live acceptance run.")
    return None
