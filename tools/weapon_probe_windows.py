"""Read-only Windows process access for the weapon instance probe.

This module deliberately exposes no process-memory write or remote-execution API.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Iterable


PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MEM_COMMIT = 0x1000


class ProbeError(RuntimeError):
    """An expected, user-actionable probe failure."""


if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wintypes.DWORD),
            ("PartitionId", wintypes.WORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wintypes.DWORD),
            ("Protect", wintypes.DWORD),
            ("Type", wintypes.DWORD),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    kernel32.VirtualQueryEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(MEMORY_BASIC_INFORMATION),
        ctypes.c_size_t,
    ]
    kernel32.VirtualQueryEx.restype = ctypes.c_size_t
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


def _require_windows() -> None:
    if sys.platform != "win32":
        raise ProbeError("The weapon probe can only read a process on Windows.")


def _winerror(prefix: str) -> ProbeError:
    error = ctypes.get_last_error()
    return ProbeError(f"{prefix}: {ctypes.WinError(error)}")


def iter_processes() -> Iterable[tuple[int, str]]:
    """Yield process IDs and executable names using the Toolhelp API."""
    _require_windows()
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise _winerror("Could not enumerate processes")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            raise _winerror("Could not read the process list")
        while True:
            yield int(entry.th32ProcessID), entry.szExeFile
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != 18:  # ERROR_NO_MORE_FILES
                    raise _winerror("Could not continue reading the process list")
                break
    finally:
        kernel32.CloseHandle(snapshot)


def find_shadps4_pid() -> int:
    matches = [(pid, name) for pid, name in iter_processes() if name.casefold() == "shadps4.exe"]
    if not matches:
        raise ProbeError("shadPS4.exe is not running. Start one game instance, load your save, and try again.")
    if len(matches) != 1:
        pids = ", ".join(str(pid) for pid, _ in matches)
        raise ProbeError(f"Found {len(matches)} shadPS4.exe processes ({pids}). Close extras and keep exactly one running.")
    return matches[0][0]


class ProcessMemory:
    """A context-managed process handle that can only query and read memory."""

    def __init__(self, pid: int):
        _require_windows()
        self.pid = int(pid)
        access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
        self._handle = kernel32.OpenProcess(access, False, self.pid)
        if not self._handle:
            raise _winerror(f"Could not open process {self.pid} for read-only inspection")

    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "ProcessMemory":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def read(self, address: int, size: int) -> bytes:
        address, size = int(address), int(size)
        if address < 0 or size < 0:
            raise ValueError("address and size must be non-negative")
        if size == 0:
            return b""
        buffer = (ctypes.c_ubyte * size)()
        count = ctypes.c_size_t()
        ok = kernel32.ReadProcessMemory(
            self._handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(count)
        )
        if not ok or count.value != size:
            raise _winerror(f"Could not read {size} bytes at 0x{address:X}")
        return bytes(buffer)

    read_bytes = read

    def query(self, address: int) -> dict[str, int]:
        info = MEMORY_BASIC_INFORMATION()
        result = kernel32.VirtualQueryEx(
            self._handle, ctypes.c_void_p(int(address)), ctypes.byref(info), ctypes.sizeof(info)
        )
        if result != ctypes.sizeof(info):
            raise _winerror(f"Could not query memory at 0x{int(address):X}")
        return {
            "base_address": int(info.BaseAddress or 0),
            "allocation_base": int(info.AllocationBase or 0),
            "region_size": int(info.RegionSize),
            "state": int(info.State),
            "protect": int(info.Protect),
            "type": int(info.Type),
        }


_BASE_VALUE = re.compile(r"base_virtual_addr\s*\.*\s*:\s*0x([0-9a-fA-F]+)", re.I)


def default_log_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ProbeError("APPDATA is unavailable; choose shad_log.txt manually.")
    return Path(appdata) / "shadPS4" / "log" / "shad_log.txt"


def bases_from_log(path: str | os.PathLike[str]) -> list[int]:
    log_path = Path(path)
    if not log_path.is_file():
        raise ProbeError(f"shadPS4 log was not found: {log_path}")
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ProbeError(f"Could not read shadPS4 log {log_path}: {exc}") from exc
    found: list[int] = []
    awaiting_base = False
    for line in text.splitlines():
        if "Loading module eboot.bin" in line:
            awaiting_base = True
            continue
        if awaiting_base:
            match = _BASE_VALUE.search(line)
            if match:
                found.append(int(match.group(1), 16))
                awaiting_base = False
    if not found:
        raise ProbeError(f"No eboot Loading module/base_virtual_addr entry was found in {log_path}.")
    # Only the latest logged load belongs to the current game session. An older
    # address is unsafe to treat as a fallback even though it is still validated.
    return [found[-1]]


def resolve_base(memory: ProcessMemory, log_path: str | os.PathLike[str], verify: Callable[[ProcessMemory, int], object]) -> int:
    failures: list[str] = []
    for base in bases_from_log(log_path):
        try:
            verdict = verify(memory, base)
            if verdict is not False:
                return base
            failures.append(f"0x{base:X}: signature did not match")
        except Exception as exc:
            failures.append(f"0x{base:X}: {exc}")
    detail = "; ".join(failures)
    raise ProbeError(f"The logged eboot base could not be validated. {detail}")


def self_test() -> dict[str, object]:
    """Read an owned buffer through the same read-only process handle."""
    _require_windows()
    expected = b"weapon-probe-read-only-self-test\x00"
    local = ctypes.create_string_buffer(expected)
    with ProcessMemory(os.getpid()) as memory:
        actual = memory.read(ctypes.addressof(local), len(expected))
        region = memory.query(ctypes.addressof(local))
    if actual != expected or region["state"] != MEM_COMMIT:
        raise ProbeError("Read-only API self-test returned unexpected data.")
    return {"ok": True, "pid": os.getpid(), "bytes_read": len(actual), "access": "PROCESS_VM_READ|PROCESS_QUERY_INFORMATION"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="read this process using the production Windows APIs")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("only --self-test is supported")
    try:
        result = self_test()
    except Exception as exc:
        print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"SELF-TEST OK: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
