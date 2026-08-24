"""Everything about the Cheat-Engine-free delivery prototype that is testable
without the game.

What these tests can and cannot establish: they prove the payload assembler
reproduces a frozen byte encoding, that the AOB matcher implements Cheat
Engine's byte-string semantics, that the descriptor encoder lays out the 24-byte
object at the validated offsets, and that the queue/verify/retry machine makes
the same transitions the CE harness makes. They prove nothing about whether the
guest process accepts any of it. That is the owner's checklist in
docs/SPEC-client-without-cheat-engine.md.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from bb_native_delivery import aob, contract, payload  # noqa: E402
from bb_native_delivery.delivery import (  # noqa: E402
    BLOOD_VIAL_NORMALIZED,
    EMPTY_SLOT,
    MAX_HYDRATION_VERIFY_POLLS,
    MAX_VERIFY_POLLS,
    MIN_ABSENT_POLLS,
    DeliveryError,
    DurableState,
    GrantCommand,
    GrantSession,
    SlotRecord,
    StackView,
)
from bb_native_delivery.descriptor import (  # noqa: E402
    DESCRIPTOR_SIZE,
    DescriptorError,
    ItemGrantDescriptor,
    goods_descriptor_ids,
    uses_persistent_source,
)
from bb_native_delivery.guest import entry_address  # noqa: E402
from bb_native_delivery.process import logged_eboot_base  # noqa: E402
from bb_native_delivery.process import install, AttachError  # noqa: E402
from bb_native_delivery.threadcontrol import (  # noqa: E402
    DEFAULT_ATTEMPT_BUDGET,
    FakeThreadController,
    InstallAborted,
    InstallOutcome,
    PatchWindow,
    install_detours_atomically,
)

# The Archipelago CI tier copies tests/ and tools/ into a checkout of Archipelago
# but not tables/, so the table sits one level up there. Same fallback as
# tests/test_grant_harness_contract.py.
TABLE_NAME = "Bloodborne-native-item-grant-auto-v2.CT"
TABLE = next(
    path
    for path in (ROOT / "tables" / TABLE_NAME, ROOT.parent / "tables" / TABLE_NAME)
    if path.exists()
)
CONTRACT_ROOT = next(
    root for root in (ROOT, ROOT.parent) if contract.contract_path(root).exists()
)


# The bytes the assembler emits. VALIDATED 2026-08-24 against a live shadPS4
# process: the CE table was loaded and armed, both caves read back with
# tools/compare_ce_payload.py, and the only differences were MR-form vs
# RM-form encodings of three reg-to-reg movs (mov rdi,r13 x2; mov rsi,rsp;
# mov esi,eax) -- semantically identical. The assembler was switched to CE's
# RM-form encoding so the shipped blob is byte-identical to the reference.
FROZEN_CONSUME_CAVE = (
    "4C892D09040000833DF2030000000F84BB000000833DE5030000020F8468000000C705D503000000"
    "0000008B052F04000089042448C7442408000000008B052D04000089442410C74424140000000049"
    "8BFD488BF48B050504000025000000F03D000000800F8507000000488D35EE0300008B158C030000"
    "48B8A0A04D0100000000FFD0E936000000C7056D03000000000000498BFD8B35980300008B156203"
    "0000488D0D870300004C8B05880300004531C948B8A0944D0100000000FFD0890543030000C7053D"
    "030000010000004489E04883C428E9A1DA3FFC"
)
FROZEN_HEARTBEAT_CAVE = (
    "833D49020000000F855C000000833DEC010000000F844F00000048833DEE010000000F8441000000"
    "488B3DE1010000488D350A02000048B8C0A24D0100000000FFD083F8FF0F841E000000488B3DBE01"
    "00008BF031D2488D0DEF01000048B8A0944D0100000000FFD04881C4E8070000E9142CB2FC"
)


class PayloadAssemblyTests(unittest.TestCase):
    def test_the_caves_assemble_to_the_frozen_encoding(self):
        self.assertEqual(FROZEN_CONSUME_CAVE, payload.consume_cave().data.hex().upper())
        self.assertEqual(FROZEN_HEARTBEAT_CAVE, payload.heartbeat_cave().data.hex().upper())

    def test_every_call_target_in_the_ce_template_is_reached_by_the_payload(self):
        """The cross-check against the source of truth: the three absolute call
        targets the CE table names are exactly the payload's relocations."""
        text = TABLE.read_text(encoding="utf-8")
        for rva in (payload.ITEM_GRANT_RVA, payload.QUANTITY_DELTA_RVA, payload.FIND_SLOT_RVA):
            self.assertIn(f"mov rax,80{rva:X}", text)
        targets = sorted(
            reloc.target_rva
            for blob in payload.blobs()
            for reloc in blob.relocations
        )
        self.assertEqual(
            sorted([payload.ITEM_GRANT_RVA, payload.QUANTITY_DELTA_RVA,
                    payload.QUANTITY_DELTA_RVA, payload.FIND_SLOT_RVA]),
            targets,
        )

    def test_the_blob_is_position_independent_apart_from_the_relocations(self):
        """Two different eboot bases must differ only in the relocated quadwords."""
        blob = payload.consume_cave()
        low = blob.relocated(0x0574_0000)
        high = blob.relocated(0x8_0000_0000)
        differing = {index for index, (a, b) in enumerate(zip(low, high)) if a != b}
        expected = {
            reloc.offset + step for reloc in blob.relocations for step in range(8)
        }
        self.assertTrue(differing, "the relocation must actually change bytes")
        self.assertTrue(differing <= expected, sorted(differing - expected))

    def test_relocation_writes_the_absolute_routine_address(self):
        blob = payload.consume_cave()
        relocated = blob.relocated(0x8_0000_0000)
        reloc = blob.relocations[0]
        value = int.from_bytes(relocated[reloc.offset : reloc.offset + 8], "little")
        self.assertEqual(0x8_0000_0000 + payload.ITEM_GRANT_RVA, value)

    def test_the_detours_cover_the_original_bytes_exactly(self):
        for detour, original, cave in (
            (payload.consume_detour(), payload.CONSUME_ORIGINAL, payload.CONSUME_CAVE_RVA),
            (payload.heartbeat_detour(), payload.HEARTBEAT_ORIGINAL, payload.HEARTBEAT_CAVE_RVA),
        ):
            self.assertEqual(len(original), len(detour.data))
            self.assertEqual(0xE9, detour.data[0])
            self.assertEqual(b"\x90" * (len(original) - 5), detour.data[5:])
            displacement = int.from_bytes(detour.data[1:5], "little", signed=True)
            self.assertEqual(cave, detour.rva + 5 + displacement)

    def test_the_displaced_original_is_re_executed_at_the_end_of_each_cave(self):
        """A detour that eats instructions without replaying them is a crash."""
        self.assertIn(payload.CONSUME_ORIGINAL, payload.consume_cave().data)
        self.assertIn(payload.HEARTBEAT_ORIGINAL, payload.heartbeat_cave().data)

    def test_the_state_region_seeds_the_slot_index_and_heartbeat_descriptor(self):
        data = payload.state_region().data
        self.assertEqual(0x70, len(data))
        self.assertEqual(EMPTY_SLOT, int.from_bytes(data[0x34:0x38], "little"))
        self.assertEqual(0xB0000384, int.from_bytes(data[0x40:0x44], "little"))
        self.assertEqual(0x40000384, int.from_bytes(data[0x44:0x48], "little"))

    def test_the_data_region_never_overlaps_the_caves(self):
        spans = [(blob.rva, blob.rva + len(blob.data)) for blob in payload.blobs()]
        for index, (start, end) in enumerate(spans):
            for other_start, other_end in spans[index + 1 :]:
                self.assertFalse(start < other_end and other_start < end,
                                 f"{spans} overlap at {start:#x}")

    def test_install_order_writes_the_caves_before_the_detours(self):
        names = [blob.name for blob in payload.blobs()]
        self.assertLess(names.index("consume_cave"), names.index("consume_detour"))
        self.assertLess(names.index("heartbeat_cave"), names.index("heartbeat_detour"))


class AobTests(unittest.TestCase):
    def test_the_ce_assert_strings_parse_and_match_their_originals(self):
        pattern = aob.parse("44 89 E0 48 83 C4 28")
        self.assertEqual(7, len(pattern))
        self.assertTrue(pattern.matches(payload.CONSUME_ORIGINAL))
        self.assertFalse(pattern.matches(payload.HEARTBEAT_ORIGINAL))

    def test_a_one_byte_difference_fails_closed(self):
        pattern = aob.parse("48 81 C4 E8 07 00 00")
        mutated = bytearray(payload.HEARTBEAT_ORIGINAL)
        mutated[3] ^= 0xFF
        self.assertFalse(pattern.matches(bytes(mutated)))

    def test_wildcards_match_any_byte_and_are_reported(self):
        pattern = aob.parse("44 ?? E0")
        self.assertTrue(pattern.has_wildcards)
        self.assertTrue(pattern.matches(bytes((0x44, 0x00, 0xE0))))
        self.assertTrue(pattern.matches(bytes((0x44, 0xFF, 0xE0))))
        self.assertFalse(pattern.matches(bytes((0x45, 0xFF, 0xE0))))

    def test_short_input_never_matches(self):
        self.assertFalse(aob.parse("44 89 E0").matches(b"\x44\x89"))

    def test_the_consume_signature_locates_the_hook_and_only_the_hook(self):
        from bb_native_delivery.process import CONSUME_SIGNATURE

        pattern = aob.parse(CONSUME_SIGNATURE)
        haystack = bytearray(b"\x00" * 64)
        needle = bytes.fromhex("4489E04883C4285B415C415D415E415F")
        haystack[20:20 + len(needle)] = needle
        self.assertEqual([20], pattern.find_all(bytes(haystack)))

    def test_malformed_patterns_raise_rather_than_matching_loosely(self):
        for text in ("", "4", "ZZ", "44 8"):
            with self.assertRaises(aob.PatternError):
                aob.parse(text)

    def test_round_trip_through_text_is_stable(self):
        text = "44 89 ?? 48"
        self.assertEqual(text.replace("?? ", "?? "), aob.parse(text).to_text())


class DescriptorTests(unittest.TestCase):
    def test_the_validated_pebble_descriptor_lands_at_the_recorded_offsets(self):
        encoded = ItemGrantDescriptor(0xB00004CE, 0x400004CE).encode()
        self.assertEqual(0xB00004CE, int.from_bytes(encoded[0x00:0x04], "little"))
        self.assertEqual(0, int.from_bytes(encoded[0x08:0x10], "little"))
        self.assertEqual(0x400004CE, int.from_bytes(encoded[0x10:0x14], "little"))
        self.assertEqual(32, len(encoded))

    def test_decode_reads_back_only_the_three_meaningful_fields(self):
        original = ItemGrantDescriptor(0x806C5660, 0x07100000)
        self.assertEqual(original, ItemGrantDescriptor.decode(original.encode()))

    def test_decode_refuses_a_short_buffer(self):
        with self.assertRaises(DescriptorError):
            ItemGrantDescriptor.decode(b"\x00" * (DESCRIPTOR_SIZE - 1))

    def test_the_goods_formula_reproduces_the_validated_canaries(self):
        for goods_id, raw, normalized in (
            (0x4CE, 0xB00004CE, 0x400004CE),  # Pebble
            (0x384, 0xB0000384, 0x40000384),  # Quicksilver Bullets
            (0x3E8, 0xB00003E8, 0x400003E8),  # Blood Vials
        ):
            self.assertEqual((raw, normalized), goods_descriptor_ids(goods_id))

    def test_the_source_branch_matches_the_caves_category_test(self):
        # The cave does `and eax,F0000000 / cmp eax,80000000`.
        self.assertTrue(uses_persistent_source(0x806C5660))   # Saw Spear, equipment
        self.assertFalse(uses_persistent_source(0xB00004CE))  # Pebble, goods
        self.assertFalse(uses_persistent_source(0xF00003E8))  # the invalid ?ItemInfo? record

    def test_out_of_range_ids_are_refused(self):
        with self.assertRaises(DescriptorError):
            ItemGrantDescriptor(0x1_0000_0000, 0x400004CE)


class FakeRuntime:
    """A scriptable stand-in for the guest process."""

    def __init__(self, stacks=None, ready=True, slot_records=None):
        self.stacks = dict(stacks or {})
        self.ready = ready
        self.slot_records = dict(slot_records or {})
        self.queued = []
        self.writes = []
        self.done = False
        self.result = EMPTY_SLOT
        self.pending = False

    def inventory_ready(self):
        return self.ready

    def find_stack(self, normalized_id):
        return self.stacks.get(normalized_id, StackView(quantity=0, exists=False))

    def read_slot_record(self, slot):
        return self.slot_records.get(slot, SlotRecord(None, None, None))

    def write_quantity(self, address, value):
        self.writes.append((address, value))
        for key, stack in self.stacks.items():
            if stack.quantity_address == address:
                self.stacks[key] = StackView(value, True, stack.slot, address)
        return True

    def request_pending(self):
        return self.pending

    def queue_native(self, descriptor, quantity, slot, quantity_address, manual_trigger):
        self.queued.append((descriptor, quantity, slot, quantity_address, manual_trigger))

    def native_done(self):
        return self.done

    def native_result(self):
        return self.result

    def clear_request(self):
        self.pending = False


PEBBLE_RAW = 0xB00004CE
PEBBLE = 0x400004CE


def _command(**overrides):
    fields = dict(raw_id=PEBBLE_RAW, normalized_id=PEBBLE, quantity=1, tag="ap-42")
    fields.update(overrides)
    return GrantCommand(**fields)


class DeliveryStateMachineTests(unittest.TestCase):
    def test_an_existing_stack_takes_the_direct_write_path(self):
        runtime = FakeRuntime({PEBBLE: StackView(3, True, 79, 0x2080_67C08)})
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=3))
        self.assertEqual("completed", session.poll())
        self.assertEqual([(0x2080_67C08, 4)], runtime.writes)
        self.assertEqual(0, len(runtime.queued), "an existing stack must not call ItemGrant")

    def test_a_direct_write_that_does_not_stick_fails_instead_of_acknowledging(self):
        runtime = FakeRuntime({PEBBLE: StackView(3, True, 79, 0x2080_67C08)})
        runtime.write_quantity = lambda address, value: False
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=3))
        self.assertEqual("write_error", session.poll())

    def test_an_absent_stack_waits_out_the_hydration_grace_before_inserting(self):
        runtime = FakeRuntime()
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=0))
        for _ in range(MIN_ABSENT_POLLS - 1):
            self.assertEqual("awaiting_inventory", session.poll())
        self.assertEqual(0, len(runtime.queued), "inserted before hydration could be ruled out")
        self.assertEqual("executing", session.poll())
        self.assertEqual(1, len(runtime.queued))
        descriptor, quantity, _slot, _address, manual = runtime.queued[0]
        self.assertEqual(ItemGrantDescriptor(PEBBLE_RAW, PEBBLE), descriptor)
        self.assertEqual(1, quantity)
        self.assertFalse(manual)

    def test_an_uncached_inventory_pointer_retains_the_command(self):
        session = GrantSession(runtime=FakeRuntime(ready=False))
        session.submit(_command(expected_before=0))
        self.assertEqual("awaiting_inventory", session.poll())
        self.assertIn("use one bullet once", session.state.detail)

    def test_absent_blood_vial_insertion_is_refused(self):
        runtime = FakeRuntime()
        session = GrantSession(runtime=runtime)
        session.submit(GrantCommand(0xB00003E8, BLOOD_VIAL_NORMALIZED, 1, "vial", expected_before=0))
        for _ in range(MIN_ABSENT_POLLS - 1):
            session.poll()
        self.assertEqual("failed", session.poll())
        self.assertEqual(0, len(runtime.queued), "a refused Vial must never reach ItemGrant")
        self.assertIn("Blood Vial", session.state.detail)

    def test_a_changed_baseline_is_a_mismatch_not_a_grant(self):
        runtime = FakeRuntime({PEBBLE: StackView(9, True, 79, 0x2080_67C08)})
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=3))
        self.assertEqual("quantity_mismatch", session.poll())
        self.assertEqual(0, len(runtime.writes), "a mismatched baseline must not be written through")

    def test_a_quantity_already_at_the_target_recovers_instead_of_granting_twice(self):
        runtime = FakeRuntime({PEBBLE: StackView(4, True, 79, 0x2080_67C08)})
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=3))
        self.assertEqual("recovered_complete", session.poll())
        self.assertEqual(0, len(runtime.writes), "recovery must not grant a second time")

    def test_a_durable_prior_baseline_survives_a_restart(self):
        """The replay-recovery case: the process died between the grant and the
        acknowledgement, so the live quantity already includes the item."""
        runtime = FakeRuntime({PEBBLE: StackView(4, True, 79, 0x2080_67C08)})
        prior = DurableState(status="executing", tag="ap-42", expected_before=3, expected_after=4)
        session = GrantSession(runtime=runtime, prior=prior)
        session.submit(_command(expected_before=None))
        self.assertEqual("recovered_complete", session.poll())

    def test_a_prior_for_a_different_tag_does_not_rebase_the_sample(self):
        runtime = FakeRuntime({PEBBLE: StackView(4, True, 79, 0x2080_67C08)})
        prior = DurableState(status="executing", tag="some-other-item",
                             expected_before=3, expected_after=4)
        session = GrantSession(runtime=runtime, prior=prior)
        session.submit(_command(expected_before=None))
        self.assertEqual("completed", session.poll())
        self.assertEqual([(0x2080_67C08, 5)], runtime.writes)

    def test_verification_accepts_the_slot_the_native_call_reported(self):
        """findItem returns the FIRST matching stack, which is the wrong witness
        when the insert landed in a stack the scan cannot see."""
        runtime = FakeRuntime(
            stacks={PEBBLE: StackView(10, True, 3, 0x1000)},
            slot_records={78: SlotRecord(PEBBLE, 1, 0x2000)},
        )
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=0))
        session._active = True
        session._expected_before = 0
        runtime.done, runtime.result = True, 78
        self.assertEqual("completed", session.poll())

    def test_a_contradicted_verify_exhausts_the_fast_budget_and_fails(self):
        runtime = FakeRuntime(
            stacks={PEBBLE: StackView(0, True, 3, 0x1000)},
            slot_records={78: SlotRecord(0xDEADBEEF, 0, 0x2000)},
        )
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=0))
        session._active, session._expected_before = True, 0
        runtime.done, runtime.result = True, 78
        statuses = [session.poll() for _ in range(MAX_VERIFY_POLLS)]
        self.assertEqual(["verify_pending"] * (MAX_VERIFY_POLLS - 1) + ["failed"], statuses)

    def test_an_unhydrated_verify_gets_the_long_budget_not_the_fast_one(self):
        runtime = FakeRuntime(slot_records={EMPTY_SLOT: SlotRecord(None, None, None)})
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=0))
        session._active, session._expected_before = True, 0
        runtime.done, runtime.result = True, EMPTY_SLOT
        statuses = [session.poll() for _ in range(MAX_VERIFY_POLLS + 5)]
        self.assertEqual({"verify_pending"}, set(statuses))
        self.assertIn(f"/{MAX_HYDRATION_VERIFY_POLLS}", session.state.detail)

    def test_an_in_flight_native_call_reports_executing_until_done(self):
        runtime = FakeRuntime()
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=0))
        session._active, session._expected_before = True, 0
        self.assertEqual("executing", session.poll())

    def test_a_pending_request_cell_blocks_a_second_queue(self):
        runtime = FakeRuntime()
        runtime.pending = True
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=0))
        for _ in range(MIN_ABSENT_POLLS - 1):
            session.poll()
        self.assertEqual("busy", session.poll())
        self.assertEqual(0, len(runtime.queued), "a busy request cell must not be overwritten")

    def test_the_durable_state_carries_the_pair_a_restart_needs(self):
        runtime = FakeRuntime({PEBBLE: StackView(3, True, 79, 0x2080_67C08)})
        session = GrantSession(runtime=runtime)
        session.submit(_command(expected_before=3))
        session.poll()
        self.assertEqual(3, session.state.expected_before)
        self.assertEqual(4, session.state.expected_after)
        self.assertEqual("ap-42", session.state.tag)

    def test_illegal_commands_are_rejected_before_any_memory_is_touched(self):
        for overrides in ({"quantity": 0}, {"quantity": 100}, {"tag": ""}, {"tag": "two words"}):
            with self.assertRaises(DeliveryError):
                _command(**overrides)


class GuestGeometryTests(unittest.TestCase):
    def test_slots_below_the_split_come_from_the_primary_bank(self):
        self.assertEqual(0x1000 + 5 * 0x10, entry_address(0, 5, 10, 0x1000, 0x2000))

    def test_slots_at_or_above_the_split_are_rebased_onto_the_secondary_bank(self):
        self.assertEqual(0x2000 + 4 * 0x10, entry_address(0, 14, 10, 0x1000, 0x2000))


class BaseResolutionTests(unittest.TestCase):
    LOG = (
        "Loading module eboot.bin\n"
        "  base_virtual_addr ..........: 0x05660000\n"
        "something else\n"
        "Loading module eboot.bin\n"
        "  base_virtual_addr ..........: 0x057C0000\n"
    )

    def test_the_latest_logged_base_wins(self):
        self.assertEqual(0x057C0000, logged_eboot_base(self.LOG))

    def test_a_log_without_a_base_returns_none_rather_than_a_guess(self):
        self.assertIsNone(logged_eboot_base("Loading module eboot.bin\nno address here\n"))


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(
            contract.contract_path(CONTRACT_ROOT).read_text(encoding="utf-8")
        )

    def test_the_committed_contract_is_what_the_generator_produces(self):
        self.assertEqual(contract.build_contract(), self.committed)

    def test_the_contract_records_the_payload_the_assembler_emits(self):
        blobs = {entry["name"]: entry for entry in self.committed["payload"]["blobs"]}
        for blob in payload.blobs():
            self.assertEqual(blob.data.hex().upper(), blobs[blob.name]["bytes"])

    def test_the_contract_hook_rvas_agree_with_the_cheat_engine_table(self):
        text = TABLE.read_text(encoding="utf-8")
        sites = {site["name"]: site for site in self.committed["hook_sites"]}
        self.assertIn(f"local consumeRva=0x{sites['consume_return']['rva']:X}", text)
        self.assertIn(f"local heartbeatRva=0x{sites['idle_heartbeat']['rva']:X}", text)

    def test_the_contract_original_bytes_agree_with_the_cheat_engine_asserts(self):
        text = TABLE.read_text(encoding="utf-8")
        for site in self.committed["hook_sites"]:
            self.assertIn(f"assert(80{site['rva']:X},{site['original_bytes'].lower().upper()})",
                          text.replace(", ", ","))

    def test_every_address_claim_carries_a_baseline_provenance_label(self):
        allowed = {"published", "observed", "inferred", "validated", "hypothesis"}
        found = []
        def walk(node):
            if isinstance(node, dict):
                if "provenance" in node:
                    found.append(node["provenance"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(self.committed)
        self.assertGreaterEqual(len(found), 15)
        self.assertFalse(set(found) - allowed, f"unknown provenance labels in {sorted(set(found))}")

    def test_the_payload_bytes_are_labelled_validated(self):
        """Owner checklist item 1 (2026-08-24): the caves were read back from a
        live armed shadPS4 process with tools/compare_ce_payload.py. The only
        differences were MR-form vs RM-form encodings of three reg-to-reg movs,
        which were switched to CE's encoding, so the shipped blob is now
        byte-identical to what CE emits. `validated` is earned, not asserted."""
        self.assertEqual("validated", self.committed["payload"]["provenance"])
        for blob in self.committed["payload"]["blobs"]:
            self.assertEqual("validated", blob["provenance"], blob["name"])

    def test_the_contract_names_only_the_validated_serial(self):
        self.assertEqual("CUSA03173", self.committed["target"]["serial"])
        self.assertEqual("01.09", self.committed["target"]["app_ver"])
        self.assertIn("CUSA00900", self.committed["target"]["note"])

    def test_the_fail_closed_policies_survive_into_the_contract(self):
        policy = self.committed["policy"]
        self.assertEqual("refused", policy["absent_blood_vial"])
        self.assertEqual(MAX_VERIFY_POLLS, policy["verify_polls"])
        self.assertEqual(MIN_ABSENT_POLLS, policy["min_absent_polls"])
        self.assertIn("Torch (ItemLot 20100000)", policy["excluded"])


class _FakeImage:
    """A sparse guest image: reads default to zero, writes are recorded in order.

    Seeded with the two validated hook originals so require_validated_image
    passes; every cave/state region is zero, which is exactly what the CE asserts
    demand ("this space is still unused"). base is 0 so address == rva.
    """

    def __init__(self):
        self.pid = 4321
        self._bytes = {}
        self.write_order = []
        self._seed(payload.CONSUME_HOOK_RVA, payload.CONSUME_ORIGINAL)
        self._seed(payload.HEARTBEAT_HOOK_RVA, payload.HEARTBEAT_ORIGINAL)

    def _seed(self, address, data):
        for index, byte in enumerate(data):
            self._bytes[address + index] = byte

    def read(self, address, size):
        return bytes(self._bytes.get(address + index, 0) for index in range(size))

    def write(self, address, data):
        self.write_order.append(address)
        self._seed(address, data)


class SafeInstallProtocolTests(unittest.TestCase):
    """The atomic-detour protocol, driven entirely by the fake thread controller.

    The live suspend + RIP read is the only thing these cannot exercise; it is
    owner checklist item 5a. Everything around it -- ordering, the nudge loop,
    fail-closed abort, and guaranteed resume -- is tested here."""

    CONSUME_HOOK = payload.CONSUME_HOOK_RVA
    HEARTBEAT_HOOK = payload.HEARTBEAT_HOOK_RVA

    def _windows(self):
        return [PatchWindow(self.CONSUME_HOOK, 7), PatchWindow(self.HEARTBEAT_HOOK, 7)]

    def test_a_rip_clear_of_both_windows_writes_on_the_first_attempt(self):
        controller = FakeThreadController(rips={1: self.CONSUME_HOOK - 0x10, 2: 0x1000})
        wrote = []
        outcome = install_detours_atomically(
            controller, self._windows(), lambda: wrote.append(True))
        self.assertEqual([True], wrote)
        self.assertEqual(1, outcome.attempts)
        self.assertEqual(0, controller.net_suspended)

    def test_a_rip_inside_a_window_nudges_until_it_clears(self):
        # Thread 2 sits inside the heartbeat window for two reads, then steps out.
        controller = FakeThreadController(rips={
            1: self.CONSUME_HOOK - 1,  # one below the window: clear
            2: [self.HEARTBEAT_HOOK + 3, self.HEARTBEAT_HOOK + 3, self.HEARTBEAT_HOOK + 8],
        })
        wrote = []
        outcome = install_detours_atomically(
            controller, self._windows(), lambda: wrote.append(True))
        self.assertEqual([True], wrote, "must not write while a RIP is in the window")
        self.assertEqual(3, outcome.attempts)
        self.assertEqual(3, controller.enumerate_calls, "each attempt re-samples (the nudge)")
        self.assertEqual(0, controller.net_suspended, "no thread left suspended after the nudge")

    def test_the_window_boundary_is_half_open(self):
        w = PatchWindow(self.HEARTBEAT_HOOK, 7)
        self.assertTrue(w.contains(self.HEARTBEAT_HOOK))
        self.assertTrue(w.contains(self.HEARTBEAT_HOOK + 6))
        self.assertFalse(w.contains(self.HEARTBEAT_HOOK + 7))  # first byte past the detour
        self.assertFalse(w.contains(self.HEARTBEAT_HOOK - 1))
        self.assertFalse(w.contains(None))  # a terminated thread cannot be in the window

    def test_budget_exhaustion_aborts_with_no_detour_written(self):
        controller = FakeThreadController(rips={1: self.HEARTBEAT_HOOK + 2})  # never clears
        wrote = []
        with self.assertRaises(InstallAborted) as caught:
            install_detours_atomically(
                controller, self._windows(), lambda: wrote.append(True), attempt_budget=5)
        self.assertFalse(wrote, "positive witness: write_detours was never called")
        self.assertEqual(5, caught.exception.attempts)
        self.assertEqual(5, controller.enumerate_calls)
        self.assertEqual(0, controller.net_suspended, "every suspend was matched by a resume")

    def test_both_detours_are_written_under_one_suspend(self):
        controller = FakeThreadController(rips={1: 0x2000, 2: 0x3000})
        observed = {}

        def write_detours():
            # At the commit point both threads are suspended and none resumed yet.
            observed["net"] = controller.net_suspended
            observed["enumerate_calls"] = controller.enumerate_calls

        install_detours_atomically(controller, self._windows(), write_detours)
        self.assertEqual(2, observed["net"], "both threads held under one suspend at write time")
        self.assertEqual(1, observed["enumerate_calls"], "a single suspend round covers both detours")

    def test_resume_runs_even_when_the_write_raises(self):
        controller = FakeThreadController(rips={1: 0x2000})

        def boom():
            raise RuntimeError("write failed")

        with self.assertRaises(RuntimeError):
            install_detours_atomically(controller, self._windows(), boom)
        self.assertEqual(0, controller.net_suspended, "no leaked suspend on the raising path")

    def test_a_zero_budget_is_rejected(self):
        controller = FakeThreadController(rips={1: 0x2000})
        with self.assertRaises(ValueError):
            install_detours_atomically(controller, self._windows(), lambda: None, attempt_budget=0)


class InstallRoutingTests(unittest.TestCase):
    """install() routes the two detours through the atomic protocol and keeps the
    caves-before-detours ordering at write time, not just structurally."""

    def _detour_addrs(self):
        return {
            payload.CONSUME_HOOK_RVA: payload.consume_detour().data,
            payload.HEARTBEAT_HOOK_RVA: payload.heartbeat_detour().data,
        }

    def test_dry_run_writes_nothing_and_needs_no_controller(self):
        image = _FakeImage()
        plan = install(image, 0, dry_run=True)
        self.assertEqual(5, len(plan))
        self.assertFalse(image.write_order, "dry run wrote nothing")

    def test_arming_without_a_controller_fails_closed(self):
        image = _FakeImage()
        with self.assertRaises(AttachError):
            install(image, 0, dry_run=False, controller=None)
        self.assertFalse(image.write_order, "nothing written when we refuse to arm")

    def test_a_clear_arm_writes_caves_before_detours(self):
        image = _FakeImage()
        controller = FakeThreadController(rips={1: 0x40})  # far from both hooks
        install(image, 0, dry_run=False, controller=controller)
        detour_addrs = {payload.CONSUME_HOOK_RVA, payload.HEARTBEAT_HOOK_RVA}
        first_detour = min(image.write_order.index(a) for a in detour_addrs)
        prelude = {payload.STATE_RVA, payload.CONSUME_CAVE_RVA, payload.HEARTBEAT_CAVE_RVA}
        last_prelude = max(image.write_order.index(a) for a in prelude)
        self.assertLess(last_prelude, first_detour, "every cave/state write precedes any detour")
        for address, data in self._detour_addrs().items():
            self.assertEqual(data, image.read(address, len(data)), "detour landed")

    def test_a_blocked_arm_aborts_leaving_the_original_hook_bytes(self):
        image = _FakeImage()
        # Thread parked inside the heartbeat window and never clearing.
        controller = FakeThreadController(rips={1: payload.HEARTBEAT_HOOK_RVA + 1})
        with self.assertRaises(InstallAborted):
            install(image, 0, dry_run=False, controller=controller, attempt_budget=3)
        # Positive witness: BOTH hook sites still hold their original bytes.
        self.assertEqual(payload.CONSUME_ORIGINAL,
                         image.read(payload.CONSUME_HOOK_RVA, len(payload.CONSUME_ORIGINAL)))
        self.assertEqual(payload.HEARTBEAT_ORIGINAL,
                         image.read(payload.HEARTBEAT_HOOK_RVA, len(payload.HEARTBEAT_ORIGINAL)))
        self.assertEqual(0, controller.net_suspended)


if __name__ == "__main__":
    unittest.main()
