"""Compare process and install paths using the host filesystem's rules."""

from __future__ import annotations

import ntpath
import os
import posixpath


def canonical_path(path: str) -> str:
    # Qt emits forward slashes on Windows; native process inspection commonly
    # emits backslashes. Do not case-fold on POSIX, where case is significant.
    if os.name == "nt":
        return ntpath.normcase(ntpath.normpath(path))
    return posixpath.normpath(path)


def same_path(left: str, right: str) -> bool:
    return canonical_path(left) == canonical_path(right)
