"""Copy-route-only activation policy for the fork's first release.

The reused external verifier accepts copy, symlink and mixed
installations.  First-release acceptance is Windows standard-user *copy*
activation only, so this module applies the narrower policy on top of a
successful verification: every verified file's ``installation`` entry must
be ``copy``.  Mixed/symlink activation is refused before arming or
connection, with the offending paths named for diagnostics.

Fork provenance is reported to the player as a warning until an exact build
has passed live acceptance.  Provenance reporting does not replace the
receipt, activation fingerprint, or installed-byte integrity checks.
"""

from __future__ import annotations

from typing import Iterable

from .fork_identity import is_supported_fork_build
from .protocol import ProtocolError


def require_copy_activation(files: Iterable[object], *, stage: str) -> None:
    """Refuse any non-copy installation entry before ``stage``.

    ``files`` are :class:`VerifiedExternalFile` records (or any object with
    ``installation`` and ``path`` attributes).  Raises ``ProtocolError``
    naming every offending path.
    """

    offenders = sorted(
        str(getattr(item, "path", "?"))
        for item in files
        if getattr(item, "installation", None) != "copy"
    )
    if offenders:
        raise ProtocolError(
            "activation-route-refused",
            f"first-release play requires copy activation; {len(offenders)} file(s) "
            f"are not copies before {stage}: " + ", ".join(offenders[:8])
            + (f" (+{len(offenders) - 8} more)" if len(offenders) > 8 else ""),
            retryable=False,
            recovery=("reactivate-copy",),
        )


def fork_build_warning(commit: str, executable_sha256: str) -> str | None:
    if not is_supported_fork_build(commit, executable_sha256):
        if not commit or not executable_sha256:
            return "Fork build provenance is unavailable; this build has not been validated."
        return (f"Fork build {commit} (SHA-256 {executable_sha256}) has not been "
                "validated by a live acceptance run.")
    return None
