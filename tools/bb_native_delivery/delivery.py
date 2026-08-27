"""The grant state machine, lifted out of the Cheat Engine harness's ``poll()``.

This is a faithful port of the control flow in
``tables/Bloodborne-native-item-grant-auto-v2.CT`` (``bb-native-grant-v7``),
with every memory access behind the :class:`Runtime` protocol so the transitions
can be tested without a game. The semantics that matter, and that the CE table
paid for live:

* hydration grace -- a stack that merely *looks* absent right after a load gets
  ``MIN_ABSENT_POLLS`` polls before the native insert path is allowed, because
  an early declaration inserts a duplicate stack next to an invisible one;
* bounded verify -- ``MAX_VERIFY_POLLS`` normally, ``MAX_HYDRATION_VERIFY_POLLS``
  when the evidence shape is "not hydrated yet" (empty result slot *and* no
  stack) rather than "contradicted";
* verify against the slot the native call reported, not only a whole-inventory
  scan, which returns the first matching stack and is the wrong witness when the
  game merged into a stack that was invisible at queue time;
* replay recovery -- a durable ``expected_before`` from a previous process lets a
  restart decide "already applied" instead of granting twice;
* fail closed -- absent Blood Vial insertion is refused outright after the live
  ``?ItemInfo?`` (``0xF00003E8``) reproduction.

Issue #144 retired one transition that used to live here. An *existing* stack
was grown by writing its quantity field with WriteProcessMemory from outside the
process. Two live reproductions on 2026-08-24 showed that write wounding the
emulator: the read-back of the same address microseconds later failed and the
guest froze shortly after. The mechanism, ``inferred`` but explaining both
freezes and the intermittent reads, is that shadPS4 protection-tracks the guest
inventory page; the eboot-image regions the caves live in are demonstrably safe
to write externally, the inventory page is not.

So both branches now go through the cave, which runs on the game's own thread:

* absent stack -> ``request = 1``, the ``ItemGrant`` insert path;
* existing stack -> ``request = 2``, the cave's ``bbAutoExisting`` label, which
  calls the game's quantity-delta routine with the slot index and quantity
  pointer the tool already located.

``_direct_write`` is kept below, unreachable from :meth:`GrantSession.poll`, so
the retired transition stays readable next to the note explaining why it is
retired. Nothing on the live ``GuestRuntime`` path calls it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .descriptor import ItemGrantDescriptor, uses_persistent_source

MAX_VERIFY_POLLS = 20
MAX_HYDRATION_VERIFY_POLLS = 240
MIN_ABSENT_POLLS = 40

BLOOD_VIAL_NORMALIZED = 0x400003E8
BULLET_NORMALIZED = 0x40000384

EMPTY_SLOT = 0xFFFFFFFF

TERMINAL = frozenset(
    {"completed", "recovered_complete", "failed", "quantity_mismatch", "command_rejected", "write_error"}
)
SUCCESS = frozenset({"completed", "recovered_complete"})
RECOVERABLE_PRIOR = frozenset(
    {"executing", "queued", "verify_pending", "recovery_pending", "completed", "recovered_complete"}
)


class DeliveryError(Exception):
    pass


@dataclass(frozen=True)
class GrantCommand:
    raw_id: int
    normalized_id: int
    quantity: int
    tag: str
    #: ``None`` means "sample the live baseline and record it durably".
    expected_before: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.quantity <= 99:
            raise DeliveryError("grant quantity must be between 1 and 99")
        if not self.tag or any(character.isspace() for character in self.tag):
            raise DeliveryError("grant tag must be one non-empty token")


@dataclass(frozen=True)
class StackView:
    """What an inventory scan found for one normalized id."""

    quantity: int
    exists: bool
    slot: int | None = None
    quantity_address: int | None = None


@dataclass(frozen=True)
class SlotRecord:
    normalized_id: int | None
    quantity: int | None
    address: int | None


class Runtime(Protocol):
    """Everything the machine needs from the guest process."""

    def inventory_ready(self) -> bool: ...
    def find_stack(self, normalized_id: int) -> StackView | None: ...
    def read_slot_record(self, slot: int) -> SlotRecord: ...
    def write_quantity(self, address: int, value: int) -> bool: ...
    def request_pending(self) -> bool: ...
    def queue_native(
        self, descriptor: ItemGrantDescriptor, quantity: int, slot: int | None,
        quantity_address: int | None, manual_trigger: bool,
        existing_stack: bool = False,
    ) -> None: ...
    def native_done(self) -> bool: ...
    def native_result(self) -> int: ...
    def clear_request(self) -> None: ...

    def read_unavailable(self) -> bool:
        """True when the last geometry read exhausted its retry budget.

        Optional: implementations that cannot fail a read (the test fakes) may
        omit it, and :class:`GrantSession` treats its absence as False.
        """
        ...


@dataclass
class DurableState:
    """The rows the CE bridge persisted to ``native-grant-state.txt``.

    They exist so a crash between a durable grant and its acknowledgement is
    decidable on the next launch instead of being replayed blind.
    """

    status: str = "awaiting_inventory"
    tag: str = ""
    expected_before: int | None = None
    expected_after: int | None = None
    detail: str = ""


@dataclass
class GrantSession:
    runtime: Runtime
    prior: DurableState = field(default_factory=DurableState)
    state: DurableState = field(default_factory=DurableState)
    command: GrantCommand | None = None
    _absent_polls: int = 0
    _absent_tag: str = ""
    _verify_polls: int = 0
    _expected_before: int | None = None
    _active: bool = False
    _manual: bool = False
    _verify_slot: int | None = None

    # -- helpers

    def _set(self, status: str, detail: str = "") -> str:
        self.state = DurableState(
            status=status,
            tag=self.command.tag if self.command else self.state.tag,
            expected_before=self._expected_before,
            expected_after=(
                None
                if self._expected_before is None or self.command is None
                else self._expected_before + self.command.quantity
            ),
            detail=detail,
        )
        return status

    def _finish(self, status: str, detail: str = "") -> str:
        result = self._set(status, detail)
        self._active = False
        return result

    def submit(self, command: GrantCommand, manual_trigger: bool = False) -> None:
        if self._active:
            raise DeliveryError("a grant is already in flight")
        self.command = command
        self._manual = manual_trigger
        self._absent_polls = 0 if self._absent_tag != command.tag else self._absent_polls
        self._absent_tag = command.tag
        self._verify_polls = 0
        self._expected_before = command.expected_before
        self._set("queued", f"tag={command.tag}")

    # -- the poll

    def poll(self) -> str:
        """One transition. Never leaves an armed request behind on the way out.

        Issue #144: a traceback out of the poll loop after the request cell had
        been committed left the cave armed, and the next consume hook the player
        triggered in game executed it and froze the guest. So any exception that
        escapes a poll with a request in flight disarms the cell first, best
        effort, and then propagates unchanged. This is belt, not braces -- the
        attach-time gate in :mod:`.process` is the backstop for the cases this
        cannot reach (a kill -9, a crash between the two writes).
        """
        try:
            if self._active:
                return self._poll_active()
            if self.command is None:
                return self.state.status
            if self.state.status in TERMINAL:
                return self.state.status
            return self._poll_pending()
        except BaseException:
            self._disarm_best_effort()
            raise

    def disarm_best_effort(self) -> None:
        """Disarm a committed request, if one is in flight. Never raises.

        Public because the CLI's poll loop needs it too (issue #146 item 5): a
        Ctrl+C in the loop's ``time.sleep`` lands outside :meth:`poll`, so the
        handler inside `poll` never sees it and the cell stayed armed.
        """
        if not self._active:
            return
        try:
            self.runtime.clear_request()
        except Exception:  # pragma: no cover - the backstop is the attach gate
            pass

    #: Retained name; :meth:`disarm_best_effort` is the same handler.
    _disarm_best_effort = disarm_best_effort

    def _poll_active(self) -> str:
        if not self.runtime.native_done():
            return self._set("executing", f"tag={self.command.tag} awaiting native completion")
        native_result = self.runtime.native_result()
        stack = self.runtime.find_stack(self.command.normalized_id)
        actual = stack.quantity if stack else None
        wanted = self._expected_before + self.command.quantity
        # The insert path returns the slot it filled. The existing path returns
        # the quantity-delta routine's own value, which is not a slot index, so
        # verify against the slot we located before queueing instead.
        record = self.runtime.read_slot_record(
            native_result if self._verify_slot is None else self._verify_slot
        )
        slot_verified = (
            record.normalized_id == self.command.normalized_id
            and record.quantity is not None
            and record.quantity >= self.command.quantity
        )
        if not slot_verified and actual != wanted:
            self._verify_polls += 1
            hydrating = record.normalized_id in (None, EMPTY_SLOT) and not actual
            budget = MAX_HYDRATION_VERIFY_POLLS if hydrating else MAX_VERIFY_POLLS
            if self._verify_polls < budget:
                return self._set(
                    "verify_pending",
                    f"tag={self.command.tag} expected_after={wanted} actual={actual} "
                    f"attempt={self._verify_polls}/{budget}",
                )
            return self._finish(
                "failed",
                f"tag={self.command.tag} expected_after={wanted} actual={actual} "
                f"native_result={native_result} retry_budget={budget}",
            )
        return self._finish("completed", f"tag={self.command.tag} native_result={native_result}")

    def _poll_pending(self) -> str:
        command = self.command
        if not self.runtime.inventory_ready():
            if self._read_unavailable():
                return self._set(
                    "read_unavailable",
                    "Command retained; a guest read failed its retry budget",
                )
            return self._set("awaiting_inventory", "Command retained; use one bullet once")
        stack = self.runtime.find_stack(command.normalized_id)
        if stack is None:
            if self._read_unavailable():
                # Issue #144: a failed ReadProcessMemory during the geometry
                # chase used to traceback out of the poll loop. It is a status
                # now, and a non-terminal one: the session stays resumable and
                # the next poll tries again.
                return self._set(
                    "read_unavailable",
                    "Command retained; a guest read failed its retry budget",
                )
            return self._set("awaiting_inventory", "Command retained; inventory geometry is not hydrated yet")
        if not stack.exists:
            self._absent_polls += 1
            if self._absent_polls < MIN_ABSENT_POLLS:
                return self._set(
                    "awaiting_inventory",
                    f"tag={command.tag} waiting for inventory hydration before declaring the "
                    f"stack absent ({self._absent_polls}/{MIN_ABSENT_POLLS})",
                )
        else:
            self._absent_polls = 0

        if command.expected_before is None:
            self._expected_before = self._recovered_baseline(command, stack.quantity)
        else:
            self._expected_before = command.expected_before
        wanted = self._expected_before + command.quantity

        if stack.quantity == wanted:
            return self._finish("recovered_complete", f"tag={command.tag} quantity={stack.quantity}")
        if stack.quantity != self._expected_before:
            return self._finish(
                "quantity_mismatch",
                f"tag={command.tag} expected_before={self._expected_before} actual={stack.quantity}",
            )

        if stack.exists:
            # Issue #144: this used to be `return self._direct_write(wanted)`.
            # The cave's `bbAutoExisting` branch does the same arithmetic on the
            # game's own thread, which is the only way the write survives.
            return self._queue(stack, existing_stack=True)

        if command.normalized_id == BLOOD_VIAL_NORMALIZED:
            return self._finish(
                "failed",
                f"tag={command.tag} absent Blood Vial insertion is disabled after the live "
                "invalid-record reproduction; acquire one Vial before delivery",
            )
        return self._queue(stack, existing_stack=False)

    def _queue(self, stack: StackView, *, existing_stack: bool) -> str:
        """Commit one request to the cave and go active.

        The existing-stack case takes the cave's own quantity-delta branch rather
        than reusing the insert path, and that branch is ``validated`` as of
        2026-08-24: owner checklist item 7 ran ``native existing-stack delta
        slot=78`` live. Whether the *insert* path's ``ItemGrant`` call would merge
        into an existing stack or duplicate the slot is moot for the delta path
        and remains ``inferred`` for the equipment insert path, which nothing has
        exercised live.
        """
        command = self.command
        if self.runtime.request_pending():
            return self._set("busy", "Native request already pending")

        descriptor = ItemGrantDescriptor(command.raw_id, command.normalized_id)
        try:
            self.runtime.queue_native(
                descriptor,
                command.quantity,
                stack.slot,
                stack.quantity_address,
                self._manual,
                existing_stack,
            )
        except BaseException:
            # The cell may be half-written; treat it as armed and disarm it.
            self._active = True
            raise
        self._active = True
        self._verify_polls = 0
        self._verify_slot = stack.slot if existing_stack else None
        if existing_stack:
            detail = (
                f"tag={command.tag} native existing-stack delta slot={stack.slot} "
                f"expected_after={self._expected_before + command.quantity}"
            )
        else:
            detail = (
                f"tag={command.tag} native source="
                f"{'persistent' if uses_persistent_source(command.raw_id) else 'in_frame'}"
            )
        return self._set("executing", detail)

    def _read_unavailable(self) -> bool:
        probe = getattr(self.runtime, "read_unavailable", None)
        return bool(probe()) if probe is not None else False

    def _direct_write(self, wanted: int) -> str:
        """RETIRED (issue #144); unreachable from :meth:`poll`.

        This is the external WriteProcessMemory into the guest inventory page
        that froze shadPS4 twice on 2026-08-24. It is kept only so the retired
        transition can be exercised against an in-memory fake, and must never be
        reached from a :class:`~.guest.GuestRuntime`.
        """
        command = self.command
        stack = self.runtime.find_stack(command.normalized_id)
        address = stack.quantity_address if stack else None
        if not address:
            return self._finish("write_error", f"tag={command.tag} quantity pointer missing")
        self._set("executing", f"tag={command.tag} direct expected_after={wanted}")
        if not self.runtime.write_quantity(address, wanted):
            return self._finish("write_error", f"tag={command.tag} quantity write failed")
        after = self.runtime.find_stack(command.normalized_id)
        if after is None or after.quantity != wanted:
            return self._finish(
                "failed",
                f"tag={command.tag} direct expected_after={wanted} "
                f"actual={after.quantity if after else None}",
            )
        return self._finish("completed", f"tag={command.tag} direct after={wanted}")

    def _recovered_baseline(self, command: GrantCommand, live_quantity: int) -> int:
        prior = self.prior
        recoverable = (
            prior.tag == command.tag
            and prior.expected_before is not None
            and prior.expected_after == prior.expected_before + command.quantity
            and prior.status in RECOVERABLE_PRIOR
        )
        return prior.expected_before if recoverable else live_quantity
