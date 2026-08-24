"""One-shot preflight of the whole player chain (bb-archipelago#103).

The first end-to-end player run failed serially, one error per attempt,
across nine distinct root causes -- each knowable up front, each costing a
full build/launch cycle to discover. This module checks every link in the
chain in one pass and renders a single PASS/WARN/FAIL list with a remedy per
failure, so the player is no longer the integration test.

Like readiness.py this module never writes anything; unlike readiness.py it
is a gate, not a status panel: it reports FAIL for anything that would
refuse or mis-build a launch. Every external probe (process scan, server
socket) is injectable so the tests stay dependency-free.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .core import (
    SUPPRESSION_PATH,
    GameInstall,
    LauncherError,
    ProcessSpec,
    ValidationError,
    elevation_risks,
    launcher_is_elevated,
    sha256_file,
    validate_processes,
)
from .workflow import (
    LauncherSettings,
    ProcessPlan,
    _read_object,
    _request_identity,
    load_process_plan,
)

PASS = "pass"
WARN = "warn"
FAIL = "fail"
SKIP = "skip"

SUPPRESSION_MANIFEST_FORMAT = "bb-vanilla-suppression-build-v1"
SUPPRESSION_OUTPUT_RELATIVE = "param/gameparam/gameparam.parambnd.dcx"

# shadPS4 blocks overlay activation outright; the other two are the processes
# that held files or the wrong privilege token during the first player run.
BLOCKING_PROCESS = "shadps4.exe"
_BBLAUNCHER_REMEDY = (
    "the third-party BBLauncher spawns shadPS4 elevated; if you use it, "
    "this launcher and the AP client must also run as administrator or the "
    "client cannot attach"
)

WARNING_PROCESSES = (
    (
        "cheatengine.exe",
        "a stray Cheat Engine instance can hold the grant table or stale "
        "bridge state; close any CE window you did not just open for this session",
    ),
    ("bblauncher.exe", _BBLAUNCHER_REMEDY),
    ("bb-launcher.exe", _BBLAUNCHER_REMEDY),  # alternate spelling of the same tool
)


@dataclass(frozen=True)
class DoctorFinding:
    status: str
    name: str
    detail: str
    remedy: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    findings: tuple[DoctorFinding, ...]

    def count(self, status: str) -> int:
        return sum(finding.status == status for finding in self.findings)

    @property
    def ok(self) -> bool:
        return self.count(FAIL) == 0

    @property
    def summary(self) -> str:
        return (
            f"{self.count(PASS)} passed, {self.count(WARN)} warning(s), "
            f"{self.count(FAIL)} failed, {self.count(SKIP)} skipped"
        )


@dataclass
class _Chain:
    """Validated intermediate state later checks build on."""

    install: GameInstall | None = None
    request: dict[str, Any] | None = None
    plan: ProcessPlan | None = None
    processes: list[ProcessSpec] | None = None


def _process_running(name: str) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return name.casefold() in result.stdout.casefold()
    proc = Path("/proc")
    if proc.is_dir():
        for command in proc.glob("[0-9]*/comm"):
            try:
                if command.read_text(encoding="utf-8").strip().casefold() == name.casefold():
                    return True
            except OSError:
                pass
    return False


def _probe_server(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=2.0):
        pass


def _check_install(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    try:
        chain.install = GameInstall.from_root(settings.game_root)
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "game installation",
            str(exc),
            "point the shadPS4 game folder at the directory holding CUSA03173, "
            "either with its CUSA03173-patch (01.09) update directory or as a "
            "merged 01.09 dump on its own",
        )
    return DoctorFinding(
        PASS,
        "game installation",
        f"CUSA03173 01.09 at {chain.install.root}",
    )


def _check_request(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    try:
        chain.request = _request_identity(settings.ap_request.expanduser().resolve())
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "AP seed request",
            str(exc),
            "select the *.bbenemizer.json the generator dropped beside your seed "
            "zip; if it predates world-version tagging, regenerate the seed",
        )
    request = chain.request
    return DoctorFinding(
        PASS,
        "AP seed request",
        f"slot {request['slot']}, runtime {request['runtime_build']}, "
        f"world {request['world_build']}",
    )


def _check_plan(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    try:
        chain.plan = load_process_plan(settings.process_plan)
        chain.processes = validate_processes(chain.plan.processes)
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "launch plan",
            str(exc),
            "use Generate Launch Plan (or python -m bb_launcher plan) against "
            "the current executables; a hash mismatch means a component was "
            "updated after the plan was pinned",
        )
    names = ", ".join(spec.name for spec in chain.processes)
    return DoctorFinding(
        PASS,
        "launch plan",
        f"{len(chain.processes)} process(es) pinned and present: {names}",
    )


def _check_slot_agreement(chain: _Chain, player_name: str | None) -> DoctorFinding:
    if chain.request is None:
        return DoctorFinding(SKIP, "request slot agreement", "upstream check failed")
    slot = chain.request["slot"]
    entered = (player_name or "").strip()
    if not entered:
        return DoctorFinding(
            WARN,
            "request slot agreement",
            f"the AP seed request is for slot {slot!r}; no player name entered to verify against",
            "enter your AP player name so the Doctor can confirm the request is "
            "yours; in a multi-Bloodborne multiworld the launcher can auto-pick "
            "another player's request file",
        )
    if entered != slot:
        return DoctorFinding(
            FAIL,
            "request slot agreement",
            f"the AP seed request is for slot {slot!r} but you entered {entered!r}",
            "select YOUR own <seed>_P<number>_<name>.bbenemizer.json from the seed "
            "output; launching with another player's request connects you as their "
            "slot and steals their checks",
        )
    return DoctorFinding(
        PASS, "request slot agreement", f"slot {slot!r} matches the entered player name"
    )


def _check_runtime_agreement(chain: _Chain) -> DoctorFinding:
    if chain.request is None or chain.plan is None:
        return DoctorFinding(SKIP, "runtime build agreement", "upstream check failed")
    wanted = chain.request["runtime_build"]
    found = chain.plan.runtime_build
    if wanted != found:
        return DoctorFinding(
            FAIL,
            "runtime build agreement",
            f"the AP seed requires runtime {wanted}, the launch plan supplies {found}",
            "regenerate the launch plan against the current AP seed request",
        )
    return DoctorFinding(PASS, "runtime build agreement", wanted)


def _check_suppression_chain(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    if chain.request is None:
        return DoctorFinding(SKIP, "suppression binder and manifest", "upstream check failed")
    binder = settings.suppression_binder.expanduser().resolve()
    manifest_path = settings.suppression_manifest.expanduser().resolve()
    if not binder.is_file() or binder.is_symlink():
        return DoctorFinding(
            FAIL,
            "suppression binder and manifest",
            f"suppression binder is not a regular file: {binder}",
            "build it with tools/build_vanilla_suppression.ps1 or select the "
            "packaged gameparam.parambnd.dcx",
        )
    try:
        manifest = _read_object(manifest_path, "suppression build manifest")
        if manifest.get("format") != SUPPRESSION_MANIFEST_FORMAT:
            raise ValidationError("suppression build manifest has the wrong format")
        if manifest.get("output_relative_path") != SUPPRESSION_OUTPUT_RELATIVE:
            raise ValidationError("suppression manifest output path is not the gameparam binder")
        expected_plan = chain.request["suppression_plan_sha256"]
        if manifest.get("plan_sha256") != expected_plan:
            raise ValidationError("suppression build plan hash does not match the AP seed")
        output_hash = sha256_file(binder)
        if manifest.get("output_gameparam_sha256") != output_hash:
            raise ValidationError("suppression binder hash does not match its build manifest")
        if manifest.get("source_gameparam_sha256") == output_hash:
            raise ValidationError(
                "suppression binder is byte-identical to vanilla; refusing an unsuppressed build"
            )
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "suppression binder and manifest",
            str(exc),
            "binder and manifest must come from the same suppression build; "
            "if the seed was regenerated, rebuild the binder for its plan hash",
        )
    return DoctorFinding(
        PASS,
        "suppression binder and manifest",
        f"binder {output_hash[:12]} matches manifest, plan {expected_plan[:12]} matches the seed",
    )


def _check_installed_gameparam(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    if chain.install is None:
        return DoctorFinding(SKIP, "installed gameparam", "upstream check failed")
    try:
        manifest = _read_object(
            settings.suppression_manifest.expanduser().resolve(), "suppression build manifest"
        )
        source_expected = manifest.get("source_gameparam_sha256")
        output_expected = manifest.get("output_gameparam_sha256")
        if not isinstance(source_expected, str) or not isinstance(output_expected, str):
            raise ValidationError("suppression manifest is missing its source/output hashes")
        backend, source_path = chain.install.resolve_file(SUPPRESSION_PATH, include_mods=False)
    except LauncherError as exc:
        return DoctorFinding(
            SKIP,
            "installed gameparam",
            f"not checked: {exc}",
        )
    actual = sha256_file(source_path)
    if actual == source_expected:
        return DoctorFinding(
            PASS,
            "installed gameparam",
            f"{backend}-layer {source_path} is the vanilla source the suppression build was made from",
        )
    if actual == output_expected:
        return DoctorFinding(
            FAIL,
            "installed gameparam",
            f"the {backend}-layer {source_path} IS the suppressed binder -- this "
            "installation was already modified outside the launcher",
            "restore the untouched 01.09 gameparam.parambnd.dcx (re-dump or "
            "re-copy the patch) before building or launching",
        )
    return DoctorFinding(
        FAIL,
        "installed gameparam",
        f"the {backend}-layer {source_path} matches neither the vanilla source "
        f"nor the suppressed build (found {actual[:12]})",
        "something outside this toolchain modified the game files; restore a "
        "clean 01.09 installation before building or launching",
    )


def _check_map_studio(
    settings: LauncherSettings, chain: _Chain, *, randomize_enemies: bool
) -> DoctorFinding:
    if not randomize_enemies:
        return DoctorFinding(SKIP, "MapStudio source", "enemy randomization is off")
    candidate = settings.map_studio_source
    if candidate is None and chain.install is not None:
        relative = Path("dvdroot_ps4") / "map" / "MapStudio"
        for _name, backend in chain.install.content_backends():
            found = backend / relative
            if found.is_dir():
                candidate = found
                break
    if candidate is None or not candidate.is_dir():
        return DoctorFinding(
            FAIL,
            "MapStudio source",
            "no source MapStudio selected and none found in the game installation",
            "select the installed map\\MapStudio directory (the patch layer's "
            "compressed *.msb.dcx set) or turn enemy randomization off",
        )
    maps = [
        path
        for path in candidate.iterdir()
        if path.is_file() and path.name.lower().endswith((".msb", ".msb.dcx"))
    ]
    if not maps:
        return DoctorFinding(
            FAIL,
            "MapStudio source",
            f"{candidate} contains no .msb/.msb.dcx files",
            "select the installed compressed MapStudio set, not a miner output directory",
        )
    return DoctorFinding(
        PASS, "MapStudio source", f"{len(maps)} map(s) under {candidate}"
    )


def _check_server(
    chain: _Chain,
    server: str | None,
    probe: Callable[[str, int], None],
) -> DoctorFinding:
    address = server
    if not address and chain.processes:
        for spec in chain.processes:
            if spec.name == "AP client" and spec.arguments:
                address = spec.arguments[0]
                break
    if not address:
        return DoctorFinding(
            SKIP, "AP server", "no server address in the launch plan and none supplied"
        )
    host, separator, raw_port = address.rpartition(":")
    if not separator or not host or not raw_port.isdigit():
        return DoctorFinding(
            FAIL,
            "AP server",
            f"cannot parse server address {address!r}",
            "use host:port, e.g. localhost:38281",
        )
    try:
        probe(host, int(raw_port))
    except (ConnectionRefusedError, OSError) as exc:
        if isinstance(exc, (socket.timeout, TimeoutError, socket.gaierror)):
            return DoctorFinding(
                WARN,
                "AP server",
                f"no answer from {address} within the probe timeout ({exc})",
                "a firewall may block the probe; the client connect is the real test",
            )
        return DoctorFinding(
            FAIL,
            "AP server",
            f"nothing is listening on {address} ({exc})",
            "start MultiServer with the seed zip first, and check the port: the "
            "client reports a wrong port only as 'a full error is available "
            "elsewhere'",
        )
    return DoctorFinding(PASS, "AP server", f"{address} accepted a connection")


def _check_item_grants(chain: _Chain) -> DoctorFinding:
    names = {spec.name for spec in chain.processes or ()}
    if "CE bridge" in names:
        return DoctorFinding(
            PASS, "item grants", "Cheat Engine bridge pinned: items can be delivered"
        )
    return DoctorFinding(
        WARN,
        "item grants",
        "no Cheat Engine bridge in the launch plan",
        "regenerate the launch plan with Cheat Engine and the grant table "
        "(Generate Launch Plan): without it your checks still reach the "
        "server, but no items can be delivered into your game",
    )


def _check_elevation(chain: _Chain, process_running: Callable[[str], bool]) -> DoctorFinding:
    if launcher_is_elevated():
        return DoctorFinding(
            PASS,
            "elevation",
            "launcher is running as administrator and can attach to an elevated shadPS4",
        )
    shad = None
    for spec in chain.processes or ():
        if spec.name == "shadPS4":
            shad = spec.executable
    risks = elevation_risks(shad, process_running)
    if risks:
        return DoctorFinding(
            WARN,
            "elevation",
            "; ".join(risks),
            "restart this launcher as administrator: an unelevated AP client "
            "cannot attach to an elevated shadPS4 and will wait forever",
        )
    return DoctorFinding(PASS, "elevation", "no elevated shadPS4 launch path detected")


def _check_processes(process_running: Callable[[str], bool]) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []
    if process_running(BLOCKING_PROCESS):
        findings.append(
            DoctorFinding(
                FAIL,
                "blocking processes",
                "shadPS4 is already running",
                "close it before launching: overlay activation refuses to touch "
                "the installation while the game runs, and a client started "
                "against the wrong boot state cannot verify the save",
            )
        )
    else:
        findings.append(
            DoctorFinding(PASS, "blocking processes", "shadPS4 is not running")
        )
    for name, remedy in WARNING_PROCESSES:
        if process_running(name):
            findings.append(
                DoctorFinding(WARN, f"running process {name}", f"{name} is running", remedy)
            )
    return findings


def _safely(check: Callable[[], DoctorFinding]) -> DoctorFinding:
    """A doctor that crashes on the ninth failure mode has learned nothing."""

    try:
        return check()
    except Exception as exc:  # noqa: BLE001 -- the report must survive anything
        return DoctorFinding(FAIL, "doctor internal", f"{type(exc).__name__}: {exc}")


def run_doctor(
    settings: LauncherSettings,
    *,
    randomize_enemies: bool = True,
    server: str | None = None,
    player_name: str | None = None,
    process_running: Callable[[str], bool] | None = None,
    probe: Callable[[str, int], None] | None = None,
) -> DoctorReport:
    """Check every link in the player chain. Never raises for bad state."""

    process_running = process_running or _process_running
    probe = probe or _probe_server
    chain = _Chain()
    findings = [
        _safely(lambda: _check_install(settings, chain)),
        _safely(lambda: _check_request(settings, chain)),
        _safely(lambda: _check_slot_agreement(chain, player_name)),
        _safely(lambda: _check_plan(settings, chain)),
        _safely(lambda: _check_item_grants(chain)),
        _safely(lambda: _check_runtime_agreement(chain)),
        _safely(lambda: _check_suppression_chain(settings, chain)),
        _safely(lambda: _check_installed_gameparam(settings, chain)),
        _safely(lambda: _check_map_studio(settings, chain, randomize_enemies=randomize_enemies)),
        _safely(lambda: _check_server(chain, server, probe)),
        _safely(lambda: _check_elevation(chain, process_running)),
    ]
    try:
        findings.extend(_check_processes(process_running))
    except Exception as exc:  # noqa: BLE001
        findings.append(DoctorFinding(FAIL, "blocking processes", f"{type(exc).__name__}: {exc}"))
    return DoctorReport(tuple(findings))


_MARKERS = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", SKIP: "SKIP"}


def format_report(report: DoctorReport) -> str:
    """Render the findings as one line each, ASCII-safe for any console."""

    lines: list[str] = []
    for finding in report.findings:
        lines.append(f"[{_MARKERS[finding.status]}] {finding.name}: {finding.detail}")
        if finding.remedy:
            lines.append(f"       -> {finding.remedy}")
    lines.append(f"Doctor: {report.summary}")
    return "\n".join(lines)
