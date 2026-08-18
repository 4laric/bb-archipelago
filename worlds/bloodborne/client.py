"""File bridge between Archipelago and the validated Cheat Engine grant harness."""
from __future__ import annotations
import argparse, asyncio, json, logging
from pathlib import Path
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, server_loop
from NetUtils import ClientStatus
from Utils import async_start
from . import GAME, ITEM_ID_BY_KEY, LOCATION_ID_BY_KEY
from .data import MODEL
from .runtime_bindings import DELIVERY_FIXTURES, ITEM_BINDINGS

logger = logging.getLogger("BloodborneClient")
ITEM_KEY_BY_AP_ID = {value: key for key, value in ITEM_ID_BY_KEY.items()}
LOCATION_BY_NAME = {loc.name.casefold(): LOCATION_ID_BY_KEY[loc.key] for loc in MODEL.locations}

class BloodborneCommandProcessor(ClientCommandProcessor):
    def _cmd_check(self, *parts: str) -> bool:
        """Manually report a check: /check <exact location name>."""
        location = LOCATION_BY_NAME.get(" ".join(parts).strip().casefold())
        if location is None:
            self.output("Unknown location. Use /missing for exact names.")
            return False
        async_start(self.ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location]}]))
        if location == LOCATION_ID_BY_KEY["boss_mergos_wet_nurse"]:
            async_start(self.ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))
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

def grant_command(item_id: int) -> str | None:
    key = ITEM_KEY_BY_AP_ID.get(item_id)
    binding = ITEM_BINDINGS.get(key) if key else None
    if item_id == 0xBB0100:
        key, binding = "blood_vial", DELIVERY_FIXTURES["blood_vial"]
    if not key or not binding or binding.normalized_item_id is None or binding.raw_descriptor is None:
        return None
    return f"GRANT 0x{binding.raw_descriptor:08X} 0x{binding.normalized_item_id:08X} 1 AUTO {key}\n"

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
        if delivered < len(ctx.items_received) and not command.exists():
            line = grant_command(ctx.items_received[delivered].item)
            if line is None:
                logger.error("Unsupported item; delivery paused")
                await asyncio.sleep(1); continue
            command.write_text(line, encoding="ascii")
            while command.exists() and not ctx.exit_event.is_set(): await asyncio.sleep(.25)
            state = read_state(state_path)
            if state.get("status") not in {"completed", "recovered_complete"}:
                logger.error("Grant failed: %s", state.get("detail", state.get("status")))
                await asyncio.sleep(1); continue
            delivered += 1
            receipt.write_text(json.dumps({"slot_key": receipt_key, "delivered": delivered}, indent=2) + "\n", encoding="utf-8")
        await asyncio.sleep(.25)

async def main(args) -> None:
    ctx = BloodborneContext(args.connect, args.password, Path(args.work_dir).resolve())
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx))
    bridge = asyncio.create_task(bridge_loop(ctx))
    if gui_enabled: ctx.run_gui()
    ctx.run_cli()
    await ctx.exit_event.wait()
    bridge.cancel()
    await ctx.shutdown()

def launch(*launch_args: str) -> None:
    parser = get_base_parser(description="Bloodborne Archipelago Client")
    parser.add_argument("--work-dir", default=str(Path.home() / "bb-archipelago" / "work"))
    asyncio.run(main(parser.parse_args(launch_args)))

if __name__ == "__main__": launch()
