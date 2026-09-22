"""Install the pinned upstream encounter compiler into the local tool cache."""
from __future__ import annotations

import hashlib
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

from .core import ValidationError

VERSION = '3.6.3'
URL = 'https://github.com/AinTunez/DarkScript3/releases/download/3.6.3/Darkscript3_6_3.zip'
ARCHIVE_SHA256 = '84fe6e2be0e721f3bf86709b973b93c08bac042225e2b9a9854b891f49638fca'
EXECUTABLE_SHA256 = 'c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de'
ARCHIVE_NAME = 'upstream-release.zip'


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = [entry for entry in archive.infolist() if not entry.is_dir()]
    names = set()
    for entry in members:
        path = PurePosixPath(entry.filename)
        if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                or ':' in entry.filename or entry.filename.casefold() in names
                or entry.filename == ARCHIVE_NAME):
            raise ValidationError('Pinned boss compiler archive contains an invalid path.')
        names.add(entry.filename.casefold())
    if 'darkscript3.exe' not in names:
        raise ValidationError('Pinned boss compiler archive has no executable.')
    return members


def verify_boss_compiler(root: Path) -> Path:
    """Verify both executable and resource data against the pinned release."""
    archive_path = root / ARCHIVE_NAME
    if not archive_path.is_file() or _hash(archive_path) != ARCHIVE_SHA256:
        raise ValidationError(f'Boss compiler cache failed verification: {root}')
    with zipfile.ZipFile(archive_path) as archive:
        members = _members(archive)
        for entry in members:
            path = root / entry.filename
            if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve())
                    or path.stat().st_size != entry.file_size
                    or _hash(path) != hashlib.sha256(archive.read(entry)).hexdigest()):
                raise ValidationError(f'Boss compiler resource changed: {entry.filename}')
        expected = {entry.filename for entry in members} | {ARCHIVE_NAME}
        actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
        if actual != expected:
            raise ValidationError('Boss compiler cache contains unlisted files.')
    executable = root / 'DarkScript3.exe'
    if _hash(executable) != EXECUTABLE_SHA256:
        raise ValidationError('Boss compiler executable failed verification.')
    return executable


def ensure_boss_compiler(state_root: Path, progress: Callable[[str], None]) -> Path:
    """Download the original upstream release once; do not redistribute it."""
    tools = Path(state_root) / 'tools'
    destination = tools / ('DarkScript3-' + VERSION)
    if destination.exists():
        return verify_boss_compiler(destination)
    tools.mkdir(parents=True, exist_ok=True)
    progress('Downloading the pinned DarkScript3 compiler for the first boss shuffle build…')
    with tempfile.TemporaryDirectory(prefix='.boss-compiler-', dir=tools) as temporary:
        staged = Path(temporary) / 'compiler'
        staged.mkdir()
        archive_path = staged / ARCHIVE_NAME
        try:
            with urllib.request.urlopen(URL, timeout=60) as response, archive_path.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        except OSError as error:
            raise ValidationError(f'Could not download the boss compiler: {error}') from error
        if _hash(archive_path) != ARCHIVE_SHA256:
            raise ValidationError('Downloaded boss compiler archive failed verification.')
        with zipfile.ZipFile(archive_path) as archive:
            for entry in _members(archive):
                path = staged / entry.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(entry))
        verify_boss_compiler(staged)
        if destination.exists():
            return verify_boss_compiler(destination)
        staged.rename(destination)
    return destination / 'DarkScript3.exe'
