"""Developer-only CLI. Inert by default; nothing writes without --arm.

    python -m tools.bb_native_delivery contract --write
    python -m tools.bb_native_delivery payload
    python -m tools.bb_native_delivery verify --pid 1234
    python -m tools.bb_native_delivery install --pid 1234            # dry run
    python -m tools.bb_native_delivery install --pid 1234 --arm      # writes
    python -m tools.bb_native_delivery grant --pid 1234 --raw 0xB00004CE \
        --normalized 0x400004CE --quantity 1 --tag manual --arm
    python -m tools.bb_native_delivery grant --pid 1234 ... --arm --clear-stale-request
    python -m tools.bb_native_delivery probe-storage --runbook
    python -m tools.bb_native_delivery probe-storage --pid 1234 --save-id throwaway-a \
        --pass a --arm --yes-throwaway-save
    python -m tools.bb_native_delivery probe-storage --summary

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


def _record_tag(path: Path, tag: str, status: str, **extra) -> None:
    """Best effort: an unwritable journal must not block a grant.

    ``extra`` is how the storage probe stores its per-step resume state
    (``probe_status``). It rides in this journal rather than a parallel store:
    a probe step IS a grant with a tag, so the reused-tag refusal from issue
    #146/#147 has to see it, and a second file would be a second answer to the
    question "has this tag been armed".
    """
    journal = _read_journal(path)
    entry = journal.get(tag) if isinstance(journal.get(tag), dict) else {}
    entry["status"] = status
    entry["armed_count"] = int(entry.get("armed_count", 0)) + (status == "armed")
    entry.update(extra)
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


DEFAULT_PROBE_REPORT = "bb-storage-probe.jsonl"


def _probe_report_path(args: argparse.Namespace) -> Path:
    """The operator's working directory, not the repo: a probe report is session
    evidence from one person's machine, and nothing in the repo consumes it."""
    return Path(args.report) if args.report else Path.cwd() / DEFAULT_PROBE_REPORT


def _probe_deliver(args, memory, base, step, expected_before: int):
    """One controlled probe grant, through the ordinary machinery.

    Nothing here re-implements delivery. The point of the probe is that the
    grant is exactly the grant the client will make, so the destination it
    observes is the destination players get; a bespoke path would measure the
    bespoke path.

    An at-cap grant is EXPECTED to end ``failed``: the stack does not reach
    ``expected_after`` because the surplus went to storage -- that is the whole
    observation (clients#445 read it as ``expected_after=5 actual=Some(20)``).
    So a terminal non-success status is recorded, not raised.
    """
    from .guest import GuestRuntime
    from .probe import DeliveryResult

    runtime = GuestRuntime(memory, base)
    if runtime.request_pending():
        raise SystemExit(
            "REFUSING: the native request cell is armed before this step. A probe step "
            "must be the only thing in flight. Re-run `grant --clear-stale-request` "
            "once, confirm the game is healthy, then resume the probe."
        )
    raw, normalized = step.descriptor
    session = GrantSession(runtime=runtime)
    session.submit(
        GrantCommand(
            raw_id=raw,
            normalized_id=normalized,
            quantity=step.quantity,
            tag=step.tag(args.save_id),
            expected_before=expected_before,
        )
    )
    _poll_to_completion(session, args.timeout)
    native_result = None
    try:
        native_result = runtime.native_result()
    except Exception as exc:  # pragma: no cover - a read failure is data, not a crash
        print(f"warning: could not read the result cell: {exc}")
    return DeliveryResult(
        status=session.state.status,
        detail=session.state.detail,
        native_result=native_result,
        expected_before=session.state.expected_before,
        expected_after=session.state.expected_after,
    )


def _cmd_probe_storage(args: argparse.Namespace) -> int:
    from . import probe

    probe.validate_steps()
    report = _probe_report_path(args)

    if args.runbook:
        print(probe.runbook())
        return 0
    if args.summary:
        records = probe.read_records(report)
        if not records:
            print(f"no probe records in {report}. Nothing to summarise.")
            return 1
        save_ids = tuple(sorted({record.get("save_id", "?") for record in records}))
        print(probe.render_summary(records, save_ids=save_ids))
        print(f"\n(read {len(records)} record(s) from {report})")
        print("Paste the block above into clients#445.")
        return 0

    if not args.save_id:
        print("REFUSING: --save-id names the throwaway save this pass runs on. It keys "
              "the journal, so resuming into a DIFFERENT save would silently skip steps "
              "that save never ran.")
        return 1
    try:
        steps = probe.steps_for(args.pass_name)
    except probe.ProbeError as exc:
        print(f"REFUSING: {exc}")
        return 1
    if args.only:
        wanted = set(args.only)
        steps = tuple(step for step in steps if step.step_id in wanted)
        unknown = wanted - {step.step_id for step in probe.PROBE_STEPS}
        if unknown:
            print(f"REFUSING: unknown step id(s): {', '.join(sorted(unknown))}")
            return 1
    if args.skip:
        steps = tuple(step for step in steps if step.step_id not in set(args.skip))
    if not steps:
        print("no steps selected")
        return 1

    journal_path = _journal_path(args)
    todo, done = probe.pending_steps(steps, _read_journal(journal_path), args.save_id)
    for step in done:
        print(f"[{step.step_id}] already recorded for save {args.save_id!r}; skipping. "
              f"(Re-run it with --redo {step.step_id}.)")
    if args.redo:
        redo = set(args.redo)
        todo = [step for step in steps if step.step_id in redo] + [
            step for step in todo if step.step_id not in redo
        ]
    if not todo:
        print(f"every selected step is already recorded for save {args.save_id!r}. "
              "Run with --summary to render the report.")
        return 0

    if not args.arm:
        print(probe.runbook(tuple(todo)))
        print("\nDry run: nothing was queued and no guest memory was touched. "
              "Re-run with --arm --yes-throwaway-save to deliver.")
        return 0
    if not args.yes_throwaway_save:
        print("REFUSING: --yes-throwaway-save is required. This session inserts a unique "
              "item, which a save can accept only once and which is not removable "
              "afterwards. Use a save you are willing to delete.")
        return 1

    from .process import StaleRequest

    memory, base = _attach(args, writable=True)
    with memory:
        try:
            _gate_request_cell(memory, base, args.clear_stale_request)
        except StaleRequest as exc:
            print(f"\nREFUSING TO PROBE: {exc}")
            return 1
        return _run_probe_steps(args, memory, base, todo, report, journal_path)


def _run_probe_steps(args, memory, base, todo, report, journal_path) -> int:
    from . import probe
    from .guest import GuestRuntime

    runtime = GuestRuntime(memory, base)
    recorded = 0
    for step in todo:
        tag = step.tag(args.save_id)
        print("\n" + "=" * 72)
        print(f"[{step.step_id}]  {step.hypothesis}  {step.item} x{step.quantity} "
              f"({step.lane} lane)")
        print(f"WHY:   {step.rationale}")
        print(f"DO THIS IN GAME FIRST:\n  {step.setup}")
        answer = input("ready? (y = deliver / s = skip this step / q = stop here): ").strip().lower()
        if answer.startswith("q"):
            print("stopping. Re-run the same command to resume where you left off.")
            break
        if answer.startswith("s"):
            _record_tag(journal_path, tag, "skipped", probe_status="skipped")
            print(f"[{step.step_id}] skipped and journalled; it will not be offered again "
                  f"for save {args.save_id!r} unless you pass --redo {step.step_id}.")
            continue

        raw, normalized = step.descriptor
        refused = _gate_descriptor(argparse.Namespace(
            raw=raw, normalized=normalized, unvalidated_descriptor=False))
        if refused:
            return refused

        read_back = runtime.find_stack(normalized)
        held_before = read_back.quantity if read_back and read_back.exists else 0
        typed = probe.parse_count(input(
            f"[{step.step_id}] read the HELD count for {step.item} off the in-game UI "
            f"(the tool read {held_before}): "))
        if typed is None:
            print(f"REFUSING: this step needs the count you can SEE. The tool's read-back "
                  "alone is what issue #146 showed cannot detect a partial prior delivery.")
            return 1
        if typed != held_before:
            print(f"REFUSING: the UI says {typed} and the tool read {held_before}. One of "
                  "them is wrong, and a probe that records a baseline it cannot "
                  "reconcile records nothing. Re-open the inventory, re-check, re-run.")
            return 1

        try:
            _record_tag(journal_path, tag, "armed", probe_status="in_flight")
            result = _probe_deliver(args, memory, base, step, held_before)
        except KeyboardInterrupt:
            _record_tag(journal_path, tag, "interrupted", probe_status="interrupted")
            print(f"\ninterrupted during [{step.step_id}]. The request cell was disarmed. "
                  "Confirm in game whether the item arrived before resuming.")
            raise
        print(f"delivery: {result.status}: {result.detail}")
        print(f"result cell: native_result={result.native_result} "
              f"expected_before={result.expected_before} expected_after={result.expected_after}")

        # The pre-delivery read-back is the one already taken above (and
        # reconciled against the UI), so the engine's first read replays it
        # rather than sampling a stack the grant has already changed.
        pending_reads = [held_before]

        def read_stack(normalized_id: int) -> int:
            if pending_reads:
                return pending_reads.pop(0)
            view = runtime.find_stack(normalized_id)
            return view.quantity if view and view.exists else 0

        context = probe.ProbeContext(
            save_id=args.save_id,
            read_stack=read_stack,
            deliver=lambda _step, _before: result,
            prompt=input,
            now=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        record = probe.run_step(step, context)
        record["operator_confirmed_held_before"] = typed
        probe.append_record(report, record)
        _record_tag(journal_path, tag, result.status or "unknown", probe_status="recorded")
        recorded += 1
        print(f"[{step.step_id}] recorded to {report}")

    print(f"\n{recorded} step(s) recorded this run.")
    records = probe.read_records(report)
    if records:
        print()
        print(probe.render_summary(
            records, save_ids=tuple(sorted({r.get("save_id", "?") for r in records}))))
        print("\nPaste the block above into clients#445.")
    return 0


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

    # The storage-routing probe (clients#445). It is a `grant` session with an
    # operator in the loop, so it takes the same attach flags -- but --pid is
    # optional here because --runbook and --summary touch no process at all.
    storage = sub.add_parser(
        "probe-storage",
        help="guided storage-routing probe: one controlled grant per step, "
             "recorded against the operator's in-game observation (clients#445)",
    )
    storage.add_argument("--pid", type=int, default=None)
    storage.add_argument("--base", type=_hex_int, default=None)
    storage.add_argument("--shad-log", default=None)
    storage.add_argument("--arm", action="store_true",
                         help="actually deliver; without it the run is a rehearsal")
    storage.add_argument("--clear-stale-request", action="store_true")
    storage.add_argument("--save-id", default=None,
                         help="a name for the THROWAWAY save this pass runs on; keys "
                              "the journal so resume cannot cross saves")
    storage.add_argument("--pass", dest="pass_name", default=None, choices=("a", "b"),
                         help="a = idle-first, b = sticky-first. Each pass needs its own "
                              "throwaway save: a unique item inserts once per save")
    storage.add_argument("--only", action="append", default=None, metavar="STEP")
    storage.add_argument("--skip", action="append", default=None, metavar="STEP")
    storage.add_argument("--redo", action="append", default=None, metavar="STEP",
                         help="run a step again even though the journal has it recorded")
    storage.add_argument("--report", default=None,
                         help=f"append-mode JSON-lines report "
                              f"(default: ./{DEFAULT_PROBE_REPORT})")
    storage.add_argument("--journal", default=None,
                         help=f"the grant journal (default: repo root/{DEFAULT_JOURNAL_NAME}); "
                              "probe resume state rides in it, not in a parallel store")
    storage.add_argument("--runbook", action="store_true",
                         help="print the operator runbook and exit; touches nothing")
    storage.add_argument("--summary", action="store_true",
                         help="render the verdicts from an existing report and exit")
    storage.add_argument("--yes-throwaway-save", action="store_true",
                         help="required with --arm: you are asserting this save is "
                              "disposable (the unique insert is once-per-save and "
                              "not removable)")
    storage.add_argument("--timeout", type=float, default=120.0)
    storage.set_defaults(func=_cmd_probe_storage)
    return parser


def main(argv: list[str] | None = None) -> int:
    print(BANNER, file=sys.stderr)
    args = build_parser().parse_args(argv)
    return args.func(args)
