"""Copy-route-only activation policy for the fork's first release.

The reused external verifier accepts copy, symlink and mixed
installations.  First-release acceptance is Windows standard-user *copy*
activation only, so this module applies the narrower policy on top of a
successful verification: every verified file's ``installation`` entry must
be ``copy``.  Mixed/symlink activation is refused before arming or
connection, with the offending paths named for diagnostics.

Executable provenance is equally strict: the existing exact-build pins
are never loosened to accept arbitrary forks.  A fork build connects only
when its (commit, executable sha256) pair is an explicit member of the
fork compatibility set.
"""

from __future__ import annotations

from typing import Iterable

from ..core import ValidationError
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


def require_fork_provenance(commit: str, executable_sha256: str) -> None:
    if not is_supported_fork_build(commit, executable_sha256):
        raise ProtocolError(
            "unsupported-build",
            "this fork build is not in the explicitly accepted compatibility set; "
            "arbitrary forks are never accepted by loosening executable pins",
            retryable=False,
            recovery=("select-supported-build",),
        )


def as_validation_error(error: ProtocolError) -> ValidationError:
    return ValidationError(f"{error.code}: {error.detail}")
