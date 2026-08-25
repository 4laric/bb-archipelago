"""Developer-only CLI. Inert by default; nothing writes without --arm.

    python -m tools.bb_native_delivery contract --write
    python -m tools.bb_native_delivery payload
    python -m tools.bb_native_delivery verify --pid 1234
    python -m tools.bb_native_delivery install --pid 1234            # dry run
    python -m tools.bb_native_delivery install --pid 1234 --arm      # writes
    python -m tools.bb_native_delivery grant --pid 1234 --raw 0xB00004CE \
        --normalized 0x400004CE --quantity 1 --tag manual --arm
    python -m tools.bb_native_delivery grant --pid 1234 ... --arm --clear-stale-request

Only descriptors this project validated live can be armed (issue #146): a
category-4 goods pair, or an allowlisted equipment row. Everything else is
refused before the attach, --unvalidated-descriptor notwithstanding.

⚠️ DEVELOPER TOOL. Validated live on 2026-08-24 (shadPS4, CUSA03173 01.09):
dry-run and armed install, atomic detour commit, native grants, restart
persistence, replay recovery and the fail-closed refusals all passed on
throwaway saves. That covers one serial and one build, and the client half has
not shipped, so Cheat Engine remains the supported delivery path; see
docs/SPEC-client-without-cheat-engine.md.
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
from .descriptor import DescriptorError, describe_validated_descriptor

BANNER = (
    "bb_native_delivery is a DEVELOPER TOOL, validated live on 2026-08-24 against "
    "shadPS4 CUSA03173 01.09 only. Cheat Engine remains the supported delivery path."
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
    if writable:
        # Issue #144: from here on, every write is confined to the eboot regions
        # this tool installed. An external write to a guest data page freezes
        # shadPS4, so the guard fails closed rather than trusting call sites.
        memory.set_write_guard(base)
    return memory, base


def _gate_request_cell(memory, base, clear: bool) -> None:
    """Refuse to proceed on an armed request cell (issue #144).

    A tool crash between committing a request and acknowledging it leaves the
    cave armed with a hair trigger the player holds: the next consume hook fired
    in game executes the stale request. Adding a second grant on top of that is
    how it detonates, so both `grant` and `install` check the cell on attach.
    """
    from .process import (
        clear_stale_request,
        format_request_cell,
        read_request_cell,
        request_is_armed,
        require_idle_request_cell,
    )

    if clear:
        state_head, descriptor_bytes = read_request_cell(memory, base)
        if not request_is_armed(state_head):
            print("--clear-stale-request: the cell was already idle; cleared it anyway.")
        print("clearing the native request cell. What was there:")
        print(format_request_cell(state_head, descriptor_bytes))
        clear_stale_request(memory, base)
        after_state, after_descriptor = read_request_cell(memory, base)
        print("after:")
        print(format_request_cell(after_state, after_descriptor))
        return
    require_idle_request_cell(memory, base)


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
    from .process import StaleRequest, install
    from .threadcontrol import InstallAborted

    memory, base = _attach(args, writable=args.arm)
    if args.arm:
        try:
            _gate_request_cell(memory, base, args.clear_stale_request)
        except StaleRequest as exc:
            print(f"\nREFUSING TO INSTALL: {exc}")
            memory.close()
            return 1
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
                  "(see docs/INSTALL-ATOMICITY.md). The live suspend/RIP read was "
                  "validated against the game on 2026-08-24 -- owner checklist "
                  "item 5a.")
        else:
            print("\nDry run. Re-run with --arm to write. Arming suspends every guest "
                  "thread and verifies no RIP is inside a detour window before writing "
                  "(docs/INSTALL-ATOMICITY.md).")
    return 0


DEFAULT_JOURNAL_NAME = ".bb-native-grant-journal.json"


def _journal_path(args: argparse.Namespace) -> Path:
    return Path(args.journal) if args.journal else _repo_root() / DEFAULT_JOURNAL_NAME


def _read_journal(path: Path) -> dict:
    """The tags this CLI has armed before. A missing or corrupt file is empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _record_tag(path: Path, tag: str, status: str) -> None:
    """Best effort: an unwritable journal must not block a grant."""
    journal = _read_journal(path)
    entry = journal.get(tag) if isinstance(journal.get(tag), dict) else {}
    entry["status"] = status
    entry["armed_count"] = int(entry.get("armed_count", 0)) + (status == "armed")
    journal[tag] = entry
    try:
        path.write_text(json.dumps(journal, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        print(f"warning: could not update the grant journal at {path}: {exc}")


def _gate_descriptor(args: argparse.Namespace) -> int:
    """Refuse an unvalidated (raw, normalized) pair BEFORE anything is queued.

    Issue #146: the Torch negative canary executed on a live save because the
    CLI armed whatever it was handed and only then waited for hydration -- 39
    polls of waiting, and then a guest write. This gate runs before the attach,
    so the refusal costs no polls and reaches no guest memory.
    """
    try:
        derivation = describe_validated_descriptor(args.raw, args.normalized)
    except DescriptorError as exc:
        if args.unvalidated_descriptor:
            print("\n*** --unvalidated-descriptor: ARMING A DESCRIPTOR NOTHING VALIDATES ***")
            print("What evidence is missing:")
            print(f"  {exc}")
            print("Research only. Use a throwaway save; an invisible record is not "
                  "removable from a save you care about.")
            return 0
        print(f"\nREFUSING TO GRANT: {exc}")
        print("Nothing was queued and no guest memory was touched.")
        return 1
    print(f"descriptor allowlist: {derivation}")
    return 0


def _gate_reused_tag(args: argparse.Namespace, journal: Path) -> int:
    """Warn on a baseline-free grant; refuse a reused tag without one.

    Issue #146 item 4: an interrupted grant landed, and rerunning the same tag
    without ``--expected-before`` granted it a second time -- the CLI samples a
    live baseline when none is given, so a partial prior delivery is invisible
    to it. A fresh tag stays frictionless; a tag this journal has already armed
    is the case that cannot be ruled out.
    """
    if args.expected_before is not None:
        return 0
    print("warning: no --expected-before. The baseline is sampled live, so a prior "
          "partial delivery of this tag cannot be detected from the numbers alone.")
    entry = _read_journal(journal).get(args.tag)
    if not entry:
        return 0
    if args.force:
        print(f"--force: arming tag {args.tag!r} again anyway (journal says "
              f"status={entry.get('status')!r}).")
        return 0
    print(f"\nREFUSING TO GRANT: tag {args.tag!r} was already armed by this CLI "
          f"(journal {journal}, status={entry.get('status')!r}). A rerun without "
          "--expected-before cannot rule out that the first attempt landed, and the "
          "live reproduction in issue #146 double-granted exactly this way. Re-run "
          "with --expected-before <count read from the inventory UI>, or a fresh "
          "--tag, or --force if you have already ruled a prior delivery out.")
    return 1


def _poll_to_completion(session, timeout: float, sleep=time.sleep) -> int:
    """The CLI's poll loop, with the disarm handler around the WHOLE loop.

    Issue #146 item 5: #145 put the disarm inside :meth:`GrantSession.poll`, but
    a Ctrl+C lands in the ``sleep`` between polls far more often than inside one,
    and there it escaped the handler and left the cave armed.
    """
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            status = session.poll()
            print(f"{status}: {session.state.detail}")
            if status in TERMINAL:
                return 0 if status in SUCCESS else 1
            sleep(0.25)
    except BaseException:
        session.disarm_best_effort()
        print("\ninterrupted: disarmed the native request cell before exiting.")
        raise
    print("timed out")
    return 1


def _cmd_grant(args: argparse.Namespace) -> int:
    from .guest import GuestRuntime
    from .process import StaleRequest

    # Both gates are pre-queue and pre-attach: they must cost no hydration polls.
    refused = _gate_descriptor(args)
    if refused:
        return refused
    journal = _journal_path(args)
    if args.arm and _gate_reused_tag(args, journal):
        return 1

    memory, base = _attach(args, writable=args.arm)
    with memory:
        if not args.arm:
            print("Dry run: not queueing. Re-run with --arm.")
            return 0
        try:
            _gate_request_cell(memory, base, args.clear_stale_request)
        except StaleRequest as exc:
            print(f"\nREFUSING TO GRANT: {exc}")
            return 1
        session = GrantSession(runtime=GuestRuntime(memory, base))
        _record_tag(journal, args.tag, "armed")
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
        try:
            code = _poll_to_completion(session, args.timeout)
        except BaseException:
            _record_tag(journal, args.tag, "interrupted")
            raise
        _record_tag(journal, args.tag, session.state.status or "unknown")
        return code


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
            attached.add_argument(
                "--clear-stale-request", action="store_true",
                help="zero the native request cell and descriptor before proceeding "
                     "(issue #144); prints what it cleared",
            )
        attached.set_defaults(func=handler)

    grant = sub.choices["grant"]
    grant.add_argument("--raw", type=_hex_int, required=True)
    grant.add_argument("--normalized", type=_hex_int, required=True)
    grant.add_argument("--quantity", type=int, default=1)
    grant.add_argument("--tag", required=True)
    grant.add_argument("--expected-before", type=int, default=None)
    grant.add_argument("--manual", action="store_true")
    grant.add_argument(
        "--unvalidated-descriptor", action="store_true",
        help="research escape hatch (issue #146): arm a (raw, normalized) pair no live "
             "dump validates. Loud, never the default, and prints what evidence is missing",
    )
    grant.add_argument(
        "--force", action="store_true",
        help="arm a tag this CLI already armed even without --expected-before "
             "(issue #146); you are asserting no prior delivery landed",
    )
    grant.add_argument(
        "--journal", default=None,
        help=f"path to the reused-tag journal (default: repo root/{DEFAULT_JOURNAL_NAME})",
    )
    grant.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    print(BANNER, file=sys.stderr)
    args = build_parser().parse_args(argv)
    return args.func(args)
