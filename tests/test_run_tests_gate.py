import contextlib
import io
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from tools import run_tests

FIXTURE = """import unittest

class GateFixture(unittest.TestCase):
    def test_first_required(self):
        self.assertTrue(True)

    def test_second_required(self):
        self.assertTrue(True)

    def test_optional_local_binary(self):
        self.skipTest("reviewed local binary unavailable")
"""


class RunTestsGateTests(unittest.TestCase):
    def _run(self, ledger_rows):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = "test_gate_fixture_" + uuid.uuid4().hex
            (root / f"{module}.py").write_text(FIXTURE, encoding="utf-8")
            ledger = root / "ledger.tsv"
            ledger.write_text(
                "\n".join(row.format(module=module) for row in ledger_rows) + "\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            error = io.StringIO()
            try:
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(
                    error
                ):
                    status = run_tests.main(
                        [
                            "--start-dir",
                            str(root),
                            "--top-level",
                            str(root),
                            "--expect-file",
                            str(ledger),
                        ]
                    )
            finally:
                sys.modules.pop(module, None)
            return status, output.getvalue(), error.getvalue(), module

    def test_exact_environment_dependent_skip_is_accounted(self):
        status, output, _, _ = self._run(
            [
                "max_skips\t0",
                "allow_skip\t{module}.GateFixture.test_optional_local_binary",
            ]
        )
        self.assertEqual(0, status)
        self.assertIn("accounted environment-dependent skips", output)

    def test_unlisted_skip_still_fails_zero_skip_gate(self):
        status, _, error, _ = self._run(["max_skips\t0"])
        self.assertEqual(1, status)
        self.assertIn("1 unaccounted skipped", error)

    def test_allowance_must_name_a_collected_test(self):
        status, _, error, _ = self._run(
            [
                "max_skips\t1",
                "allow_skip\t{module}.GateFixture.test_missing",
            ]
        )
        self.assertEqual(1, status)
        self.assertIn("allow_skip entries did not name collected tests", error)

    def test_module_row_is_an_executed_floor_and_permits_accounted_skip(self):
        status, _, error, _ = self._run(
            [
                "max_skips\t0",
                "allow_skip\t{module}.GateFixture.test_optional_local_binary",
                "module\t{module}\t2",
            ]
        )
        self.assertEqual(0, status, error)

    def test_no_skip_module_cannot_use_optional_skip_allowance(self):
        status, _, error, _ = self._run(
            [
                "max_skips\t0",
                "allow_skip\t{module}.GateFixture.test_optional_local_binary",
                "no_skip_module\t{module}\t2",
            ]
        )
        self.assertEqual(1, status)
        self.assertIn("is AP-required but skipped 1 test", error)


if __name__ == "__main__":
    unittest.main()
