"""Run Archipelago generation and a localhost server without a shell.

This module treats an Archipelago installation as read-only with exactly one
exception, and that exception is never silent: :func:`install_bloodborne_world`
copies the ``bloodborne.apworld`` this package ships into the installation's
``custom_worlds`` directory, and only when the player asks for it from the UI.
Nothing else here writes into the installation. Discovering that Bloodborne is
missing or incompatible still produces an actionable diagnostic
(:class:`BloodborneWorldUnavailable`), which now says *which* of the two it is
so the caller can offer "install" or "update" rather than a wall of prose.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .core import ValidationError
from .resources import application_root, resource_root


OutputCallback = Callable[[str], None]


@dataclass(frozen=True)
class APTools:
    root: Path
    generate_command: tuple[str, ...]
    server_command: tuple[str, ...]


@dataclass(frozen=True)
class GenerationResult:
    archive: Path
    output_directory: Path
    log_path: Path


class GenerationCancelled(ValidationError):
    pass


class BloodborneWorldUnavailable(ValidationError):
    """The selected Archipelago install cannot generate this launcher's seeds.

    ``reason`` separates the two cases a caller has to offer different words
    for: ``"missing"`` (no Bloodborne world at all) and ``"mismatch"`` (a
    Bloodborne world of the wrong version). The UI turns that into "Install
    Bloodborne world" or "Update Bloodborne world to X".
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        expected_version: str = "",
        installed_version: str = "",
        path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.expected_version = expected_version
        self.installed_version = installed_version
        self.path = path

    @property
    def missing(self) -> bool:
        return self.reason == "missing"

    @property
    def mismatch(self) -> bool:
        return self.reason == "mismatch"


def _packaged_ap_tools(root: Path) -> tuple[Path, Path] | None:
    generate = root / "ArchipelagoGenerate.exe"
    server = root / "ArchipelagoServer.exe"
    return (generate, server) if generate.is_file() and server.is_file() else None


def _source_ap_tools(root: Path) -> tuple[Path, Path] | None:
    generate = root / "Generate.py"
    server = root / "MultiServer.py"
    return (generate, server) if generate.is_file() and server.is_file() else None


def is_archipelago_root(ap_root: Path | str) -> bool:
    """Whether this folder is an Archipelago install the launcher recognises.

    The same packaged/source detection :func:`discover_ap_tools` runs, without
    its Python-executable requirement: installing a world into a source
    checkout does not need an interpreter chosen first.
    """
    root = Path(ap_root).expanduser().resolve()
    return bool(_packaged_ap_tools(root) or _source_ap_tools(root))


def discover_ap_tools(ap_root: Path | str, python_executable: Path | str | None = None) -> APTools:
    """Resolve packaged AP tools, or an explicitly selected source checkout.

    Source execution is opt-in because importing AP with an arbitrary Python is
    fragile.  A frozen launcher cannot safely use its embedded interpreter.
    """
    root = Path(ap_root).expanduser().resolve()
    packaged = _packaged_ap_tools(root)
    if packaged is not None:
        generate_exe, server_exe = packaged
        return APTools(root, (str(generate_exe),), (str(server_exe),))

    source = _source_ap_tools(root)
    generate_py = root / "Generate.py"
    server_py = root / "MultiServer.py"
    if source is not None and python_executable is not None:
        python = Path(python_executable).expanduser().resolve()
        if not python.is_file():
            raise ValidationError(f"the selected Python executable does not exist: {python}")
        return APTools(root, (str(python), str(generate_py)), (str(python), str(server_py)))
    if source is not None and not getattr(sys, "frozen", False):
        return APTools(root, (sys.executable, str(generate_py)), (sys.executable, str(server_py)))

    detail = " Select a Python executable for this source checkout." if generate_py.is_file() else ""
    raise ValidationError(
        f"{root} does not contain ArchipelagoGenerate.exe and ArchipelagoServer.exe."
        f" Choose the extracted Archipelago install folder.{detail}"
    )


def _read_world_manifest(path: Path) -> Mapping[str, object] | None:
    try:
        if path.is_dir():
            return json.loads((path / "archipelago.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(path) as package:
            names = {name.replace("\\", "/"): name for name in package.namelist()}
            member = names.get("bloodborne/archipelago.json") or names.get("archipelago.json")
            return json.loads(package.read(member).decode("utf-8-sig")) if member else None
    except (OSError, KeyError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile):
        return None


def validate_bloodborne_world(
    ap_root: Path | str, *, expected_manifest: Mapping[str, object] | None = None
) -> Mapping[str, object]:
    """Verify the selected AP install already has the expected Bloodborne world."""
    root = Path(ap_root).expanduser().resolve()
    if expected_manifest is None:
        manifest_path = resource_root() / "worlds" / "bloodborne" / "archipelago.json"
        try:
            expected_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"the launcher cannot read its Bloodborne version metadata: {exc}") from exc
    expected_world = str(expected_manifest.get("world_version", ""))
    candidates = (
        root / "custom_worlds" / "bloodborne.apworld",
        root / "worlds" / "bloodborne",
        root / "lib" / "worlds" / "bloodborne",
    )
    package = next(((path, _read_world_manifest(path)) for path in candidates if path.exists()), None)
    if package is None or package[1] is None:
        raise BloodborneWorldUnavailable(
            "Bloodborne generation support was not found in the selected Archipelago install. "
            "This launcher ships the matching bloodborne.apworld and can install it into "
            f"{root / 'custom_worlds'} for you.",
            reason="missing",
            expected_version=expected_world,
            path=root,
        )
    path, actual = package
    expected_ap = str(expected_manifest.get("minimum_ap_version", ""))
    if actual.get("game") != "Bloodborne" or str(actual.get("world_version", "")) != expected_world:
        raise BloodborneWorldUnavailable(
            f"{path} is not the Bloodborne world version this launcher expects "
            f"({actual.get('world_version', 'unknown')} installed; {expected_world} required). "
            "This launcher ships the matching bloodborne.apworld and can install it for you.",
            reason="mismatch",
            expected_version=expected_world,
            installed_version=str(actual.get("world_version", "")),
            path=path,
        )
    # minimum_ap_version describes the world's floor, not the installed AP
    # version.  Comparing this manifest field still catches mismatched builds;
    # probing AP itself is intentionally left to a future supported version API.
    if expected_ap and str(actual.get("minimum_ap_version", "")) != expected_ap:
        raise BloodborneWorldUnavailable(
            f"{path} targets Archipelago {actual.get('minimum_ap_version', 'unknown')} or newer; "
            f"this launcher package expects {expected_ap}. This launcher ships the matching "
            "bloodborne.apworld and can install it for you.",
            reason="mismatch",
            expected_version=expected_world,
            installed_version=str(actual.get("world_version", "")),
            path=path,
        )
    return actual


def bundled_apworld_path() -> Path:
    """Return the ``bloodborne.apworld`` this build installs.

    The packaged location is ``<package>/worlds/bloodborne.apworld``, resolved
    from :func:`application_root` exactly like ``tools/bb-ap-client.exe``. A
    source checkout has no package layout, so ``build/bloodborne.apworld`` --
    what ``./build.ps1 -Apworld`` writes -- is accepted there instead. The
    packaged path is returned either way when neither exists, so a caller's
    error message names the file the package is supposed to carry.
    """
    root = application_root()
    packaged = root / "worlds" / "bloodborne.apworld"
    if packaged.is_file():
        return packaged
    if not getattr(sys, "frozen", False):
        built = root / "build" / "bloodborne.apworld"
        if built.is_file():
            return built
    return packaged


# ArchipelagoLauncher enumerates and imports worlds once, at start. Installing
# a world under a running Archipelago changes nothing that process can see, and
# the resulting "my world is still missing" is indistinguishable from a failed
# copy -- so every caller says this, unconditionally, rather than guessing at
# process state it cannot read reliably.
RESTART_NOTICE = (
    "Archipelago loads its worlds at start: if Archipelago or ArchipelagoLauncher "
    "is open, close and reopen it before generating."
)


def install_bloodborne_world(ap_root: Path | str) -> Path:
    """Install this package's ``bloodborne.apworld`` into ``ap_root``.

    Returns the installed path. The copy is atomic (temporary file plus
    replace) so an interrupted install cannot leave a half-written world where
    a working one was, and it is verified by re-running
    :func:`validate_bloodborne_world` before returning.

    A *source* Archipelago install that carries Bloodborne under ``worlds/`` or
    ``lib/worlds/`` is refused rather than shadowed: that checkout is the thing
    to update, and an apworld next to it would leave two versions on disk.
    """
    root = Path(ap_root).expanduser().resolve()
    if not is_archipelago_root(root):
        raise ValidationError(
            f"{root} is not an Archipelago installation, so there is nowhere to install the "
            "Bloodborne world. Choose the extracted Archipelago folder."
        )
    for existing in (root / "worlds" / "bloodborne", root / "lib" / "worlds" / "bloodborne"):
        if existing.is_dir():
            raise ValidationError(
                f"{existing} is a source install of the Bloodborne world. Update that checkout "
                "instead; installing an .apworld beside it would leave two versions installed."
            )
    source = bundled_apworld_path()
    if not source.is_file():
        raise ValidationError(
            f"this launcher build does not carry a bloodborne.apworld ({source} is missing). "
            "Download bloodborne.apworld from the release and install it with ArchipelagoLauncher, "
            "or, from a checkout, run ./build.ps1 -Apworld first."
        )
    destination_directory = root / "custom_worlds"
    destination = destination_directory / "bloodborne.apworld"
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
        staged = destination_directory / f".bloodborne.apworld.{uuid.uuid4().hex}.part"
        try:
            shutil.copyfile(source, staged)
            os.replace(staged, destination)
        finally:
            if staged.exists():
                staged.unlink()
    except OSError as exc:
        raise ValidationError(f"could not install {source} into {destination_directory}: {exc}") from exc
    validate_bloodborne_world(root)
    return destination


def _run_streaming(
    command: list[str], *, cwd: Path, on_output: OutputCallback | None,
    cancel: threading.Event | None, log_path: Path, cancel_timeout: float = 5.0,
) -> int:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )
    assert process.stdout is not None
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    reader = threading.Thread(target=read_output, name="archipelago-generation-output", daemon=True)
    reader.start()
    cancellation_started: float | None = None
    killed = False
    try:
        with log_path.open("w", encoding="utf-8", newline="\n") as log:
            while True:
                if cancel is not None and cancel.is_set() and process.poll() is None:
                    if cancellation_started is None:
                        cancellation_started = time.monotonic()
                        process.terminate()
                    elif not killed and time.monotonic() - cancellation_started >= cancel_timeout:
                        process.kill()
                        killed = True
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    # Grandchildren can inherit the pipe and keep it open.  The
                    # process status, rather than EOF alone, bounds cancellation.
                    if process.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                cleaned = line.rstrip("\r\n")
                log.write(cleaned + "\n")
                log.flush()
                if on_output:
                    on_output(cleaned)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            code = process.wait(timeout=cancel_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait(timeout=cancel_timeout)
    if cancel is not None and cancel.is_set():
        raise GenerationCancelled(f"Archipelago generation was cancelled; log: {log_path}")
    return code


def _contains_multidata(archive: Path) -> bool:
    try:
        with zipfile.ZipFile(archive) as bundle:
            return any(not item.is_dir() and item.filename.lower().endswith(".archipelago") for item in bundle.infolist())
    except (OSError, zipfile.BadZipFile):
        return False


def generate_seed(
    tools: APTools,
    player_files: Path | str,
    output_root: Path | str,
    *,
    on_output: OutputCallback | None = None,
    cancel: threading.Event | None = None,
) -> GenerationResult:
    players = Path(player_files).expanduser().resolve()
    if not players.is_dir():
        raise ValidationError(f"the player YAML folder does not exist: {players}")
    run = Path(output_root).expanduser().resolve() / f"generation-{uuid.uuid4().hex}"
    run.mkdir(parents=True, exist_ok=False)
    command = [*tools.generate_command, "--player_files_path", str(players), "--outputpath", str(run)]
    log_path = run / "generation.log"
    code = _run_streaming(
        command, cwd=tools.root, on_output=on_output, cancel=cancel, log_path=log_path
    )
    if code:
        raise ValidationError(f"Archipelago generation failed with exit code {code}; log: {log_path}")
    archives = sorted(run.glob("*.zip"))
    if len(archives) != 1:
        raise ValidationError(
            f"generation produced {len(archives)} zip files in {run}; expected exactly one; log: {log_path}"
        )
    archive = archives[0]
    if not _contains_multidata(archive):
        raise ValidationError(
            f"{archive.name} is not a hostable AP seed: it contains no .archipelago multidata; log: {log_path}"
        )
    return GenerationResult(archive, run, log_path)


class LocalServer:
    def __init__(self, process: subprocess.Popen[str], output_thread: threading.Thread, log_path: Path):
        self.process = process
        self._output_thread = output_thread
        self.log_path = log_path

    @property
    def running(self) -> bool:
        return self.process.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        if self.process.poll() is not None:
            return
        forced = False
        try:
            if self.process.stdin is not None:
                self.process.stdin.write("/exit\n")
                self.process.stdin.flush()
            self.process.wait(timeout=timeout)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            forced = True
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self._output_thread.join(timeout=timeout)
        if forced:
            raise ValidationError(
                f"Archipelago Server did not accept or finish graceful shutdown and was forced closed; "
                f"its latest save may be incomplete. Log: {self.log_path}"
            )


def start_server(
    tools: APTools,
    seed_zip: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 38281,
    on_output: OutputCallback | None = None,
    startup_timeout: float = 60.0,
) -> LocalServer:
    archive = Path(seed_zip).expanduser().resolve()
    if not archive.is_file() or not _contains_multidata(archive):
        raise ValidationError(f"the selected seed is not a hostable Archipelago zip: {archive}")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValidationError("local hosting must bind to localhost")
    if not 1 <= port <= 65535:
        raise ValidationError("server port must be between 1 and 65535")
    # Fail before spawning so an existing service cannot be mistaken for the
    # server represented by the returned handle.  MultiServer remains the
    # authority at bind time; this check only makes the common conflict clear.
    for family, socktype, proto, _canonname, address in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        probe = socket.socket(family, socktype, proto)
        try:
            if sys.platform == "win32":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(address)
        except OSError as exc:
            raise ValidationError(
                f"localhost port {port} is already in use; choose another port"
            ) from exc
        finally:
            probe.close()
    log_path = archive.parent / f"server-{uuid.uuid4().hex}.log"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    process = subprocess.Popen(
        [*tools.server_command, str(archive), "--host", host, "--port", str(port)],
        cwd=tools.root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )

    ready = threading.Event()

    def forward() -> None:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8", newline="\n") as log:
            for line in process.stdout:
                cleaned = line.rstrip("\r\n")
                log.write(cleaned + "\n")
                log.flush()
                if on_output:
                    on_output(cleaned)
                if re.search(rf"\bserver listening on .+:{port}\b", cleaned, re.IGNORECASE):
                    ready.set()

    thread = threading.Thread(target=forward, name="archipelago-server-output", daemon=True)
    thread.start()
    deadline = time.monotonic() + startup_timeout
    while not ready.wait(0.05):
        code = process.poll()
        if code is not None:
            thread.join(timeout=1.0)
            raise ValidationError(
                f"Archipelago Server exited during startup with code {code}; log: {log_path}"
            )
        if time.monotonic() >= deadline:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
            thread.join(timeout=1.0)
            raise ValidationError(
                f"Archipelago Server did not bind localhost:{port} within {startup_timeout:g} seconds; "
                f"log: {log_path}"
            )
    return LocalServer(process, thread, log_path)
