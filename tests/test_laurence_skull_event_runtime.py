"""Bounded interpreter for the emitted Laurence altar event.

The fixture is a BBEventWriter dump whose replacement records are checked
against DarkScript 3.6.3 output. This model decodes instruction arguments and
intentionally supports only the control flow used by this event.
"""

from __future__ import annotations

import re
import struct
import unittest
from dataclasses import dataclass
from pathlib import Path


PASSWORD = 12401803
WITNESS = 12401898
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Instruction:
    bank: int
    ident: int
    args: bytes


def emitted_instructions() -> tuple[Instruction, ...]:
    records = []
    text = (ROOT / "tests/fixtures/laurence_emitted_dump.txt").read_text()
    for line in text.splitlines():
        match = re.search(r"\[\d+\] (\d+)\[(\d+)\] ?([0-9a-f]*)$", line)
        if match:
            records.append(Instruction(int(match[1]), int(match[2]), bytes.fromhex(match[3])))
    if len(records) != 19:
        raise AssertionError(f"expected 19 emitted records, found {len(records)}")
    return tuple(records)


def run(event: tuple[Instruction, ...], *, client: bool, witness: bool,
        password: bool, action: bool = True) -> tuple[str, bool, bool]:
    """Interpret the reviewed event shape for two activations.

    The multiplayer predicate's binary schema is not published in this repo,
    so this intentionally recognizes the exact DarkScript-reviewed records
    rather than assigning speculative names to each byte.
    """
    flags = {WITNESS: witness, PASSWORD: password, 12401800: True}
    for _activation in range(2):
        groups: dict[int, bool] = {}
        restarted = False
        for instruction in event:
            key, args = (instruction.bank, instruction.ident), instruction.args
            if key == (1003, 2):  # EndIfEventFlag
                end_type, state, flag_type, _pad, flag = struct.unpack("<BBBBi", args)
                value = flags.get(PASSWORD if flag_type == 1 else flag, False)
                if value == bool(state):
                    if end_type == 0:
                        flags[PASSWORD] = True
                        return "completed", flags[WITNESS], flags[PASSWORD]
                    restarted = True
                    break
            elif key == (1003, 6):  # reviewed vanilla EndIf(client)
                if args != bytes.fromhex("00010000"):
                    raise AssertionError(f"unexpected multiplayer end: {args.hex()}")
                if client:
                    flags[PASSWORD] = True
                    return "completed", flags[WITNESS], flags[PASSWORD]
            elif key == (3, 0):  # IfEventFlag
                group, state, flag_type, _pad, flag = struct.unpack("<bBBBi", args)
                value = flags.get(PASSWORD if flag_type == 1 else flag, False)
                groups[group] = value == bool(state)
                if group == 0 and not groups[group]:
                    return "waiting", flags[WITNESS], flags[PASSWORD]
            elif key == (3, 6):  # IfMultiplayerState(AND_01, Client)
                group, multiplayer_state, _padding = struct.unpack("<bbH", args)
                groups[group] = client == (multiplayer_state == 1)
            elif key == (0, 0):  # IfConditionGroup
                result, desired_state, target, _padding = struct.unpack("<bBbB", args)
                if result != 0:
                    raise AssertionError(f"unexpected result group: {result}")
                if target == 1:
                    ready = groups.get(1, False) == bool(desired_state)
                elif target == 2:
                    # The vanilla action-button pair defines group 2
                    # immediately before this reviewed MAIN wait.
                    ready = action == bool(desired_state)
                else:
                    raise AssertionError(f"unexpected condition wait: {args.hex()}")
                if not ready:
                    return "waiting", flags[WITNESS], flags[PASSWORD]
            elif key == (2003, 2):  # SetEventFlag
                flag, state = struct.unpack("<iBxxx", args)
                flags[flag] = bool(state)
            elif key == (1000, 4):  # EndUnconditionally
                (end_type,) = struct.unpack("<Bxxx", args)
                if end_type == 1:
                    restarted = True
                    break
                flags[PASSWORD] = True
                return "completed", flags[WITNESS], flags[PASSWORD]
        if not restarted:
            flags[PASSWORD] = True
            return "completed", flags[WITNESS], flags[PASSWORD]
    return "waiting", flags[WITNESS], flags[PASSWORD]


class LaurenceEventLifecycleTests(unittest.TestCase):
    def test_emitted_client_guard_is_a_complete_wait(self):
        emitted = emitted_instructions()
        self.assertEqual(emitted[1], Instruction(3, 0, bytes.fromhex("00000000ea3cbd00")))
        self.assertEqual(emitted[6], Instruction(3, 6, bytes.fromhex("01010000")))
        self.assertEqual(emitted[7], Instruction(0, 0, bytes.fromhex("00000100")))
        self.assertEqual(emitted[18], Instruction(1000, 4, bytes.fromhex("01000000")))

    def test_restart_and_reload_cannot_complete_password_event(self):
        fixed = emitted_instructions()
        self.assertEqual(run(fixed, client=False, witness=False, password=False),
                         ("waiting", True, False))
        self.assertEqual(run(fixed, client=False, witness=True, password=False),
                         ("waiting", True, False))

    def test_client_waits_before_the_interaction(self):
        self.assertEqual(run(emitted_instructions(), client=True, witness=False,
                             password=False), ("waiting", False, False))

    def test_host_without_action_waits_before_recording_witness(self):
        self.assertEqual(run(emitted_instructions(), client=False, witness=False,
                             password=False, action=False),
                         ("waiting", False, False))

    def test_missing_main_wait_mutant_reaches_interaction(self):
        fixed = emitted_instructions()
        mutant = fixed[:7] + fixed[8:]
        self.assertEqual(run(mutant, client=True, witness=False, password=False),
                         ("waiting", True, False))

    def test_old_client_end_mutant_completes_password_for_guest(self):
        fixed = emitted_instructions()
        mutant = fixed[:6] + (
            Instruction(1003, 6, bytes.fromhex("00010000")),
        ) + fixed[8:]
        self.assertEqual(run(mutant, client=True, witness=False, password=False),
                         ("completed", False, True))

    def test_bad_witness_end_mutant_completes_password(self):
        fixed = emitted_instructions()
        mutant = fixed[:1] + (
            Instruction(1003, 2, bytes.fromhex("00010000ea3cbd00")),
        ) + fixed[2:]
        self.assertEqual(run(mutant, client=False, witness=True, password=False),
                         ("completed", True, True))

    def test_existing_ap_password_is_preserved(self):
        self.assertEqual(run(emitted_instructions(), client=False, witness=True,
                             password=True), ("waiting", True, True))


if __name__ == "__main__":
    unittest.main()
