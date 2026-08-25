from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bb_launcher.cli import main as cli_main
from bb_launcher.core import ValidationError, sha256_file
from bb_launcher.plan import (
    DEFAULT_SERVER,
    DEFAULT_SHAD_BUILD,
    generate_process_plan,
    write_process_plan,
)
from bb_launcher.workflow import PROCESS_PLAN_FORMAT, load_process_plan


def make_executable(root: Path, name: str, payload: bytes) -> Path:
    path = root / name
    path.write_bytes(payload)
    return path


def make_request(root: Path, *, player_name: str = "Alice", runtime_build: str = "r1") -> Path:
    path = root / "request.json"
    path.write_text(
        json.dumps(
            {
                "format": "bb-seed-request-v1",
                "player": 1,
                "player_name": player_name,
                "runtime_build": runtime_build,
                "world_version": "0.1.0",
                "enemizer_seed": "seed-1",
                "suppression": {"plan_sha256": "0" * 64},
            }
        ),
        encoding="utf-8",
    )
    return path


class PlanGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.shad = make_executable(self.root, "shadPS4.exe", b"shad")
        self.client = make_executable(self.root, "bb-ap-client.exe", b"client")
        self.ce = make_executable(self.root, "cheatengine.exe", b"ce")
        self.table = make_executable(self.root, "grant.CT", b"table")

    def test_generated_plan_is_pinned_portable_and_loadable(self) -> None:
        document = generate_process_plan(
            shad_executable=self.shad,
            client_executable=self.client,
            ce_executable=self.ce,
            ce_table=self.table,
            slot="Alice",
            runtime_build="r1",
        )
        self.assertEqual(document["format"], PROCESS_PLAN_FORMAT)
        self.assertEqual(document["shad_build"], DEFAULT_SHAD_BUILD)
        names = [record["name"] for record in document["processes"]]
        self.assertEqual(names, ["shadPS4", "CE bridge", "AP client"])
        by_name = {record["name"]: record for record in document["processes"]}
        self.assertEqual(by_name["shadPS4"]["sha256"], sha256_file(self.shad))
        self.assertEqual(by_name["CE bridge"]["sha256"], sha256_file(self.ce))
        self.assertEqual(by_name["AP client"]["sha256"], sha256_file(self.client))
        self.assertEqual(by_name["shadPS4"]["arguments"], ["CUSA03173"])
        self.assertEqual(by_name["CE bridge"]["arguments"], [str(self.table.resolve())])
        client_args = by_name["AP client"]["arguments"]
        self.assertEqual(client_args[0], DEFAULT_SERVER)
        self.assertEqual(client_args[1], "Alice")
        self.assertIn("{runtime_config}", client_args)
        self.assertIn("{ledger}", client_args)
        self.assertIn("--assume-correct-save", client_args)
        self.assertEqual(client_args[2:], ["{runtime_config}", "{ledger}", "--assume-correct-save"])
        loaded = load_process_plan(write_process_plan(self.root / "plan.json", document))
        self.assertEqual([spec.name for spec in loaded.processes], names)

    def test_generation_refuses_bad_components(self) -> None:
        missing = self.root / "absent.exe"
        with self.assertRaises(ValidationError):
            generate_process_plan(
                shad_executable=missing,
                client_executable=self.client,
                slot="Alice",
                runtime_build="r1",
            )
        with self.assertRaises(ValidationError):
            generate_process_plan(
                shad_executable=self.shad,
                client_executable=self.client,
                ce_executable=self.ce,
                slot="Alice",
                runtime_build="r1",
            )
        with self.assertRaises(ValidationError):
            generate_process_plan(
                shad_executable=self.shad,
                client_executable=self.client,
                server="bad server",
                slot="Alice",
                runtime_build="r1",
            )
        with self.assertRaises(ValidationError):
            generate_process_plan(
                shad_executable=self.shad,
                client_executable=self.client,
                slot=" ",
                runtime_build="r1",
            )

    def test_write_never_clobbers_without_force(self) -> None:
        document = generate_process_plan(
            shad_executable=self.shad,
            client_executable=self.client,
            slot="Alice",
            runtime_build="r1",
        )
        output = write_process_plan(self.root / "plan.json", document)
        first = output.read_bytes()
        with self.assertRaises(ValidationError):
            write_process_plan(output, document)
        self.assertEqual(output.read_bytes(), first)
        rewritten = write_process_plan(output, document, force=True)
        self.assertEqual(rewritten, output)
        loaded = load_process_plan(output)
        self.assertEqual(loaded.runtime_build, "r1")

    def test_cli_plan_derives_identity_from_ap_request(self) -> None:
        request = make_request(self.root, player_name="Bob", runtime_build="r9")
        output = self.root / "plan.json"
        code = cli_main(
            [
                "plan",
                "--output", str(output),
                "--shad", str(self.shad),
                "--client", str(self.client),
                "--ap-request", str(request),
            ]
        )
        self.assertEqual(code, 0)
        document = json.loads(output.read_text(encoding="utf-8-sig"))
        self.assertEqual(document["runtime_build"], "r9")
        client_args = document["processes"][-1]["arguments"]
        self.assertEqual(client_args[1], "Bob")
        conflicting = self.root / "conflict.json"
        code = cli_main(
            [
                "plan",
                "--output", str(conflicting),
                "--shad", str(self.shad),
                "--client", str(self.client),
                "--ap-request", str(request),
                "--slot", "Carol",
            ]
        )
        self.assertEqual(code, 1)
        self.assertFalse(conflicting.exists())


if __name__ == "__main__":
    unittest.main()
