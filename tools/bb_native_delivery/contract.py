"""Emit and load the machine-readable runtime contract.

``research/runtime/bb-native-grant-contract.v5.json`` is the single committed
statement of what the current native grant harness does to the guest process.
It exists so the Cheat Engine table, this prototype and (eventually)
``crates/bb-archipelago`` in the clients repo stop being three uncompared copies
of one contract.

Every address carries a ``provenance`` label from the RESEARCH-BASELINE.md
vocabulary. Read them literally. ``table-derived`` is NOT a label in that
vocabulary and is deliberately spelled out here as ``inferred`` with a note, so
nothing in this file can be mistaken for live validation it never had.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import payload
from .descriptor import DESCRIPTOR_SIZE, STAGED_SIZE
from .process import ASSERTS, CONSUME_SIGNATURE

CONTRACT_VERSION = "bb-native-grant-contract-v5"
HARNESS = "bb-native-grant-v7"
BUILD = "bb-0.1.0-r9"
PROTOCOL = "BBGRANT1"

ROOT_CANDIDATES = ("research/runtime/bb-native-grant-contract.v5.json",)


def contract_path(root: Path) -> Path:
    return root / ROOT_CANDIDATES[0]


def _blob_entry(blob: payload.AssembledBlob, provenance: str, note: str) -> dict:
    return {
        "name": blob.name,
        "rva": blob.rva,
        "size": len(blob.data),
        "bytes": blob.data.hex().upper(),
        "relocations": [reloc.as_dict() for reloc in blob.relocations],
        "provenance": provenance,
        "note": note,
    }


def build_contract() -> dict:
    return {
        "format": CONTRACT_VERSION,
        "harness": HARNESS,
        "build": BUILD,
        "bridge_protocol": PROTOCOL,
        "target": {
            "serial": "CUSA03173",
            "app_ver": "01.09",
            "eboot_sha256": "d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9",
            "emulator": "shadPS4 0.18.x",
            "provenance": "validated",
            "note": (
                "CUSA00900 01.09 reproduced the six published hook-site byte sequences "
                "read-only, but no grant path has ever been installed there. Every other "
                "serial and app version must fail closed."
            ),
        },
        "base_resolution": {
            "strategy": [
                "read the last eboot base_virtual_addr from shad_log.txt",
                "verify it against both hook originals",
                "otherwise AOB-scan the consume-return signature and require exactly one candidate",
            ],
            "consume_signature": CONSUME_SIGNATURE,
            "provenance": "validated",
            "note": (
                "shadPS4 0.18 maps the eboot below 4 GiB at a launch-dependent address; "
                "v0.17 absolutes such as 0x8014DA0A0 are not a portable binding."
            ),
        },
        "hook_sites": [
            {
                "name": "consume_return",
                "rva": payload.CONSUME_HOOK_RVA,
                "original_bytes": payload.CONSUME_ORIGINAL.hex(" ").upper(),
                "return_rva": payload.CONSUME_RETURN_RVA,
                "provenance": "validated",
                "note": "the accepted game-thread context for the native grant",
            },
            {
                "name": "idle_heartbeat",
                "rva": payload.HEARTBEAT_HOOK_RVA,
                "original_bytes": payload.HEARTBEAT_ORIGINAL.hex(" ").upper(),
                "return_rva": payload.HEARTBEAT_RETURN_RVA,
                "provenance": "validated",
                "note": (
                    "runs every frame; drives a zero-delta update on the Bullet stack so the "
                    "consume hook fires without player input. Its patch window is the "
                    "atomicity hazard."
                ),
            },
            {
                "name": "hp_capture", "rva": payload.HP_HOOK_RVA,
                "original_bytes": payload.HP_ORIGINAL.hex(" ").upper(),
                "return_rva": payload.HP_RETURN_RVA, "provenance": "published",
                "note": "captures the validated player status pointer; incoming DeathLink writes current HP at +0xF8",
            },
        ],
        "native_routines": [
            {"name": "allocate_equipment_instance", "rva": payload.ALLOCATE_EQUIPMENT_INSTANCE_RVA,
             "provenance": "validated",
             "signature": "(rdi=descriptor, rsi=equipment registry, edx=raw id) -> descriptor handle",
             "note": "live-validated with a Beast Claw whose allocated handle resolved to a weapon object"},
            {"name": "allocate_armor_instance", "rva": payload.ALLOCATE_ARMOR_INSTANCE_RVA,
             "provenance": "validated",
             "signature": "(rdi=descriptor, rsi=equipment registry, edx=raw id) -> armor handle",
             "note": "Charred Hunter Garb appeared in inventory and equipped successfully"},
            {"name": "resolve_descriptor", "rva": payload.RESOLVE_DESCRIPTOR_RVA,
             "provenance": "validated",
             "signature": "(rdi=descriptor) -> backing equipment object"},
            {"name": "lookup_weapon_param", "rva": payload.LOOKUP_WEAPON_PARAM_RVA,
             "provenance": "validated",
             "signature": "(rdi=lookup result, esi=normalized weapon id) -> param row at result+8"},
            {"name": "ItemGrant", "rva": payload.ITEM_GRANT_RVA, "provenance": "validated",
             "signature": "(rdi=inventory, rsi=descriptor, edx=quantity) -> slot|-1"},
            {"name": "quantity_delta", "rva": payload.QUANTITY_DELTA_RVA, "provenance": "validated",
             "signature": "(rdi=inventory, esi=slot, edx=delta, rcx=overflow, r8=metadata, r9=0)"},
            {"name": "find_slot_by_descriptor", "rva": payload.FIND_SLOT_RVA, "provenance": "validated",
             "signature": "(rdi=inventory, rsi=descriptor) -> slot|-1"},
        ],
        "descriptor": {
            "size": DESCRIPTOR_SIZE,
            "staged_size": STAGED_SIZE,
            "fields": [
                {"offset": 0x00, "width": 4, "name": "raw_id"},
                {"offset": 0x08, "width": 8, "name": "internal_pointer", "note": "game-filled; staged zero"},
                {"offset": 0x10, "width": 4, "name": "normalized_id"},
            ],
            "goods_formula": {
                "raw": "0xB0000000 | goods_id",
                "normalized": "0x40000000 | goods_id",
                "provenance": "inferred",
                "note": (
                    "holds for the validated category-4 canaries (Pebble 0x4CE, Bullets 0x384, "
                    "Vials 0x3E8). It is NOT a general runtime-descriptor formula: Torch and "
                    "Rifle Spear ItemLot ids produced invisible records."
                ),
            },
            "source_selection": {
                "test": "raw_id & 0xF0000000 == 0x80000000",
                "true": (
                    "persistent descriptor cell after native equipment-instance allocation; "
                    "the backing object's durability is initialized from EquipParamWeapon +0xBE"
                ),
                "false": "24 bytes materialized in the consume frame (category 4, goods)",
                "provenance": "validated",
            },
        },
        "state_cells": {
            "region_rva": payload.STATE_RVA,
            "region_size": 0x70,
            "cells": [
                {"name": "request", "rva": payload.REQUEST_RVA, "width": 4,
                 "values": {"0": "idle", "1": "native insert", "2": "existing-stack delta",
                            "3": "read-only generated-instance resolver probe"}},
                {"name": "quantity", "rva": payload.QUANTITY_RVA, "width": 4},
                {"name": "result", "rva": payload.RESULT_RVA, "width": 4, "note": "native slot, or 0xFFFFFFFF"},
                {"name": "done", "rva": payload.DONE_RVA, "width": 4},
                {"name": "inventory", "rva": payload.INVENTORY_RVA, "width": 8,
                 "note": "cached by the consume hook from r13; zero until one consumable is used"},
                {"name": "overflow", "rva": payload.OVERFLOW_RVA, "width": 4},
                {"name": "slot_index", "rva": payload.SLOT_INDEX_RVA, "width": 4},
                {"name": "item_quantity_pointer", "rva": payload.ITEM_QUANTITY_POINTER_RVA, "width": 8,
                 "note": "quantity pointer for request 2; resolved backing-object pointer for diagnostic request 3"},
                {"name": "heartbeat_descriptor", "rva": payload.HEARTBEAT_DESCRIPTOR_RVA, "width": 12,
                 "note": "Bullets: raw B0000384, normalized 40000384, delta arg at +0xC"},
                {"name": "manual_trigger", "rva": payload.MANUAL_TRIGGER_RVA, "width": 4},
                {"name": "descriptor", "rva": payload.DESCRIPTOR_RVA, "width": STAGED_SIZE},
                {"name": "player_status", "rva": payload.PLAYER_STATUS_RVA, "width": 8,
                 "note": "latest RDI observed at the HP hook; current HP is player_status+0xF8"},
            ],
            "provenance": "validated",
        },
        "inventory_geometry": {
            "split": 0x24, "last": 0x88, "primary_array": 0x58, "secondary_array": 0x48,
            "record_stride": 0x10, "record_id": 0x04, "record_quantity": 0x08,
            "provenance": "observed",
        },
        "asserts": [
            {"name": name, "rva": rva, "bytes": " ".join(text.split()), "provenance":
             ("published" if name == "hp_hook" else
              "validated" if name.endswith("hook") else
              "inferred" if name == "hp_cave" else "observed"),
             "note": (
                 "instruction observed by the validated HP capture table; install fails closed until it matches the live image"
                 if name == "hp_hook" else
                 "spare gap between the heartbeat cave and state region; a mismatch refuses the native install"
                 if name == "hp_cave" else
                 "hook originals are validated; zeroed cave regions are an unused-space claim"
             )}
            for name, rva, text in ASSERTS
        ],
        "payload": {
            "assembled_at_base": 0,
            "source": "tools/bb_native_delivery/payload.py",
            "source_of_truth": "tables/Bloodborne-native-item-grant-auto-v2.CT autoAssemble template",
            "provenance": "validated",
            "note": (
                "VALIDATED 2026-08-24 against a live shadPS4 process. The CE table was "
                "loaded and armed, both caves read back with tools/compare_ce_payload.py, "
                "and the only differences were MR-form vs RM-form encodings of three "
                "reg-to-reg movs (mov rdi,r13 x2; mov rsi,rsp; mov esi,eax) -- semantically "
                "identical instructions. The assembler was switched to CE's RM-form encoding, "
                "so the shipped blob is now byte-identical to what CE emits. Owner checklist "
                "item 1 is complete."
            ),
            "blobs": [
                _blob_entry(payload.state_region(), "validated", "initial request/state block"),
                _blob_entry(payload.consume_cave(), "validated", "consume-return detour cave"),
                _blob_entry(payload.heartbeat_cave(), "validated", "idle-heartbeat detour cave"),
                _blob_entry(payload.hp_cave(), "inferred", "capture RDI, replay mov edx,[rdi+F8], return; pointer cell is at cave+0x30"),
                _blob_entry(payload.consume_detour(), "validated", "E9 rel32 + NOP pad over the original"),
                _blob_entry(payload.heartbeat_detour(), "validated", "E9 rel32 + NOP pad over the original"),
                _blob_entry(payload.hp_detour(), "inferred", "E9 rel32 + NOP over the HP read"),
            ],
        },
        "policy": {
            "absent_blood_vial": "refused",
            "absent_blood_vial_reason": (
                "live reproduction created raw 0xF00003E8 '?ItemInfo?' instead of 0xB00003E8"
            ),
            "equipment": (
                "allowlist only; allocate a category-0 instance, resolve its backing object, "
                "and initialize current durability at object+0x18 from durabilityMax at "
                "EquipParamWeapon row+0xBE before ItemGrant"
            ),
            "armor": "exact allowlist; category-1 allocator; Charred Hunter Garb insert and equip validated",
            "blood_gems": "refused; category-8 lot ids require generation semantics not yet mapped",
            "excluded": ["Torch (ItemLot 20100000)", "Rifle Spear (ItemLot 10000000)"],
            "verify_polls": 20,
            "hydration_verify_polls": 240,
            "min_absent_polls": 40,
        },
    }


def write_contract(root: Path) -> Path:
    path = contract_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_contract(), indent=2) + "\n", encoding="utf-8")
    return path


def load_contract(root: Path) -> dict:
    return json.loads(contract_path(root).read_text(encoding="utf-8"))
