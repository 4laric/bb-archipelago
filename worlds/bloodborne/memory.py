"""Read-only access to a running shadPS4 process.

Nothing in this module writes to the target. It resolves shadPS4's exported
``g_eboot_address``, dereferences it for the guest image base, and verifies the
published hook sites against their recorded bytes.

The design boundary matters: everything above ``ProcessReader`` is pure and
testable anywhere, and only ``Win32ProcessReader`` touches Windows. That is
deliberate — the parsing is where the bugs live, and it must not require the
game to exercise.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Protocol

EBOOT_BASE_SYMBOL = "g_eboot_address"

# Observed on every capture so far, and hardcoded by shadPS4 itself since
# PR #2879. Used only as a fallback when the export cannot be resolved, and
# reported as such — never silently.
FALLBACK_GUEST_BASE = 0x800000000


class ProcessReader(Protocol):
    """The whole I/O surface. Implementations must not write."""

    def read(self, address: int, size: int) -> bytes:
        """Return exactly ``size`` bytes, or raise ``MemoryReadError``."""


class MemoryReadError(RuntimeError):
    pass


class ImageParseError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Hook sites
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HookSite:
    """A published hook site, eboot-relative.

    ``expected`` is a prefix, not the full 16 bytes, because that is what the
    sources actually record. ``evidence`` uses the vocabulary in
    docs/RESEARCH-BASELINE.md: an instruction transcribed from a cheat table is
    ``published``; bytes we have actually read back are ``observed``; an
    encoding derived from a disassembly listing is ``inferred`` and must not be
    treated as a match failure until someone confirms it.
    """

    name: str
    offset: int
    expected: bytes | None
    evidence: str
    note: str = ""


HOOK_SITES: tuple[HookSite, ...] = (
    HookSite("hp", 0x1BFC5F7, bytes.fromhex("8b97f8000000"), "inferred",
             "encoding derived from `mov edx,[rdi+0xF8]`; not yet read back"),
    HookSite("blood_echoes", 0x190029B, bytes.fromhex("898a94000000"), "published",
             "assert() in the capture tables"),
    HookSite("stamina", 0x18F78DB, bytes.fromhex("8b8034010000"), "published",
             "assert() in the capture tables"),
    HookSite("frenzy", 0x1901FB4, bytes.fromhex("8bb384000000"), "published",
             "assert() in the capture tables"),
    HookSite("consumable_quantity", 0x14D9556, bytes.fromhex("4189c444896308"), "published",
             "original bytes recorded in RESEARCH-BASELINE.md"),
    HookSite("one_hit", 0x1A0D47B, None, "unrecorded",
             "site is published but no expected bytes exist anywhere in the repo"),
    # Not one of the six published sites, but the two the grant harness patches.
    # Verifying them is what tells a tester whether the harness will install.
    HookSite("consume_hook_return", 0x14D9575, bytes.fromhex("4489e04883c428"), "published",
             "assert() in the grant harness"),
    HookSite("heartbeat_hook", 0x1BFE882, bytes.fromhex("4881c4e8070000"), "published",
             "assert() in the grant harness"),
)


@dataclass(frozen=True)
class SiteResult:
    site: HookSite
    address: int
    actual: bytes
    matched: bool | None   # None == nothing recorded to compare against

    @property
    def status(self) -> str:
        if self.matched is None:
            return "uncheckable"
        return "ok" if self.matched else "MISMATCH"


def verify_sites(reader: ProcessReader, guest_base: int,
                 sites: tuple[HookSite, ...] = HOOK_SITES) -> list[SiteResult]:
    results = []
    for site in sites:
        address = guest_base + site.offset
        actual = reader.read(address, 16)
        matched = None if site.expected is None else actual.startswith(site.expected)
        results.append(SiteResult(site, address, actual, matched))
    return results


def summarise(results: list[SiteResult]) -> str:
    ok = sum(1 for r in results if r.matched is True)
    bad = sum(1 for r in results if r.matched is False)
    unknown = sum(1 for r in results if r.matched is None)
    parts = [f"{ok}/{ok + bad} verified"]
    if bad:
        parts.append(f"{bad} MISMATCHED")
    if unknown:
        parts.append(f"{unknown} with no recorded bytes")
    return ", ".join(parts)


# --------------------------------------------------------------------------
# PE export resolution
# --------------------------------------------------------------------------

def resolve_export(reader: ProcessReader, module_base: int, symbol: str) -> int:
    """Return the virtual address of ``symbol`` exported by the module.

    Walks the loaded image in the target process, so every offset here is an
    RVA relative to ``module_base``.
    """
    if reader.read(module_base, 2) != b"MZ":
        raise ImageParseError("module does not start with MZ")
    e_lfanew = struct.unpack("<I", reader.read(module_base + 0x3C, 4))[0]
    pe = module_base + e_lfanew
    if reader.read(pe, 4) != b"PE\0\0":
        raise ImageParseError("PE signature not found")

    # COFF header is 20 bytes; the optional header follows.
    opt = pe + 4 + 20
    magic = struct.unpack("<H", reader.read(opt, 2))[0]
    if magic == 0x20B:          # PE32+
        data_dir = opt + 112
    elif magic == 0x10B:        # PE32
        data_dir = opt + 96
    else:
        raise ImageParseError(f"unknown optional header magic 0x{magic:X}")

    export_rva, export_size = struct.unpack("<II", reader.read(data_dir, 8))
    if not export_rva:
        raise ImageParseError("module has no export directory")

    directory = module_base + export_rva
    number_of_names = struct.unpack("<I", reader.read(directory + 0x18, 4))[0]
    functions_rva = struct.unpack("<I", reader.read(directory + 0x1C, 4))[0]
    names_rva = struct.unpack("<I", reader.read(directory + 0x20, 4))[0]
    ordinals_rva = struct.unpack("<I", reader.read(directory + 0x24, 4))[0]

    target = symbol.encode("ascii")
    for i in range(number_of_names):
        name_rva = struct.unpack("<I", reader.read(module_base + names_rva + i * 4, 4))[0]
        if _read_cstring(reader, module_base + name_rva) != target:
            continue
        ordinal = struct.unpack("<H", reader.read(module_base + ordinals_rva + i * 2, 2))[0]
        function_rva = struct.unpack("<I", reader.read(module_base + functions_rva + ordinal * 4, 4))[0]
        # A forwarder RVA points back inside the export directory. We do not
        # follow them; g_eboot_address is a data export and never forwarded.
        if export_rva <= function_rva < export_rva + export_size:
            raise ImageParseError(f"{symbol} is a forwarder export")
        return module_base + function_rva
    raise ImageParseError(f"{symbol} not found among {number_of_names} exported names")


def _read_cstring(reader: ProcessReader, address: int, limit: int = 256) -> bytes:
    out = bytearray()
    while len(out) < limit:
        chunk = reader.read(address + len(out), 16)
        if b"\0" in chunk:
            out += chunk[:chunk.index(b"\0")]
            return bytes(out)
        out += chunk
    raise ImageParseError("unterminated export name")


@dataclass(frozen=True)
class BaseResolution:
    guest_base: int
    source: str          # "export" or "fallback"
    detail: str

    @property
    def trustworthy(self) -> bool:
        return self.source == "export"


def resolve_guest_base(reader: ProcessReader, module_base: int) -> BaseResolution:
    """Resolve the guest image base, preferring the export over the constant.

    Falling back is allowed but never silent — the caller is expected to say so
    on the connect banner, because "it worked on my machine with the hardcoded
    base" is precisely the claim this is here to stop being invisible.
    """
    try:
        address = resolve_export(reader, module_base, EBOOT_BASE_SYMBOL)
        value = struct.unpack("<Q", reader.read(address, 8))[0]
    except (ImageParseError, MemoryReadError) as exc:
        return BaseResolution(FALLBACK_GUEST_BASE, "fallback",
                              f"{EBOOT_BASE_SYMBOL} unresolved ({exc}); using the hardcoded base")
    if value == 0:
        return BaseResolution(FALLBACK_GUEST_BASE, "fallback",
                              f"{EBOOT_BASE_SYMBOL} read as 0; the game is probably not loaded yet")
    return BaseResolution(value, "export", f"{EBOOT_BASE_SYMBOL} at 0x{address:X}")


# --------------------------------------------------------------------------
# Windows implementation — the only part that needs the real OS
# --------------------------------------------------------------------------

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400


class Win32ProcessReader:
    """``ProcessReader`` over ``ReadProcessMemory``. Opened read-only."""

    def __init__(self, pid: int):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.OpenProcess.restype = wintypes.HANDLE
        self._k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        handle = self._k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            raise MemoryReadError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
        self._handle = handle
        self.pid = pid

    def read(self, address: int, size: int) -> bytes:
        ctypes = self._ctypes
        buffer = (ctypes.c_char * size)()
        read = ctypes.c_size_t(0)
        ok = self._k32.ReadProcessMemory(self._handle, ctypes.c_void_p(address),
                                        buffer, ctypes.c_size_t(size), ctypes.byref(read))
        if not ok or read.value != size:
            raise MemoryReadError(
                f"ReadProcessMemory(0x{address:X}, {size}) failed: {ctypes.get_last_error()}")
        return bytes(buffer)

    def close(self) -> None:
        if getattr(self, "_handle", None):
            self._k32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "Win32ProcessReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def find_shadps4(process_name: str = "shadPS4.exe") -> tuple[int, int]:
    """Return ``(pid, module_base)`` for a running shadPS4.

    Uses the ToolHelp snapshot API rather than psutil so the client keeps no
    dependency Archipelago does not already have.
    """
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    TH32CS_SNAPMODULE = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    class MODULEENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                    ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                    ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    wanted = process_name.encode("ascii").lower()

    snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pid = None
    try:
        entry = PROCESSENTRY32(); entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        found = k32.Process32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.lower() == wanted:
                pid = entry.th32ProcessID
                break
            found = k32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snapshot)
    if pid is None:
        raise MemoryReadError(f"no running process named {process_name}")

    snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    try:
        module = MODULEENTRY32(); module.dwSize = ctypes.sizeof(MODULEENTRY32)
        if not k32.Module32First(snapshot, ctypes.byref(module)):
            raise MemoryReadError(f"could not enumerate modules of pid {pid}")
        base = ctypes.cast(module.modBaseAddr, ctypes.c_void_p).value
    finally:
        k32.CloseHandle(snapshot)
    return pid, int(base)


@dataclass(frozen=True)
class AttachReport:
    """Everything worth putting on a connect banner."""

    pid: int
    module_base: int
    base: BaseResolution
    results: list[SiteResult]

    def lines(self) -> list[str]:
        out = [
            f"shadPS4 pid {self.pid}, module base 0x{self.module_base:X}",
            f"guest base 0x{self.base.guest_base:X} via {self.base.source} — {self.base.detail}",
            f"hook sites: {summarise(self.results)}",
        ]
        for r in self.results:
            if r.matched is False:
                out.append(f"  MISMATCH {r.site.name} @ 0x{r.address:X}: "
                           f"expected {r.site.expected.hex(' ')}..., got {r.actual.hex(' ')}")
            elif r.matched is None:
                out.append(f"  no recorded bytes for {r.site.name} @ 0x{r.address:X}: "
                           f"{r.actual.hex(' ')}")
        if not self.base.trustworthy:
            out.append("  the guest base was NOT resolved from the export; treat any "
                       "site result above as unconfirmed")
        return out


def attach_and_verify(process_name: str = "shadPS4.exe") -> AttachReport:
    pid, module_base = find_shadps4(process_name)
    reader = Win32ProcessReader(pid)
    try:
        base = resolve_guest_base(reader, module_base)
        results = verify_sites(reader, base.guest_base)
    finally:
        reader.close()
    return AttachReport(pid, module_base, base, results)


if __name__ == "__main__":  # pragma: no cover - manual smoke test on Windows
    for line in attach_and_verify().lines():
        print(line)
