"""One-click GUI for a read-only shadPS4 weapon diagnostic capture."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import threading
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import weapon_probe_windows as windows


def output_directory() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def unique_zip_path(directory: Path, now: datetime) -> Path:
    stem = f"weapon-probe-{now.astimezone().strftime('%Y%m%d-%H%M%S')}"
    candidate = directory / f"{stem}.zip"
    number = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{number}.zip"
        number += 1
    return candidate


def capture_package(observation: str, log_path: str) -> tuple[Path, bool, str]:
    now = datetime.now(timezone.utc)
    record: dict[str, object] = {
        "schema": "bb-weapon-instance-probe-v1",
        "captured_at": now.isoformat(),
        "operator_control": {
            "reported_weapon_and_displayed_level": observation.strip(),
            "review_status": "pending_review",
            "mode": "read_only",
            "can_control_game": False,
            "claim": "Operator-entered control; not an automatic pass.",
        },
        "status": "error",
    }
    success = False
    message = "Capture failed"
    try:
        core = importlib.import_module("weapon_probe_core")
        pid = windows.find_shadps4_pid()
        record["process"] = {"name": "shadPS4.exe", "pid": pid}
        with windows.ProcessMemory(pid) as memory:
            base = windows.resolve_base(memory, log_path, core.verify_base)
            record["eboot_base"] = f"0x{base:X}"
            payload = core.capture(memory, base)
        if not isinstance(payload, dict):
            raise TypeError("weapon_probe_core.capture() must return a JSON object")
        record["status"] = payload.get("status", "captured")
        record["capture"] = payload
        success = record["status"] == "captured"
        message = "Capture completed" if success else "Capture incomplete; send the bundle for review. It is not a diagnosis."
    except Exception as exc:
        record["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        message = str(exc) or type(exc).__name__

    destination = unique_zip_path(output_directory(), now)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result.json", encoded)
    return destination, success, message


class ProbeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bloodborne Weapon Diagnostic")
        self.geometry("680x430")
        self.minsize(600, 390)
        self.last_output: Path | None = None
        try:
            initial_log = str(windows.default_log_path())
        except windows.ProbeError:
            initial_log = ""
        self.log_path = tk.StringVar(value=initial_log)
        self.observation = tk.StringVar()
        self.status = tk.StringVar(value="Ready — read-only; the tool cannot control the game.")
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Weapon instance diagnostic", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=("Run the AP client in an ordinary connected session so its held-inventory cache is hydrated. "
                  "Load your save, stand still, and do not attack while capturing. Keep exactly one shadPS4 "
                  "instance open. This tool only reads memory and cannot control the game."),
            wraplength=620,
            justify="left",
        ).pack(anchor="w", pady=(8, 18))

        ttk.Label(frame, text="Tonitrus level and another known-working weapon level (required)").pack(anchor="w")
        entry = ttk.Entry(frame, textvariable=self.observation)
        entry.pack(fill="x", pady=(4, 14))
        entry.focus_set()

        ttk.Label(frame, text="shadPS4 log").pack(anchor="w")
        log_row = ttk.Frame(frame)
        log_row.pack(fill="x", pady=(4, 18))
        ttk.Entry(log_row, textvariable=self.log_path).pack(side="left", fill="x", expand=True)
        ttk.Button(log_row, text="Browse…", command=self._browse).pack(side="left", padx=(8, 0))

        self.capture_button = ttk.Button(frame, text="Capture diagnostic", command=self._start_capture)
        self.capture_button.pack(fill="x", ipady=8)
        ttk.Label(frame, textvariable=self.status, wraplength=620, justify="left").pack(anchor="w", pady=(16, 8))
        self.open_button = ttk.Button(frame, text="Open output folder", command=self._open_folder, state="disabled")
        self.open_button.pack(anchor="w")

    def _browse(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose shadPS4 log",
            initialdir=str(Path(self.log_path.get()).parent) if self.log_path.get() else None,
            filetypes=[("shadPS4 log", "*.txt"), ("All files", "*.*")],
        )
        if chosen:
            self.log_path.set(chosen)

    def _start_capture(self) -> None:
        observation = self.observation.get().strip()
        if not observation:
            messagebox.showerror("Observation required", "Enter the displayed Tonitrus level and another known-working weapon's level.")
            return
        if not self.log_path.get().strip():
            messagebox.showerror("Log required", "Choose shad_log.txt before capturing.")
            return
        self.capture_button.configure(state="disabled")
        self.status.set("Capturing… Stay still and do not attack. Read-only access; no game control.")
        threading.Thread(target=self._capture_worker, args=(observation, self.log_path.get().strip()), daemon=True).start()

    def _capture_worker(self, observation: str, log_path: str) -> None:
        try:
            result = capture_package(observation, log_path)
        except Exception as exc:
            self.after(0, self._finish_unpacked_error, str(exc) or type(exc).__name__)
            return
        self.after(0, self._finish_capture, *result)

    def _finish_unpacked_error(self, message: str) -> None:
        self.capture_button.configure(state="normal")
        self.status.set(f"Could not create result ZIP: {message}")
        messagebox.showerror("Capture failed", self.status.get())

    def _finish_capture(self, path: Path, success: bool, message: str) -> None:
        self.last_output = path
        self.capture_button.configure(state="normal")
        self.open_button.configure(state="normal")
        if success:
            self.status.set(f"Capture complete: {path}")
            messagebox.showinfo("Capture complete", f"Saved diagnostic ZIP:\n{path}")
        elif message.startswith("Capture incomplete"):
            self.status.set(f"Capture incomplete; bundle saved for review: {path}")
            messagebox.showwarning("Capture incomplete", f"{message}\n\nSaved diagnostic ZIP:\n{path}")
        else:
            self.status.set(f"Capture failed; details saved in {path}: {message}")
            messagebox.showerror("Capture failed", self.status.get())

    def _open_folder(self) -> None:
        folder = self.last_output.parent if self.last_output else output_directory()
        os.startfile(str(folder))


def _safe_print(message: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream)


def _write_self_test_result(path: str, result: dict[str, object]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run the read-only Windows API self-test")
    parser.add_argument("--self-test-result", metavar="PATH", help="write self-test JSON here (useful for windowed/frozen builds)")
    parser.add_argument("--capture", action="store_true", help="capture without opening the GUI")
    parser.add_argument("--observation", help="Tonitrus level and another known-working weapon level")
    parser.add_argument("--log", help="path to shad_log.txt")
    args = parser.parse_args()
    if args.self_test and args.capture:
        parser.error("--self-test and --capture cannot be used together")
    if args.self_test:
        try:
            result = windows.self_test()
            result["status"] = "passed"
            if args.self_test_result:
                _write_self_test_result(args.self_test_result, result)
            _safe_print(json.dumps(result, indent=2))
            return 0
        except Exception as exc:
            result = {"ok": False, "status": "failed", "error": str(exc) or type(exc).__name__}
            if args.self_test_result:
                try:
                    _write_self_test_result(args.self_test_result, result)
                except Exception as write_exc:
                    result["result_write_error"] = str(write_exc)
            _safe_print(f"SELF-TEST FAILED: {json.dumps(result)}", error=True)
            return 1
    if args.self_test_result:
        parser.error("--self-test-result requires --self-test")
    if args.capture:
        if not args.observation or not args.observation.strip():
            parser.error("--capture requires --observation")
        log_path = args.log
        if not log_path:
            try:
                log_path = str(windows.default_log_path())
            except windows.ProbeError as exc:
                parser.error(str(exc))
        try:
            path, success, message = capture_package(args.observation, log_path)
        except Exception as exc:
            _safe_print(f"Could not create result ZIP: {exc}", error=True)
            return 1
        _safe_print(json.dumps({"path": str(path), "captured": success, "message": message}))
        return 0 if success else 2
    if args.observation or args.log:
        parser.error("--observation and --log require --capture")
    ProbeApp().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
