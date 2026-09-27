"""Read-only paired-process telemetry with operator markers; no game hooks.

Usage: python -m tools.coop_diagnostics record --host-pid 123 --guest-pid 456
       --output work/coop/run.jsonl --duration 600
In that console: `mark A bell_before`, `mark B bell_after`, or `stop`.
This records sampled OS/GPU metrics, not FPS, event flags, or game events.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time


def stamp() -> dict:
    return {"time_ms": time.time_ns() // 1_000_000, "monotonic_ns": time.monotonic_ns()}


def sha256(path: str | Path) -> str:
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def parse_gpu_csv(text: str) -> list[dict]:
    names = ("index", "uuid", "name", "memory_total_mib", "memory_used_mib",
             "utilization_percent", "temperature_c", "power_w")
    result = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != len(names):
            raise ValueError("Unexpected nvidia-smi column count")
        gpu = dict(zip(names, (value.strip() for value in row)))
        for key in names[3:]:
            raw = gpu[key]
            try:
                number = float(raw)
                gpu[key] = number if math.isfinite(number) else None
            except ValueError:
                gpu[key] = None
        result.append(gpu)
    if not result:
        raise ValueError("nvidia-smi returned no GPUs")
    return result


def snapshot(process_ids: list[int]) -> dict:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        raise RuntimeError("PowerShell is required")
    command = [shell, "-NoProfile", "-NonInteractive", "-File",
               str(Path(__file__).with_name("coop_resource_snapshot.ps1")),
               "-ProcessIds", ",".join(map(str, process_ids))]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(command, capture_output=True, text=True, timeout=15,
                            creationflags=flags, check=True)
    data = json.loads(result.stdout.lstrip("\ufeff"))
    nvidia = shutil.which("nvidia-smi")
    if nvidia is None:
        data["gpu"] = {"status": "unavailable", "error": "nvidia-smi not found"}
    else:
        try:
            result = subprocess.run(
                [nvidia, "--query-gpu=index,uuid,name,memory.total,memory.used,"
                 "utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True, creationflags=flags)
            data["gpu"] = {"status": "ok", "devices": parse_gpu_csv(result.stdout)}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            data["gpu"] = {"status": "unavailable", "error": str(error)}
    return data


def identify(data: dict, roles: dict[str, int]) -> dict:
    by_pid = {item["pid"]: item for item in data["processes"]}
    identities = {}
    for role, process_id in roles.items():
        item = by_pid.get(process_id, {})
        if item.get("status") != "ok" or not item.get("started_utc") or not item.get("executable"):
            raise ValueError(f"Cannot identify {role} PID {process_id}; stop before testing")
        identities[role] = {key: item[key] for key in ("pid", "name", "started_utc", "executable")}
        identities[role]["executable_sha256"] = sha256(item["executable"])
    return identities


def check_identity(data: dict, identities: dict) -> str | None:
    by_pid = {item["pid"]: item for item in data["processes"]}
    for role, identity in identities.items():
        item = by_pid.get(identity["pid"], {})
        if item.get("status") != "ok":
            return f"{role}: process exited or telemetry became unavailable"
        if any(item.get(key) != identity[key] for key in ("started_utc", "executable")):
            return f"{role}: PID identity changed"
    return None


class Recorder:
    def __init__(self, stream):
        self.stream = stream
        self.sequence = 0

    def write(self, kind: str, *, timestamp: dict | None = None, **fields):
        self.sequence += 1
        entry = {"type": kind, "seq": self.sequence, **(timestamp or stamp()), **fields}
        self.stream.write(json.dumps(entry, allow_nan=False) + "\n")
        self.stream.flush()


def read_commands(commands: queue.Queue):
    for line in sys.stdin:
        commands.put((stamp(), line.strip()))
    commands.put((stamp(), "stop"))


def drain_commands(commands: queue.Queue, recorder: Recorder) -> bool:
    while True:
        try:
            timestamp, line = commands.get_nowait()
        except queue.Empty:
            return False
        if line == "stop":
            recorder.write("marker", timestamp=timestamp, role="operator", label="stop")
            return True
        pieces = line.split(maxsplit=2)
        if len(pieces) == 3 and pieces[0] == "mark" and pieces[1] in ("A", "B", "both", "operator"):
            recorder.write("marker", timestamp=timestamp, role=pieces[1], label=pieces[2])
        else:
            recorder.write("invalid_command", timestamp=timestamp, text=line)
            print("Use: mark A|B|both|operator <label>, or stop", flush=True)


def record(args) -> int:
    roles = {"A": args.host_pid}
    if args.guest_pid is not None:
        roles["B"] = args.guest_pid
    if len(set(roles.values())) != len(roles) or min(roles.values()) <= 0:
        raise ValueError("Use distinct positive PIDs")
    if not (math.isfinite(args.interval) and args.interval >= 2):
        raise ValueError("Interval must be finite and at least two seconds")
    if not (math.isfinite(args.duration) and 0 < args.duration <= 1800):
        raise ValueError("Duration must be between zero and 1800 seconds")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental destruction of an earlier capture.
    with args.output.open("x", encoding="utf-8") as stream:
        recorder = Recorder(stream)
        recorder.write("header", schema=1, roles=roles, interval_s=args.interval,
                       duration_s=args.duration, scope="OS samples; not a game-event probe",
                       logger_sha256=sha256(__file__),
                       sampler_sha256=sha256(Path(__file__).with_name("coop_resource_snapshot.ps1")))
        try:
            initial = snapshot(list(roles.values()))
            identities = identify(initial, roles)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            recorder.write("probe_install_failed", error=str(error))
            return 2
        recorder.write("ready", identities=identities, initial=initial)
        commands = queue.Queue()
        threading.Thread(target=read_commands, args=(commands,), daemon=True).start()
        print(f"Recording to {args.output}. Use mark A|B|both|operator <label>, or stop.", flush=True)
        start = time.monotonic()
        due = start
        reason = "duration_elapsed"
        exit_code = 0
        try:
            while time.monotonic() - start < args.duration:
                if drain_commands(commands, recorder):
                    reason = "operator_stop"
                    break
                now = time.monotonic()
                if now < due:
                    time.sleep(min(0.1, due - now))
                    continue
                began = stamp()
                data = snapshot(list(roles.values()))
                identity_error = check_identity(data, identities)
                recorder.write("sample", timestamp=began, finished=stamp(),
                               scheduler_lag_s=max(0, now - due),
                               sample_duration_s=(time.monotonic_ns() - began["monotonic_ns"]) / 1e9,
                               **data)
                if identity_error:
                    recorder.write("diagnostic_failure", error=identity_error)
                    reason, exit_code = "process_identity_failure", 2
                    break
                # Do not burst to catch up. Mark unobserved polling slots explicitly.
                due += args.interval
                skipped = max(0, math.ceil((time.monotonic() - due) / args.interval))
                if skipped:
                    recorder.write("sampling_gap", skipped_poll_slots=skipped,
                                   meaning="Unobserved OS sampling slots, not missed game calls")
                    due += skipped * args.interval
        except KeyboardInterrupt:
            reason = "keyboard_interrupt"
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            recorder.write("diagnostic_failure", error=str(error))
            reason, exit_code = "sampler_failure", 2
        finally:
            drain_commands(commands, recorder)
            recorder.write("footer", reason=reason, exit_code=exit_code)
        return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("record")
    capture.add_argument("--host-pid", type=int, required=True)
    capture.add_argument("--guest-pid", type=int)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--interval", type=float, default=5)
    capture.add_argument("--duration", type=float, default=600)
    args = parser.parse_args()
    try:
        return record(args)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
