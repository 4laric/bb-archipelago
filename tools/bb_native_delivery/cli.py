"""Developer-only CLI. Inert by default; nothing writes without --arm.

    python -m tools.bb_native_delivery contract --write
    python -m tools.bb_native_delivery payload
    python -m tools.bb_native_delivery verify --pid 1234
    python -m tools.bb_native_delivery install --pid 1234            # dry run
    python -m tools.bb_native_delivery install --pid 1234 --arm      # writes
    python -m tools.bb_native_delivery grant --pid 1234 --raw 0xB00004CE \
        --normalized 0x400004CE --quantity 1 --tag manual --arm

⚠️ UNTESTED AGAINST A LIVE GAME. This has never attached to shadPS4. Cheat
Engine remains the supported delivery path; see docs/SPEC-client-without-cheat-engine.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import payload
from .contract import build_contract, contract_path, write_contract
from .delivery import GrantCommand, GrantSession, SUCCESS, TERMINAL

BANNER = (
    "bb_native_delivery is a DEVELOPER PROTOTYPE. It has never been run against "
    "a live game. Cheat Engine remains the supported delivery path."
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cmd_contract(args: argparse.Namespace) -> int:
    if args.write:
        print(f"wrote {write_contract(_repo_root())}")
        return 0
    print(json.dumps(build_contract(), indent=2))
    return 0


def _cmd_payload(_args: argparse.Namespace) -> int:
    for blob in payload.blobs():
        print(f"{blob.name:18} rva=+{blob.rva:#09x} size={len(blob.data):4}")
        print(f"  {blob.data.hex().upper()}")
        for reloc in blob.relocations:
            print(f"  reloc +{reloc.offset:#x} w{reloc.width} -> eboot+{reloc.target_rva:#x}")
    return 0


def _attach(args: argparse.Namespace, writable: bool):
    from .process import ProcessMemory, default_shad_log, logged_eboot_base, verify_base

    memory = ProcessMemory(args.pid, writable=writable)
    base = args.base
    if base is None:
        log = Path(args.shad_log) if args.shad_log else default_shad_log()
        base = logged_eboot_base(log.read_text(encoding="utf-8", errors="replace"))
        if base is None or not verify_base(memory, base):
            raise SystemExit(
                "could not resolve a validated eboot base from the shad log; "
                "pass --base explicitly (a live AOB scan is not implemented in this prototype)"
            )
    return memory, base


def _cmd_verify(args: argparse.Namespace) -> int:
    from .process import run_asserts

    memory, base = _attach(args, writable=False)
    with memory:
        print(f"eboot base 0x{base:X}")
        failed = 0
        for result in run_asserts(memory, base):
            mark = "ok " if result.ok else "FAIL"
            failed += not result.ok
            print(f"  [{mark}] {result.name:16} +{result.rva:#09x} {result.actual.hex(' ').upper()}")
        if failed:
            print("\nREFUSING: this is not the validated CUSA03173 01.09 image.")
        return 1 if failed else 0


def _cmd_install(args: argparse.Namespace) -> int:
    from .process import install
    from .threadcontrol import InstallAborted

    memory, base = _attach(args, writable=args.arm)
    controller = None
    if args.arm:
        from .threadcontrol import WindowsThreadController

        controller = WindowsThreadController(memory.pid)
    with memory:
        try:
            plan = install(memory, base, dry_run=not args.arm, controller=controller)
        except InstallAborted as exc:
            print(f"\nINSTALL ABORTED: {exc}")
            return 1
        for name, address, size in plan:
            print(f"{'WROTE' if args.arm else 'would write'} {name:18} 0x{address:X} ({size} bytes)")
        if args.arm:
            print("\nDetours were committed under a full guest-thread suspend "
                  "(see docs/INSTALL-ATOMICITY.md). The live suspend/RIP read is "
                  "untested against the game -- owner checklist item 5a.")
        else:
            print("\nDry run. Re-run with --arm to write. Arming suspends every guest "
                  "thread and verifies no RIP is inside a detour window before writing "
                  "(docs/INSTALL-ATOMICITY.md).")
    return 0


def _cmd_grant(args: argparse.Namespace) -> int:
    from .guest import GuestRuntime

    memory, base = _attach(args, writable=args.arm)
    with memory:
        if not args.arm:
            print("Dry run: not queueing. Re-run with --arm.")
            return 0
        session = GrantSession(runtime=GuestRuntime(memory, base))
        session.submit(
            GrantCommand(
                raw_id=args.raw,
                normalized_id=args.normalized,
                quantity=args.quantity,
                tag=args.tag,
                expected_before=args.expected_before,
            ),
            manual_trigger=args.manual,
        )
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            status = session.poll()
            print(f"{status}: {session.state.detail}")
            if status in TERMINAL:
                return 0 if status in SUCCESS else 1
            time.sleep(0.25)
        print("timed out")
        return 1


def _hex_int(text: str) -> int:
    return int(text, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bb_native_delivery", description=BANNER)
    sub = parser.add_subparsers(dest="command", required=True)

    contract = sub.add_parser("contract", help="print or regenerate the runtime contract")
    contract.add_argument("--write", action="store_true")
    contract.set_defaults(func=_cmd_contract)

    payload_parser = sub.add_parser("payload", help="assemble and print the static blob")
    payload_parser.set_defaults(func=_cmd_payload)

    for name, handler, help_text in (
        ("verify", _cmd_verify, "check the assert bytes; write nothing"),
        ("install", _cmd_install, "install the static payload (dry run without --arm)"),
        ("grant", _cmd_grant, "queue one grant descriptor and poll to completion"),
    ):
        attached = sub.add_parser(name, help=help_text)
        attached.add_argument("--pid", type=int, required=True)
        attached.add_argument("--base", type=_hex_int, default=None)
        attached.add_argument("--shad-log", default=None)
        if name != "verify":
            attached.add_argument("--arm", action="store_true",
                                  help="actually write to the guest process")
        attached.set_defaults(func=handler)

    grant = sub.choices["grant"]
    grant.add_argument("--raw", type=_hex_int, required=True)
    grant.add_argument("--normalized", type=_hex_int, required=True)
    grant.add_argument("--quantity", type=int, default=1)
    grant.add_argument("--tag", required=True)
    grant.add_argument("--expected-before", type=int, default=None)
    grant.add_argument("--manual", action="store_true")
    grant.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    print(BANNER, file=sys.stderr)
    args = build_parser().parse_args(argv)
    return args.func(args)
