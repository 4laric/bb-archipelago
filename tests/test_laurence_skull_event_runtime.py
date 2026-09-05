"""Small lifecycle model for the emitted Laurence event.

The model is deliberately limited to the event-control instructions that can
implicitly set an event's completion flag.  The instruction snapshots below
come from DarkScript's Bloodborne output for the bundled source, and keep this
test independent of a game or emulator.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
import re


PASSWORD = 12401803
WITNESS = 12401898


@dataclass(frozen=True)
class Instruction:
    bank: int
    ident: int
    args: str = ""


# Actual emitted instruction records from the fixed event. The guard records
# are the output of DarkScript 3.6.3 for the source transform and the same
# records are emitted by BBEventWriter's replacements.
ROOT = Path(__file__).resolve().parents[1]


def emitted_instructions() -> tuple[Instruction, ...]:
    """Load the checked-in dump produced by the event compiler/writer path."""
    records = []
    for line in (ROOT / "tests" / "fixtures" / "laurence_emitted_dump.txt").read_text().splitlines():
        match = re.search(r"\[\d+\] (\d+)\[(\d+)\] ?([0-9a-f]*)$", line)
        if match:
            records.append(Instruction(int(match[1]), int(match[2]), match[3]))
    if len(records) != 19:
        raise AssertionError(f"expected 19 emitted records, found {len(records)}")
    return tuple(records)


def run(event: tuple[Instruction, ...], *, client: bool, witness: bool,
        password: bool) -> tuple[str, bool, bool]:
    """Run the control-flow boundary twice, returning outcome and flags."""
    for _pass in range(2):
        guard = event[1]
        multiplayer = event[6]
        if guard.bank == 1003 and guard.ident == 2:
            return "completed", witness, password or not client
        if guard.bank == 3 and guard.ident == 0 and witness:
            return "waiting", witness, password
        if multiplayer.bank == 1003 and multiplayer.ident == 6 and client:
            return "completed", witness, password
        if multiplayer.bank == 3 and multiplayer.ident == 6 and client:
            return "waiting", witness, password
        if len(event) < 4:
            return "waiting", witness, password
        witness = True
        # RestartEvent reaches the next pass; a fixed event then waits.
    return "waiting", witness, password


class LaurenceEventLifecycleTests(unittest.TestCase):
    def test_emitted_guard_records_are_waits_and_tail_restarts(self):
        emitted = emitted_instructions()
        self.assertEqual(emitted[1], Instruction(3, 0, "00000000ea3cbd00"))
        self.assertEqual(emitted[6], Instruction(3, 6, "01010000"))
        self.assertEqual(emitted[17].bank, 2003)
        self.assertEqual(emitted[17].ident, 2)
        self.assertEqual(emitted[18], Instruction(1000, 4, "01000000"))

    def test_restart_and_reload_cannot_complete_password_event(self):
        fixed = emitted_instructions()
        outcome, witness, password = run(fixed, client=False, witness=False, password=False)
        self.assertEqual((outcome, witness, password), ("waiting", True, False))
        outcome, witness, password = run(fixed, client=False, witness=True, password=False)
        self.assertEqual((outcome, witness, password), ("waiting", True, False))

    def test_client_mutant_would_complete_but_fixed_event_waits(self):
        fixed = emitted_instructions()
        outcome, _witness, password = run(fixed, client=True, witness=False, password=False)
        self.assertEqual((outcome, password), ("waiting", False))
        mutant = fixed[:6] + (Instruction(1003, 6, "00010000"),) + fixed[7:]
        outcome, _witness, password = run(mutant, client=True, witness=False, password=False)
        self.assertEqual((outcome, password), ("completed", False))

    def test_bad_witness_end_mutant_completes_on_second_pass(self):
        fixed = emitted_instructions()
        mutant = fixed[:1] + (Instruction(1003, 2, "00010000ea3cbd00"),) + fixed[2:]
        outcome, witness, password = run(mutant, client=False, witness=True, password=False)
        self.assertEqual((outcome, witness, password), ("completed", True, True))

    def test_existing_ap_password_is_preserved(self):
        outcome, witness, password = run(emitted_instructions(), client=False, witness=True, password=True)
        self.assertEqual((outcome, witness, password), ("waiting", True, True))


if __name__ == "__main__":
    unittest.main()
