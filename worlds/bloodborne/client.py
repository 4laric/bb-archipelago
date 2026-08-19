"""File bridge between Archipelago and the validated Cheat Engine grant harness."""
from __future__ import annotations
import argparse, asyncio, json, logging
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled,
                          handle_url_arg, server_loop)
from NetUtils import ClientStatus
from Utils import async_start
from . import (
    GAME,
    GOAL_LOCATION_KEY,
    ITEM_ID_BY_KEY,
    LOCATION_ID_BY_KEY,
    NETWORK_LOCATIONS,
    RUNTIME_BUILD,
    WORLD_VERSION,
)
from .runtime_bindings import DELIVERY_FIXTURES, ITEM_BINDINGS

logger = logging.getLogger("BloodborneClient")
ITEM_KEY_BY_AP_ID = {value: key for key, value in ITEM_ID_BY_KEY.items()}
LOCATION_BY_NAME = {
    loc.name.casefold(): LOCATION_ID_BY_KEY[loc.key] for loc in NETWORK_LOCATIONS
}
LOCATION_NAME_BY_ID = {
    LOCATION_ID_BY_KEY[loc.key]: loc.name for loc in NETWORK_LOCATIONS
}
CHECK_JOURNAL = "manual-checks.jsonl"
BRIDGE_PROTOCOL = "BBGRANT1"
HARNESS_VERSION = "bb-native-grant-v5"
BRIDGE_TIMEOUT_SECONDS = 30
TERMINAL_GRANT_STATES = {"failed", "command_rejected", "quantity_mismatch", "setup_error", "write_error"}


def location_suggestions(query: str, limit: int = 3) -> list[str]:
    """Return player-facing names closest to an unsuccessful `/check` query."""
    matches = get_close_matches(query.strip().casefold(), LOCATION_BY_NAME, n=limit, cutoff=0.45)
    return [LOCATION_NAME_BY_ID[LOCATION_BY_NAME[match]] for match in matches]


def journal_check(work_dir: Path, location: int) -> None:
    """Append one durable, machine-readable record for a manual location check."""
    work_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "location_name": LOCATION_NAME_BY_ID[location],
        "location_id": location,
        "world_version": WORLD_VERSION,
    }
    with (work_dir / CHECK_JOURNAL).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def attach_report_lines() -> list[str]:
    """Read-only shadPS4 inspection, or an explanation of why it could not run.

    Never raises. A client that cannot attach is still a usable client — manual
    checks and the file bridge both work without it — so this reports and
    carries on rather than refusing to start.
    """
    try:
        from .memory import attach_and_verify
        return attach_and_verify().lines()
    except Exception as exc:                      # noqa: BLE001 - reporting, not handling
        return [f"shadPS4 not inspected: {type(exc).__name__}: {exc}"]


class BloodborneCommandProcessor(ClientCommandProcessor):
    def _cmd_check(self, *parts: str) -> bool:
        """Manually report a check: /check <exact location name>."""
        query = " ".join(parts).strip()
        location = LOCATION_BY_NAME.get(query.casefold())
        if location is None:
            suggestions = location_suggestions(query)
            suffix = f" Did you mean: {'; '.join(suggestions)}?" if suggestions else ""
            self.output(f"Unknown location.{suffix} Use /missing for exact names.")
            return False
        try:
            journal_check(self.ctx.work_dir, location)
        except OSError as exc:
            logger.warning("Could not journal manual check: %s", exc)
        async_start(self.ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location]}]))
        if location == LOCATION_ID_BY_KEY[GOAL_LOCATION_KEY]:
            async_start(self.ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))
        return True

    def _cmd_shadps4(self) -> bool:
        """Re-inspect the running shadPS4 process: guest base and hook sites."""
        for line in attach_report_lines():
            self.output(line)
        return True


class BloodborneContext(CommonContext):
    game = GAME
    command_processor = BloodborneCommandProcessor
    items_handling = 0b111
    def __init__(self, server_address, password, work_dir: Path):
        super().__init__(server_address, password)
        self.work_dir = work_dir
    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

def read_state(path: Path) -> dict[str, str]:
    if not path.exists(): return {}
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)

def grant_command(item_id: int, tag: str | None = None) -> str | None:
    key = ITEM_KEY_BY_AP_ID.get(item_id)
    binding = ITEM_BINDINGS.get(key) if key else None
    if item_id == 0xBB0100:
        key, binding = "blood_vial", DELIVERY_FIXTURES["blood_vial"]
    if not key or not binding or binding.normalized_item_id is None or binding.raw_descriptor is None:
        return None
    command_tag = tag or key
    if not command_tag or any(character.isspace() for character in command_tag):
        raise ValueError("grant tag must be one non-empty token")
    return (f"{BRIDGE_PROTOCOL} GRANT 0x{binding.raw_descriptor:08X} "
            f"0x{binding.normalized_item_id:08X} 1 AUTO {command_tag}\n")


def grant_state_outcome(state: dict[str, str], tag: str) -> str:
    """Classify only a state written by this protocol for this receipt tag."""
    if (state.get("build") != RUNTIME_BUILD
            or state.get("protocol") != BRIDGE_PROTOCOL
            or state.get("harness") != HARNESS_VERSION):
        return "incompatible"
    if state.get("tag") != tag:
        return "pending"
    if state.get("status") in {"completed", "recovered_complete"}:
        return "success"
    if state.get("status") in TERMINAL_GRANT_STATES:
        return "failure"
    return "pending"

async def bridge_loop(ctx: BloodborneContext) -> None:
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    command, state_path = ctx.work_dir / "native-grant-command.txt", ctx.work_dir / "native-grant-state.txt"
    receipt = ctx.work_dir / "ap-client-state.json"
    delivered = 0
    while not ctx.seed_name and not ctx.exit_event.is_set(): await asyncio.sleep(.25)
    receipt_key = f"{ctx.seed_name}:{ctx.slot}"
    if receipt.exists():
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            delivered = int(saved.get("delivered", 0)) if saved.get("slot_key") == receipt_key else 0
        except (ValueError, OSError, json.JSONDecodeError): logger.warning("Ignoring invalid receipt")
    while not ctx.exit_event.is_set():
        if delivered < len(ctx.items_received):
            tag = f"received_{delivered}"
            line = grant_command(ctx.items_received[delivered].item, tag)
            if line is None:
                logger.error("Unsupported item; delivery paused")
                await asyncio.sleep(1); continue
            state = read_state(state_path)
            outcome = grant_state_outcome(state, tag)
            if outcome == "incompatible":
                logger.error("Grant bridge mismatch: expected %s / %s / %s, found %s / %s / %s",
                             RUNTIME_BUILD, BRIDGE_PROTOCOL, HARNESS_VERSION,
                             state.get("build", "missing"), state.get("protocol", "missing"),
                             state.get("harness", "missing"))
                await asyncio.sleep(1); continue
            if outcome == "failure":
                logger.error("Grant failed: %s", state.get("detail", state.get("status")))
                await asyncio.sleep(1); continue
            if outcome != "success" and not command.exists():
                command.write_text(line, encoding="ascii")
            deadline = asyncio.get_running_loop().time() + BRIDGE_TIMEOUT_SECONDS
            while outcome == "pending" and not ctx.exit_event.is_set():
                if asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(.25)
                state = read_state(state_path)
                outcome = grant_state_outcome(state, tag)
            if outcome == "incompatible":
                logger.error("Grant bridge changed version while processing %s", tag)
                await asyncio.sleep(1); continue
            if outcome == "failure":
                logger.error("Grant failed: %s", state.get("detail", state.get("status")))
                await asyncio.sleep(1); continue
            if outcome != "success":
                logger.error("Grant bridge timed out after %s seconds; command retained for diagnosis",
                             BRIDGE_TIMEOUT_SECONDS)
                await asyncio.sleep(1); continue
            command.unlink(missing_ok=True)
            delivered += 1
            receipt.write_text(json.dumps({"slot_key": receipt_key, "delivered": delivered}, indent=2) + "\n", encoding="utf-8")
        await asyncio.sleep(.25)

async def main(args) -> None:
    ctx = BloodborneContext(args.connect, args.password, Path(args.work_dir).resolve())
    ctx.auth = args.name
    harness_state = read_state(ctx.work_dir / "native-grant-state.txt")
    logger.info("Bloodborne Client build %s, world version %s; bridge reports build %s, "
                "protocol %s, harness %s", RUNTIME_BUILD, WORLD_VERSION,
                harness_state.get("build", "missing"), harness_state.get("protocol", "missing"),
                harness_state.get("harness", "missing"))
    for line in attach_report_lines():
        logger.info("%s", line)
    ctx.server_task = asyncio.create_task(server_loop(ctx))
    bridge = asyncio.create_task(bridge_loop(ctx))
    if gui_enabled: ctx.run_gui()
    ctx.run_cli()
    await ctx.exit_event.wait()
    bridge.cancel()
    await ctx.shutdown()

def build_parser() -> argparse.ArgumentParser:
    """Mirrors CommonClient's own ``run_as_textclient`` parser.

    ``get_base_parser`` supplies only --connect/--password/--nogui; --name and the
    url positional live in CommonClient's ``__main__`` block, so a client that
    reads ``args.name`` has to declare them itself.
    """
    parser = get_base_parser(description="Bloodborne Archipelago Client")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("--work-dir", default=str(Path.home() / "bb-archipelago" / "work"))
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    return parser

def launch(*launch_args: str) -> None:
    args = build_parser().parse_args(launch_args)
    args = handle_url_arg(args, parser=build_parser())
    asyncio.run(main(args))

if __name__ == "__main__": launch()
