#!/usr/bin/env python3
"""Compile the two owned Cathedral Ward EMEVD edits from a user-owned binary."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.patch_emblem_chokepoint import patch as patch_emblem
from tools.patch_laurence_skull import patch as patch_laurence


FORMAT = "bb-cathedral-emevd-build-v1"
EVENT_FILE = "m24_00_00_00.emevd.dcx"
OUTPUT_RELATIVE_PATH = f"dvdroot_ps4/event/{EVENT_FILE}"
DARKSCRIPT_VERSION = "3.6.3"
DARKSCRIPT_SHA256 = "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de"
# DarkScript 3.6.3 output for the supported CUSA03173 01.09 map event when
# its required common link is supplied. This differs from the historical
# standalone research dump, which was produced without resolving links.
LINKED_SOURCE_SHA256 = "1191bb2d5a67825dfc86a3d76782e1e02aa05e5a4c2dd2d8ffd1b0dfca527c57"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_compiler(executable: Path, mode: str, source: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(executable), "/cmd", f"-{mode}", "-game", "bb", "-indir", str(source),
         "-outdir", str(output), "-force", "-silent"],
        check=True,
    )


def unrelated_events(source: str) -> dict[str, str]:
    source = source.replace("\r\n", "\n")
    chunks = source.split("\n$Event(")
    result: dict[str, str] = {}
    for index, chunk in enumerate(chunks):
        body = chunk if index == 0 else "$Event(" + chunk
        if not body.startswith("$Event("):
            continue
        event_id = body[7:].split(",", 1)[0]
        if event_id not in {"12400760", "12401803"}:
            result[event_id] = body
    return result


def event(source: str, event_id: str) -> str:
    marker = f"$Event({event_id},"
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"event {event_id} is absent after compilation")
    end = source.find("\n$Event(", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def build(executable: Path, source_binary: Path, output_binary: Path, manifest: Path) -> None:
    if sha256(executable) != DARKSCRIPT_SHA256:
        raise ValueError(
            f"unsupported DarkScript3 executable; require {DARKSCRIPT_VERSION} sha256 "
            f"{DARKSCRIPT_SHA256}"
        )
    if source_binary.name.lower() != EVENT_FILE:
        raise ValueError(f"source must be named {EVENT_FILE}")
    if output_binary.exists() or manifest.exists():
        raise FileExistsError("refusing to overwrite output or manifest")

    with tempfile.TemporaryDirectory(prefix="bb-cathedral-emevd-") as raw:
        root = Path(raw)
        original_dir, source_dir, baseline_dir, baseline_verify_dir, compiled_dir, verify_dir = (
            root / "original", root / "source", root / "baseline",
            root / "baseline-verify", root / "compiled", root / "verify"
        )
        original_dir.mkdir()
        shutil.copyfile(source_binary, original_dir / EVENT_FILE)
        # Bloodborne map events link `common`; DarkScript resolves linked
        # binaries from the same input directory while decompiling. Supplying
        # only the target file makes 3.6.3 terminate with an unhandled
        # "Missing linked file common" exception before any patching occurs.
        linked_common = source_binary.parent / "common.emevd.dcx"
        if not linked_common.is_file():
            raise FileNotFoundError(f"required linked common event is absent: {linked_common}")
        shutil.copyfile(linked_common, original_dir / linked_common.name)
        run_compiler(executable, "decompile", original_dir, source_dir)
        source_path = source_dir / f"{EVENT_FILE}.js"
        original_source = source_path.read_bytes()
        if hashlib.sha256(original_source).hexdigest() != LINKED_SOURCE_SHA256:
            raise ValueError("unsupported linked Cathedral event source")
        # DarkScript normalizes two unrelated events during an ordinary
        # compile/decompile cycle. Establish that tool-owned baseline first;
        # the patched round trip must match it everywhere except our events.
        run_compiler(executable, "compile", source_dir, baseline_dir)
        run_compiler(executable, "decompile", baseline_dir, baseline_verify_dir)
        baseline_text = (baseline_verify_dir / f"{EVENT_FILE}.js").read_text(
            encoding="utf-8-sig"
        )
        patched = patch_laurence(
            patch_emblem(original_source, verify_source=False), verify_source=False
        )
        source_path.write_bytes(patched)
        run_compiler(executable, "compile", source_dir, compiled_dir)
        compiled = compiled_dir / EVENT_FILE
        if not compiled.is_file():
            raise ValueError(f"compiler did not produce {EVENT_FILE}")
        run_compiler(executable, "decompile", compiled_dir, verify_dir)
        verified_text = (verify_dir / f"{EVENT_FILE}.js").read_text(encoding="utf-8-sig")
        expected_text = patched.decode("utf-8-sig")
        if event(verified_text, "12401803") != event(expected_text, "12401803"):
            raise ValueError("compiled Laurence event did not round-trip")
        verified_unrelated = unrelated_events(verified_text)
        expected_unrelated = unrelated_events(baseline_text)
        if verified_unrelated != expected_unrelated:
            changed = sorted(
                key for key in verified_unrelated.keys() | expected_unrelated.keys()
                if verified_unrelated.get(key) != expected_unrelated.get(key)
            )
            raise ValueError(f"compile changed unrelated events: {changed}")
        if event(verified_text, "12400760") != event(expected_text, "12400760"):
            raise ValueError("compiled Emblem event did not round-trip")

        output_binary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(compiled, output_binary)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({
            "format": FORMAT,
            "compiler_version": DARKSCRIPT_VERSION,
            "compiler_sha256": sha256(executable),
            "source_sha256": sha256(source_binary),
            "output_sha256": sha256(output_binary),
            "output_relative_path": OUTPUT_RELATIVE_PATH,
            "events": [12400760, 12401803],
            "laurence_witness_flag": 12401898,
            "suppressed_password_flag": 12401803,
        }, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--darkscript", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("refusing to build without --apply")
    build(args.darkscript.resolve(), args.source.resolve(), args.output.resolve(), args.manifest.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
