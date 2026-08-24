"""Guest thread suspension for atomic detour installation.

The heartbeat hook at ``eboot+0x1BFE882`` executes every frame. Overwriting the
seven original bytes with an ``E9 rel32`` + ``NOP`` detour is not atomic against
a guest thread that is mid-fetch inside that window: it can resume into a
half-written instruction and take a native fault that no ``ReadProcessMemory``
re-verification pass can catch, because the thread is already gone. See
``docs/INSTALL-ATOMICITY.md`` for the hazard, the ordering argument, and the
protocol this module implements.

The one primitive that cannot be exercised without the game -- suspending a live
guest thread and reading its ``RIP`` -- lives behind :class:`ThreadController`.
:class:`WindowsThreadController` is the real implementation and is
``untested-against-game``: no line of it has run against shadPS4, for the same
reason the rest of this package hasn't (the sandbox has neither Windows nor the
emulator). :class:`FakeThreadController` is scriptable and is what the tests
drive, so the *control flow* around the primitive is fully exercised while the
primitive itself stays owner-gated (owner checklist item 5a).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence

#: How many suspend/check/nudge rounds before we give up and fail closed. A
#: heartbeat thread only sits inside the seven-byte window for the handful of
#: cycles it takes to retire one instruction, so a clear read normally lands on
#: the first attempt; the budget exists so a pathological schedule aborts rather
#: than spins forever.
DEFAULT_ATTEMPT_BUDGET = 100


@dataclass(frozen=True)
class PatchWindow:
    """An absolute byte range a detour write will land on. ``rip`` inside
    ``[start, start + length)`` at write time is the unsafe condition."""

    start: int
    length: int

    def contains(self, rip: int | None) -> bool:
        if rip is None:  # a terminated thread has no context; it cannot be in the window
            return False
        return self.start <= rip < self.start + self.length


class InstallAborted(Exception):
    """The attempt budget was exhausted with a thread still in a patch window.

    Raised *before* any detour byte is written. Fail closed: the caves and state
    region are already in place and are harmless on their own (nothing jumps to
    them until a detour exists), so aborting here leaves a consistent,
    un-hooked image.
    """

    def __init__(self, attempts: int) -> None:
        super().__init__(
            f"aborting install: a guest thread stayed inside a detour window across "
            f"{attempts} suspend attempts; no detour was written"
        )
        self.attempts = attempts


class ThreadController(Protocol):
    """The live primitive, injectable exactly like process.py injects
    OpenProcess/ReadProcessMemory so the protocol runs on Linux under a fake."""

    def enumerate(self) -> Sequence[int]:
        """Thread ids belonging to the guest process, sampled now."""
        ...

    def suspend(self, tid: int) -> None:
        ...

    def resume(self, tid: int) -> None:
        ...

    def rip(self, tid: int) -> int | None:
        """The suspended thread's instruction pointer, or ``None`` if its context
        is unavailable (the thread exited between enumerate and read)."""
        ...


@dataclass
class InstallOutcome:
    attempts: int
    thread_count: int


def _suspend_all(controller: ThreadController, tids: Sequence[int]) -> list[int]:
    suspended: list[int] = []
    for tid in tids:
        controller.suspend(tid)
        suspended.append(tid)
    return suspended


def _resume_all(controller: ThreadController, tids: Sequence[int]) -> None:
    # Resume every thread we suspended, even if one resume raises: a leaked
    # suspend is its own hang. Best-effort, first error re-raised after the rest.
    first_error: Exception | None = None
    for tid in tids:
        try:
            controller.resume(tid)
        except Exception as exc:  # pragma: no cover - defensive; fake never raises here
            first_error = first_error or exc
    if first_error is not None:  # pragma: no cover
        raise first_error


def install_detours_atomically(
    controller: ThreadController,
    windows: Sequence[PatchWindow],
    write_detours: Callable[[], None],
    *,
    attempt_budget: int = DEFAULT_ATTEMPT_BUDGET,
) -> InstallOutcome:
    """Suspend every guest thread, verify no RIP is inside either window, and only
    then run ``write_detours`` -- once, under a single suspend covering *both*
    windows -- before resuming.

    ``write_detours`` must write both detours. Doing them under one suspend is
    load-bearing: if the first detour were committed and threads resumed before
    the second, a thread redirected through the first cave could re-enter the
    second window before it was patched. One suspend, both writes, then resume.

    Resume is guaranteed on every path (clear-and-write, not-clear-nudge, and a
    raising ``write_detours``) so no thread is ever left suspended.
    """
    if attempt_budget < 1:
        raise ValueError("attempt_budget must be at least 1")

    for attempt in range(1, attempt_budget + 1):
        tids = list(controller.enumerate())
        suspended = _suspend_all(controller, tids)
        try:
            # Read each RIP exactly once per attempt (GetThreadContext is not free,
            # and a scripted fake must not be double-consumed), then test it against
            # every window.
            rips = [controller.rip(tid) for tid in suspended]
            blocked = any(
                window.contains(rip) for rip in rips for window in windows
            )
            if not blocked:
                # Commit point. Both detours, under this one suspend.
                write_detours()
                return InstallOutcome(attempts=attempt, thread_count=len(suspended))
        finally:
            # Always resume -- clears the way for the nudge on a blocked attempt,
            # and never leaves a thread suspended if write_detours raised.
            _resume_all(controller, suspended)
        # Blocked: threads are running again (the nudge); loop re-samples and
        # re-suspends on the next attempt.

    raise InstallAborted(attempt_budget)


# --------------------------------------------------------------------------
# Test double. Not Windows-specific; drives the protocol above on any platform.
# --------------------------------------------------------------------------


@dataclass
class FakeThreadController:
    """A scriptable ThreadController for tests.

    ``rips`` maps a thread id to either a fixed int RIP or a list of RIPs
    consumed one per read, so a test can make a thread sit inside a window for a
    few attempts and then step out (the nudge clearing). Every suspend and resume
    is recorded so tests can assert nothing is left suspended.
    """

    rips: dict = field(default_factory=dict)
    suspend_log: list = field(default_factory=list)
    resume_log: list = field(default_factory=list)
    #: How many times enumerate() has been called -- i.e. attempts started.
    enumerate_calls: int = 0

    def enumerate(self) -> Sequence[int]:
        self.enumerate_calls += 1
        return list(self.rips.keys())

    def suspend(self, tid: int) -> None:
        self.suspend_log.append(tid)

    def resume(self, tid: int) -> None:
        self.resume_log.append(tid)

    def rip(self, tid: int) -> int | None:
        value = self.rips.get(tid)
        if isinstance(value, list):
            if not value:
                return None
            return value.pop(0)
        return value  # int or None

    @property
    def net_suspended(self) -> int:
        """Suspends minus resumes. Must be zero after any install call."""
        return len(self.suspend_log) - len(self.resume_log)


# --------------------------------------------------------------------------
# Real Windows implementation. UNTESTED AGAINST THE GAME (owner checklist 5a).
# --------------------------------------------------------------------------


class WindowsThreadController:  # pragma: no cover - requires Windows + the emulator
    """Enumerate/suspend/resume the guest threads and read each RIP via Win32.

    ``inferred`` at best -- no line here has run against shadPS4. It mirrors how
    :mod:`.process` wraps kernel32 directly. Enumeration uses a Toolhelp thread
    snapshot filtered to the target pid; RIP comes from ``GetThreadContext`` with
    ``CONTEXT_CONTROL``.
    """

    TH32CS_SNAPTHREAD = 0x00000004
    THREAD_SUSPEND_RESUME = 0x0002
    THREAD_GET_CONTEXT = 0x0008
    THREAD_QUERY_INFORMATION = 0x0040
    CONTEXT_AMD64 = 0x00100000
    CONTEXT_CONTROL = CONTEXT_AMD64 | 0x00000001

    def __init__(self, pid: int) -> None:
        import ctypes

        if not hasattr(ctypes, "WinDLL"):
            raise RuntimeError("WindowsThreadController requires Windows")
        self._ctypes = ctypes
        self._pid = pid
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def enumerate(self) -> Sequence[int]:
        import ctypes
        from ctypes import wintypes

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
            ]

        snapshot = self._kernel32.CreateToolhelp32Snapshot(self.TH32CS_SNAPTHREAD, 0)
        if snapshot == -1 or snapshot == 0xFFFFFFFF:
            raise RuntimeError("CreateToolhelp32Snapshot failed")
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(THREADENTRY32)
            tids = []
            ok = self._kernel32.Thread32First(snapshot, ctypes.byref(entry))
            while ok:
                if entry.th32OwnerProcessID == self._pid:
                    tids.append(int(entry.th32ThreadID))
                ok = self._kernel32.Thread32Next(snapshot, ctypes.byref(entry))
            return tids
        finally:
            self._kernel32.CloseHandle(snapshot)

    def _open(self, tid: int, access: int):
        handle = self._kernel32.OpenThread(access, False, tid)
        if not handle:
            raise RuntimeError(f"OpenThread({tid}) failed: {self._ctypes.get_last_error()}")
        return handle

    def suspend(self, tid: int) -> None:
        handle = self._open(tid, self.THREAD_SUSPEND_RESUME)
        try:
            if self._kernel32.SuspendThread(handle) == -1:
                raise RuntimeError(f"SuspendThread({tid}) failed")
        finally:
            self._kernel32.CloseHandle(handle)

    def resume(self, tid: int) -> None:
        handle = self._open(tid, self.THREAD_SUSPEND_RESUME)
        try:
            self._kernel32.ResumeThread(handle)
        finally:
            self._kernel32.CloseHandle(handle)

    def rip(self, tid: int) -> int | None:
        import ctypes

        # CONTEXT (AMD64) must be 16-byte aligned; over-allocate and slot Rip by
        # its documented offset (0xF8) rather than mirror the whole 1232-byte
        # structure. ContextFlags sits at 0x30.
        buffer_size = 1232
        raw = (ctypes.c_byte * (buffer_size + 16))()
        address = ctypes.addressof(raw)
        aligned = (address + 15) & ~15
        ctypes.memset(address, 0, buffer_size + 16)
        ctypes.c_uint32.from_address(aligned + 0x30).value = self.CONTEXT_CONTROL

        handle = self._open(tid, self.THREAD_GET_CONTEXT | self.THREAD_QUERY_INFORMATION)
        try:
            ok = self._kernel32.GetThreadContext(handle, ctypes.c_void_p(aligned))
            if not ok:
                return None
            return int(ctypes.c_uint64.from_address(aligned + 0xF8).value)
        finally:
            self._kernel32.CloseHandle(handle)
