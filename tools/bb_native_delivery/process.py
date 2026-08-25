"""Win32 attach / read / write for shadPS4.exe, replacing Cheat Engine's runtime.

DEVELOPER TOOL. Untested against a live game: no line in this module has been
run against shadPS4, because the sandbox this was written in has neither Windows
nor the emulator. Treat every claim here as ``inferred``.

The only Cheat Engine service with no trivial Win32 equivalent was
``autoAssemble``; :mod:`.payload` moves that to build time. What is left is
``OpenProcess`` / ``ReadProcessMemory`` / ``WriteProcessMemory`` /
``VirtualProtectEx``, plus the base resolution the CE table already performs by
reading shad_log.txt and falling back to a live signature scan.
"""

from __future__ import annotations

import ctypes
import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from . import payload
from .aob import BytePattern, parse
from .descriptor import STAGED_SIZE
from .threadcontrol import (
    DEFAULT_ATTEMPT_BUDGET,
    PatchWindow,
    ThreadController,
    install_detours_atomically,
)

#: The consume-return signature the CE table scans for when the log base is
#: stale. ``validated`` -- it resolved the base live on two machines.
CONSUME_SIGNATURE = "44 89 E0 48 83 C4 28 5B 41 5C 41 5D 41 5E 41 5F"

#: Assert bytes: every one of these must match before anything is written.
#: The hook originals are ``validated``; the zeroed cave regions are the CE
#: table's own ``assert`` arguments, i.e. "this space is still unused".
ASSERTS: tuple[tuple[str, int, str], ...] = (
    ("consume_hook", payload.CONSUME_HOOK_RVA, "44 89 E0 48 83 C4 28"),
    ("heartbeat_hook", payload.HEARTBEAT_HOOK_RVA, "48 81 C4 E8 07 00 00"),
    ("consume_cave", payload.CONSUME_CAVE_RVA, "00 " * 16),
    ("heartbeat_cave", payload.HEARTBEAT_CAVE_RVA, "00 " * 16),
    ("state_region", payload.STATE_RVA, "00 " * 16),
    ("descriptor", payload.DESCRIPTOR_RVA, "00 " * 24),
)

#: The span of the state block, in bytes, counted from ``payload.STATE_RVA``.
#: ``payload.state_region()`` is 0x70 bytes, but the 32-byte staged descriptor
#: starts at +0x60, so the block the tool owns actually runs to +0x80.
STATE_SPAN = (payload.DESCRIPTOR_RVA - payload.STATE_RVA) + STAGED_SIZE

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
PAGE_EXECUTE_READWRITE = 0x40


class WriteRefused(Exception):
    """A write was aimed outside the launcher-owned eboot regions.

    ``observed`` (issue #144, two live reproductions on 2026-08-24): the guest
    inventory page under shadPS4 is protection-tracked, so an external
    WriteProcessMemory into it wounds the emulator -- the read-back of the very
    address just written fails microseconds later and the guest freezes shortly
    after. Regions inside the eboot image (the caves, the state block, the
    descriptor, the two detour sites) were written externally many times in the
    same sessions with no ill effect.

    So the rule this guard enforces is not a style preference: every external
    write must land inside the eboot image. Anything else is refused, loudly,
    before a single byte reaches the guest.
    """


class AttachError(Exception):
    """The process could not be opened, or is not the image we validated."""


class ImageMismatch(AttachError):
    """An assert byte string did not match. Fail closed; never guess."""


@dataclass
class AssertResult:
    name: str
    rva: int
    expected: BytePattern
    actual: bytes
    ok: bool


def owned_write_ranges(base: int) -> tuple[tuple[str, int, int], ...]:
    """(name, start, end) for every region this tool is allowed to write.

    The five contract regions come straight from :func:`payload.blobs` -- the
    state block, both caves and both detour sites -- so the guard cannot drift
    away from what the installer actually writes. The descriptor span is added
    explicitly because it reaches past the end of the state blob (see
    :data:`STATE_SPAN`).
    """
    ranges = [
        (blob.name, base + blob.rva, base + blob.rva + len(blob.data))
        for blob in payload.blobs()
    ]
    ranges.append(("descriptor", base + payload.DESCRIPTOR_RVA,
                   base + payload.DESCRIPTOR_RVA + STAGED_SIZE))
    return tuple(ranges)


def assert_write_allowed(base: int, address: int, size: int) -> str:
    """Return the owning region's name, or raise :class:`WriteRefused`.

    Pure, so the guard is testable without a process. Fails closed: a write that
    straddles a region boundary is refused even though its first byte is inside.
    """
    if size <= 0:
        raise WriteRefused(f"refusing a {size}-byte write at {address:#x} (issue #144)")
    for name, start, end in owned_write_ranges(base):
        if start <= address and address + size <= end:
            return name
    raise WriteRefused(
        f"refusing WriteProcessMemory({address:#x}, {size}): outside the "
        f"launcher-owned eboot regions (eboot base {base:#x}). External writes "
        "to guest pages freeze shadPS4 -- see issue #144. Grants into an "
        "existing stack go through the native queue, not through this path."
    )


class ProcessMemory:
    """A thin ReadProcessMemory/WriteProcessMemory wrapper.

    Once :meth:`set_write_guard` has been told the eboot base, every write is
    checked against :func:`owned_write_ranges` and refused if it falls outside.
    The guard is armed by the CLI on attach; leaving it unset keeps the raw
    behaviour for probes that resolve a base by scanning.
    """

    def __init__(self, pid: int, *, writable: bool = False) -> None:
        if os.name != "nt":  # pragma: no cover - the sandbox has no Win32
            raise AttachError("this prototype only attaches on Windows")
        access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
        if writable:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(access, False, pid)
        if not handle:
            raise AttachError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
        self.pid = pid
        self.handle = handle
        self._kernel32 = kernel32
        self._write_guard_base: int | None = None

    def set_write_guard(self, base: int) -> None:
        """Confine every subsequent write to the eboot regions at ``base``."""
        self._write_guard_base = base

    def close(self) -> None:
        if getattr(self, "handle", None):
            self._kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "ProcessMemory":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def read(self, address: int, size: int) -> bytes:
        buffer = (ctypes.c_ubyte * size)()
        read = ctypes.c_size_t(0)
        ok = self._kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(read)
        )
        if not ok or read.value != size:
            raise AttachError(f"ReadProcessMemory({address:#x}, {size}) failed")
        return bytes(buffer)

    def write(self, address: int, data: bytes) -> None:
        if self._write_guard_base is not None:
            assert_write_allowed(self._write_guard_base, address, len(data))
        old = ctypes.c_ulong(0)
        self._kernel32.VirtualProtectEx(
            self.handle, ctypes.c_void_p(address), len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old)
        )
        written = ctypes.c_size_t(0)
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        ok = self._kernel32.WriteProcessMemory(
            self.handle, ctypes.c_void_p(address), buffer, len(data), ctypes.byref(written)
        )
        self._kernel32.VirtualProtectEx(
            self.handle, ctypes.c_void_p(address), len(data), old, ctypes.byref(old)
        )
        if not ok or written.value != len(data):
            raise AttachError(f"WriteProcessMemory({address:#x}, {len(data)}) failed")

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def write_u32(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def write_u64(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<Q", value))


_LOG_BASE = re.compile(r"base_virtual_addr\s*\.*:\s*0x([0-9A-Fa-f]+)")


def logged_eboot_base(log_text: str) -> int | None:
    """The most recent eboot base shadPS4 recorded, or None.

    A logged base is a *hint*: the CE table validates it against the hook
    originals and falls back to a signature scan, and so must any port. A stale
    v0.17 base was live-observed being accepted by an earlier probe.
    """
    pending = False
    found: int | None = None
    for line in log_text.splitlines():
        if "Loading module eboot.bin" in line:
            pending = True
            continue
        if pending:
            match = _LOG_BASE.search(line)
            if match:
                found = int(match.group(1), 16)
                pending = False
    return found


def default_shad_log() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "shadPS4" / "log" / "shad_log.txt"


def verify_base(memory: ProcessMemory, base: int) -> bool:
    """Both hook originals must be present at the candidate base."""
    for _name, rva, text in ASSERTS[:2]:
        if not parse(text).matches(memory.read(base + rva, len(parse(text)))):
            return False
    return True


def run_asserts(memory: ProcessMemory, base: int) -> list[AssertResult]:
    results = []
    for name, rva, text in ASSERTS:
        expected = parse(text)
        actual = memory.read(base + rva, len(expected))
        results.append(AssertResult(name, rva, expected, actual, expected.matches(actual)))
    return results


def require_validated_image(memory: ProcessMemory, base: int) -> None:
    """Fail closed unless every assert matches.

    CUSA00900 and every other serial or app version land here and are refused:
    the recorded contract is CUSA03173 01.09 only, and a partial match is a
    different image, not a near-enough one.
    """
    failures = [result for result in run_asserts(memory, base) if not result.ok]
    if failures:
        detail = "; ".join(
            f"{result.name}@+{result.rva:#x} expected [{result.expected.to_text()}] "
            f"got [{result.actual.hex(' ').upper()}]"
            for result in failures
        )
        raise ImageMismatch(
            "refusing to patch: this is not the validated CUSA03173 01.09 image. " + detail
        )


class StaleRequest(AttachError):
    """The state cell was armed when we attached. Refuse; do not add to it."""


#: The 16-byte head of the state block: request / quantity / result / done.
REQUEST_HEAD_SIZE = 0x10


def read_request_cell(memory: ProcessMemory, base: int) -> tuple[bytes, bytes]:
    """(state head, staged descriptor) as raw bytes, for printing."""
    return (
        memory.read(base + payload.STATE_RVA, REQUEST_HEAD_SIZE),
        memory.read(base + payload.DESCRIPTOR_RVA, STAGED_SIZE),
    )


def request_is_armed(state_head: bytes) -> bool:
    """True when the cave would pick this request up on its next fire.

    ``observed`` (issue #144): the cave arms on ``bbAutoRequest != 0`` and clears
    it itself, so the request word alone decides. ``done``/``result`` are left
    set by a *completed* grant and the descriptor keeps its last contents, so
    demanding an all-zero block here would refuse every second legitimate grant.
    """
    return struct.unpack_from("<I", state_head, 0x00)[0] != 0


def format_request_cell(state_head: bytes, descriptor_bytes: bytes) -> str:
    return (
        f"  state_region  +{payload.STATE_RVA:#x}  {state_head.hex(' ').upper()}\n"
        f"  descriptor    +{payload.DESCRIPTOR_RVA:#x}  {descriptor_bytes.hex(' ').upper()}"
    )


STALE_REQUEST_GUIDANCE = (
    "A request is still armed in the state cell. The next consume hook the "
    "player triggers in game would execute it -- that is the landmine in issue "
    "#144, and queueing a second grant on top of it is how it detonates.\n"
    "Either re-run the original grant with the same --tag (the durable ledger "
    "replays it and decides 'already applied' instead of granting twice), or "
    "re-run with --clear-stale-request to zero the cell first."
)


def require_idle_request_cell(memory: ProcessMemory, base: int) -> None:
    """Fail closed when the state cell is armed on attach."""
    state_head, descriptor_bytes = read_request_cell(memory, base)
    if request_is_armed(state_head):
        raise StaleRequest(
            "refusing to proceed: the native request cell is not idle.\n"
            + format_request_cell(state_head, descriptor_bytes)
            + "\n"
            + STALE_REQUEST_GUIDANCE
        )


def clear_stale_request(memory: ProcessMemory, base: int) -> tuple[bytes, bytes]:
    """Disarm the cell and return the bytes that were there.

    Safe to write externally: both the state block and the descriptor live
    inside the eboot image at ``eboot+0x50DBxxx``, which issue #144 established
    is not protection-tracked (``observed``).

    The state block is restored to the freshly-installed
    :func:`payload.state_region` bytes rather than zeroed outright -- a zero fill
    would also wipe ``bbAutoSlotIndex = FFFFFFFF`` and the heartbeat descriptor
    that the heartbeat cave reads every frame.
    """
    before = read_request_cell(memory, base)
    blob = payload.state_region()
    memory.write(base + blob.rva, blob.data)
    memory.write(base + payload.DESCRIPTOR_RVA, bytes(STAGED_SIZE))
    return before


def install(
    memory: ProcessMemory,
    base: int,
    *,
    dry_run: bool = True,
    controller: ThreadController | None = None,
    attempt_budget: int = DEFAULT_ATTEMPT_BUDGET,
) -> list[tuple[str, int, int]]:
    """Write the static payload. Inert unless ``dry_run=False``.

    Ordering is the safety contract (see docs/INSTALL-ATOMICITY.md). The state
    region and both caves are written first; only then are the two ``E9`` detours
    written, and they are the commit point -- nothing in the guest jumps to a cave
    until a detour exists, so everything before the detours is harmless. The
    structural half of this ordering is pinned by ``payload.blobs()`` and its
    test ``test_install_order_writes_the_caves_before_the_detours``.

    The heartbeat hook executes every frame, so writing its detour is not atomic
    against a guest thread mid-fetch. When arming, the two detours are therefore
    committed through :func:`threadcontrol.install_detours_atomically`: suspend
    every guest thread, verify no RIP is inside either seven-byte window, write
    both detours under that one suspend, resume. Arming requires a ``controller``;
    without one this fails closed rather than write a detour blind. The live
    suspend/RIP read is the only piece untested against the game (owner checklist
    item 5a).
    """
    require_validated_image(memory, base)

    all_blobs = payload.blobs()
    detours = [blob for blob in all_blobs if blob.name.endswith("_detour")]
    prelude = [blob for blob in all_blobs if not blob.name.endswith("_detour")]

    plan = [(blob.name, base + blob.rva, len(blob.relocated(base))) for blob in all_blobs]
    if dry_run:
        return plan

    if controller is None:
        raise AttachError(
            "refusing to arm without a thread controller: writing the heartbeat "
            "detour without suspending guest threads is the unsolved atomicity "
            "hazard. Pass a ThreadController (see threadcontrol.py)."
        )

    # Caves and state first -- fully written before either detour (the commit point).
    for blob in prelude:
        memory.write(base + blob.rva, blob.relocated(base))

    windows = [PatchWindow(base + blob.rva, len(blob.data)) for blob in detours]

    def write_detours() -> None:
        for blob in detours:
            memory.write(base + blob.rva, blob.relocated(base))

    install_detours_atomically(controller, windows, write_detours, attempt_budget=attempt_budget)
    return plan
