#!/usr/bin/env python3
"""Compile and verify the owned category-8 additions to common.emevd."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from tools.build_cathedral_emevd import (
    DARKSCRIPT_SHA256, DARKSCRIPT_VERSION, event, run_compiler, sha256,
)
from tools.patch_category8_awards import EVENT_ID, patch
from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS


FORMAT = "bb-common-emevd-build-v1"
EVENT_FILE = "common.emevd.dcx"
OUTPUT_RELATIVE_PATH = f"dvdroot_ps4/event/{EVENT_FILE}"


def instructions(event_source: str) -> str:
    """Reduce an event body to what the compiler preserves.

    DarkScript3 discards ``//`` comments and trailing whitespace when it
    decompiles, so a round-trip comparison must do the same or a commented
    source event can never match its own compiled form.
    """
    kept = []
    for line in event_source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept)


def build(executable: Path, source_binary: Path, output_binary: Path, manifest: Path) -> None:
    if sha256(executable) != DARKSCRIPT_SHA256:
        raise ValueError(f"unsupported DarkScript3 executable; require {DARKSCRIPT_VERSION}")
    if source_binary.name.lower() != EVENT_FILE:
        raise ValueError(f"source must be named {EVENT_FILE}")
    if output_binary.exists() or manifest.exists():
        raise FileExistsError("refusing to overwrite output or manifest")
    with tempfile.TemporaryDirectory(prefix="bb-common-emevd-") as raw:
        root = Path(raw)
        original, source, compiled, verify = (
            root / "original", root / "source", root / "compiled", root / "verify"
        )
        original.mkdir()
        shutil.copyfile(source_binary, original / EVENT_FILE)
        run_compiler(executable, "decompile", original, source)
        source_path = source / f"{EVENT_FILE}.js"
        expected = patch(source_path.read_bytes())
        source_path.write_bytes(expected)
        run_compiler(executable, "compile", source, compiled)
        product = compiled / EVENT_FILE
        run_compiler(executable, "decompile", compiled, verify)
        verified = (verify / f"{EVENT_FILE}.js").read_text(encoding="utf-8-sig")
        expected_text = expected.decode("utf-8-sig")
        verify_owned_events(expected_text, verified)
        constructor = event(verified, "0")
        for index, row in enumerate(CATEGORY8_AWARDS):
            initializer = (
                f"$InitializeEvent(0, {EVENT_ID + index}, {row.token_goods_id}, "
                f"{row.item_lot_id}, {row.ack_flag});"
            )
            if constructor.count(initializer) != 1:
                raise ValueError(
                    f"compiled common constructor did not retain exactly one {initializer}"
                )
        output_binary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(product, output_binary)
        manifest.write_text(json.dumps({
            "format": FORMAT,
            "compiler_version": DARKSCRIPT_VERSION,
            "compiler_sha256": sha256(executable),
            "source_sha256": sha256(source_binary),
            "output_sha256": sha256(output_binary),
            "output_relative_path": OUTPUT_RELATIVE_PATH,
            "event": EVENT_ID,
            "rows": [row.__dict__ for row in CATEGORY8_AWARDS],
        }, indent=2) + "\n", encoding="utf-8")


def verify_owned_events(expected: str, actual: str) -> None:
    """Check every isolated row, including non-pilot rows such as #362's row 15."""
    for index, _ in enumerate(CATEGORY8_AWARDS):
        event_id = str(EVENT_ID + index)
        if instructions(event(actual, event_id)) != instructions(event(expected, event_id)):
            raise ValueError(f"compiled category-8 event {event_id} did not round-trip")
