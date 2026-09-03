"""Generate deterministic Windows version resources for packaged executables."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


PRODUCT_NAME = "Bloodborne Archipelago"
PUBLISHER = "4laric"
COPYRIGHT = "Copyright (c) 2026 4laric"
_VERSION = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?P<suffix>-(?:[0-9A-Za-z-]+\.)*(?P<sequence>\d+))?$"
)


@dataclass(frozen=True)
class ReleaseVersion:
    product_version: str
    file_version: str
    file_version_tuple: tuple[int, int, int, int]
    prerelease: bool


def parse_release_version(raw: str) -> ReleaseVersion:
    value = raw.strip()
    match = _VERSION.fullmatch(value)
    if match is None:
        raise ValueError(
            "release version must look like v0.1.0, v0.1.0-beta.1, "
            "or v0.1.0-signing-canary.2"
        )
    parts = tuple(int(match.group(name)) for name in ("major", "minor", "patch"))
    sequence = int(match.group("sequence") or 0)
    numeric = (*parts, sequence)
    if any(part > 65535 for part in numeric):
        raise ValueError("Windows file-version components must be between 0 and 65535")
    product = value[1:] if value.startswith("v") else value
    return ReleaseVersion(
        product_version=product,
        file_version=".".join(str(part) for part in numeric),
        file_version_tuple=numeric,
        prerelease=match.group("suffix") is not None,
    )


def pyinstaller_version_text(
    version: ReleaseVersion,
    *,
    description: str,
    original_filename: str,
) -> str:
    flags = "0x2" if version.prerelease else "0x0"
    strings = {
        "CompanyName": PUBLISHER,
        "FileDescription": description,
        "FileVersion": version.file_version,
        "InternalName": original_filename,
        "LegalCopyright": COPYRIGHT,
        "OriginalFilename": original_filename,
        "ProductName": PRODUCT_NAME,
        "ProductVersion": version.product_version,
    }
    rows = ",\n".join(
        f"          StringStruct({key!r}, {value!r})" for key, value in strings.items()
    )
    return (
        "# UTF-8\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={version.file_version_tuple!r},\n"
        f"    prodvers={version.file_version_tuple!r},\n"
        "    mask=0x3f,\n"
        f"    flags={flags},\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable('040904B0', [\n"
        f"{rows}\n"
        "      ])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )


def write_metadata(output: Path, raw_version: str) -> dict[str, object]:
    version = parse_release_version(raw_version)
    output.mkdir(parents=True, exist_ok=True)
    resources = {
        "launcher-version.txt": (
            "Bloodborne Archipelago Launcher",
            "BloodborneAPLauncher.exe",
        ),
        "planner-version.txt": (
            "Bloodborne Enemy Randomization Planner",
            "BBEnemizerPlanner.exe",
        ),
    }
    for name, (description, filename) in resources.items():
        (output / name).write_text(
            pyinstaller_version_text(
                version,
                description=description,
                original_filename=filename,
            ),
            encoding="utf-8",
            newline="\n",
        )
    metadata: dict[str, object] = {
        "format": "bb-windows-version-metadata-v1",
        "product_name": PRODUCT_NAME,
        "publisher": PUBLISHER,
        "copyright": COPYRIGHT,
        "product_version": version.product_version,
        "file_version": version.file_version,
        "file_version_tuple": list(version.file_version_tuple),
        "prerelease": version.prerelease,
    }
    (output / "version-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        metadata = write_metadata(args.output, args.release_version)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
