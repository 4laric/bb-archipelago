"""The packaged seed writers may overlap, but cache composition must wait."""

from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path

from bb_launcher.workflow import (
    EnemizerOptions, EnemizerToolchain, LauncherWorkflow, _run_initial_writers,
)
from tests import test_launcher_ui as fixtures


class PackagedFakeToolchain(fixtures.FakeToolchain, EnemizerToolchain):
    def __init__(self, tools: Path):
        fixtures.FakeToolchain.__init__(self)
        tools.mkdir()
        self.event_exe = tools / "BBEventWriter.exe"
        self.param_exe = tools / "BBSuppressionWriter.exe"
        self.event_exe.write_bytes(b"fixture")
        self.param_exe.write_bytes(b"fixture")
        self.barrier = threading.Barrier(3, timeout=3)
        self.caller = threading.get_ident()
        self.worker_threads: list[int] = []

    @property
    def event_writer_executable(self):
        return self.event_exe

    @property
    def parameter_writer_executable(self):
        return self.param_exe

    def _overlap(self, values):
        self.worker_threads.append(threading.get_ident())
        values["progress"]("writer started")
        self.barrier.wait()

    def write_cathedral_event(self, **values):
        self._overlap(values)
        super().write_cathedral_event(**values)

    def write_common_event(self, **values):
        self._overlap(values)
        super().write_common_event(**values)

    def write_seed_weapons(self, **values):
        self._overlap(values)
        super().write_seed_weapons(**values)


class ParallelInitialWriterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LauncherUiWorkflowTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_packaged_writers_overlap_and_cache_waits_for_all_outputs(self):
        fixture = self.fixture
        payload = json.loads(fixture.request.read_text(encoding="utf-8"))
        payload.update({
            "randomize_starting_weapons": True,
            "starting_weapons": {
                "right_hand": [9000000, 5100000, 2000000],
                "left_hand": [6000000, 14000000],
            },
        })
        fixture.request.write_text(json.dumps(payload), encoding="utf-8")
        toolchain = PackagedFakeToolchain(fixture.root / "tools")
        workflow = LauncherWorkflow(fixture.repo, toolchain=toolchain)
        progress_threads: list[int] = []
        prepared = workflow.prepare_seed(
            fixture.settings(enemy_inputs=False), EnemizerOptions(enabled=False),
            progress=lambda _message: progress_threads.append(threading.get_ident()),
        )
        self.assertEqual(3, len(set(toolchain.worker_threads)))
        self.assertNotIn(toolchain.caller, toolchain.worker_threads)
        self.assertEqual({toolchain.caller}, set(progress_threads))
        self.assertEqual(
            b"suppressed-gameparam-starting",
            (prepared.build.path / "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx").read_bytes(),
        )
        self.assertTrue((prepared.build.path / "dvdroot_ps4/event/common.emevd.dcx").is_file())

    def test_failure_joins_other_writer_before_staging_cleanup(self):
        first_finished = threading.Event()
        second_started = threading.Event()

        def failure(report):
            second_started.wait(timeout=2)
            report("failing")
            raise ValueError("writer failed")

        def slow_success(report):
            second_started.set()
            time.sleep(0.1)
            report("finished")
            first_finished.set()

        seen = []
        with self.assertRaisesRegex(ValueError, "writer failed"):
            _run_initial_writers([failure, slow_success], seen.append, parallel=True)
        self.assertTrue(first_finished.is_set())
        self.assertEqual(["failing", "finished"], seen)

    def test_source_toolchain_remains_serial(self):
        toolchain = PackagedFakeToolchain(self.fixture.root / "tools")
        toolchain.event_exe.unlink()
        toolchain.barrier = threading.Barrier(3, timeout=0.01)
        # The fake still writes valid outputs; hitting the overlap barrier
        # would fail if a missing packaged executable accidentally enabled it.
        toolchain._overlap = lambda _values: toolchain.worker_threads.append(threading.get_ident())
        workflow = LauncherWorkflow(self.fixture.repo, toolchain=toolchain)
        workflow.prepare_seed(self.fixture.settings(enemy_inputs=False),
                              EnemizerOptions(enabled=False))
        self.assertEqual([toolchain.caller, toolchain.caller], toolchain.worker_threads)
        self.assertEqual(["cathedral", "common"], [kind for kind, _ in toolchain.event_calls])


if __name__ == "__main__":
    unittest.main()
