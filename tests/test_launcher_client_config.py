from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher.client_config import (
    session_key,
    session_paths,
    substitute_plan_arguments,
    write_client_runtime_config,
)
from bb_launcher.core import (
    APP_VERSION,
    CATHEDRAL_EVENT_PATH,
    COMMON_EVENT_PATH,
    SUPPRESSION_PATH,
    GameInstall,
    ProcessSpec,
    SeedCache,
    SeedIdentity,
    ValidationError,
    activate_build,
    sha256_file,
)
from bb_launcher.workflow import (
    EnemizerOptions,
    LauncherSettings,
    LauncherWorkflow,
    ProcessPlan,
    resolve_process_plan,
)


def write_sfo(path: Path, values: dict[str, str]) -> None:
    keys = bytearray()
    data = bytearray()
    entries: list[bytes] = []
    for key, value in values.items():
        key_offset = len(keys)
        keys.extend(key.encode("utf-8") + b"\0")
        encoded = value.encode("utf-8") + b"\0"
        data_offset = len(data)
        data.extend(encoded)
        entries.append(struct.pack("<HHIII", key_offset, 0x0204, len(encoded), len(encoded), data_offset))
    key_table = 20 + 16 * len(entries)
    data_table = key_table + len(keys)
    payload = struct.pack("<4s4I", b"\0PSF", 0x00000101, key_table, data_table, len(entries))
    payload += b"".join(entries) + bytes(keys) + bytes(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def make_install(root: Path) -> GameInstall:
    base = root / "CUSA03173"
    patch = root / "CUSA03173-patch"
    write_sfo(base / "sce_sys" / "param.sfo", {"TITLE_ID": "CUSA03173", "APP_VER": "01.00"})
    write_sfo(patch / "sce_sys" / "param.sfo", {"TITLE_ID": "CUSA03173", "APP_VER": APP_VERSION})
    return GameInstall.from_root(root)


def make_build(root: Path, seed: str, content: bytes) -> Path:
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    binder = inputs / f"{seed}.parambnd.dcx"
    binder.write_bytes(content)
    identity = SeedIdentity(
        seed=seed,
        slot="Hunter",
        world_build="bb-world-r1",
        runtime_build="bb-runtime-r1",
        shad_build="0.18.0",
        source_hashes={SUPPRESSION_PATH: hashlib.sha256(content + b"-source").hexdigest()},
        options={"enemy_randomizer": False},
        suppression_plan_sha256=hashlib.sha256(b"plan").hexdigest(),
        suppression_binder_sha256=hashlib.sha256(content).hexdigest(),
    )
    return SeedCache(root / "cache").build(identity, binder).path


class ClientConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def activate(self, seed: str, content: bytes) -> tuple[GameInstall, dict]:
        install = make_install(self.root / "game")
        build = make_build(self.root / seed, seed, content)
        owner = activate_build(install, build, process_is_running=lambda: False)
        return install, owner

    def test_written_config_points_at_the_verified_active_overlay_binder(self):
        install, owner = self.activate("seed", b"suppressed")
        manifest = self.root / "build-manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        state = self.root / "state"
        paths = write_client_runtime_config(
            state,
            seed="seed",
            slot="Hunter",
            install=install,
            owner=owner,
            suppression_manifest=manifest,
            shad_log=self.root / "shad_log.txt",
            auto_upgrade=True,
            auto_equip=True,
            research_captures=True,
        )
        raw = paths.config.read_bytes()
        # The native client rejects a UTF-8 BOM at line 1 column 1.
        self.assertNotEqual(raw[:3], b"\xef\xbb\xbf")
        config = json.loads(raw.decode("utf-8"))
        installed = install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        self.assertEqual(config["installed_gameparam"], str(installed))
        self.assertEqual(sha256_file(installed), owner["suppression"]["sha256"])
        self.assertEqual(config["suppression_manifest"], str(manifest.resolve()))
        self.assertEqual(config["shad_log"], str((self.root / "shad_log.txt").resolve()))
        self.assertEqual(config["bridge_root"], str(state.resolve() / "bridge"))
        self.assertTrue(config["auto_upgrade"])
        self.assertTrue(config["auto_equip"])
        self.assertTrue(config["pickup_notification_probe"])
        self.assertTrue(config["boss_flag_census"])
        self.assertTrue(config["rune_capture"])
        self.assertFalse(config["insight_probe"])
        self.assertTrue(config["readiness_durations"])
        # Seed-owned tables stay empty: the client replaces them from
        # slot_data on connect, and local config cannot weaken the seed.
        self.assertEqual(
            {key: config[key] for key in ("locations", "items", "expected_save_identity")},
            {"locations": [], "items": {}, "expected_save_identity": None},
        )
        # The ledger path is named per session but the file is not created:
        # the client treats a missing ledger as an empty one.
        self.assertEqual(paths.ledger, paths.session / "ledger.json")
        self.assertFalse(paths.ledger.exists())

    def test_session_state_is_isolated_per_seed_slot_and_survives_rebuilds(self):
        state = self.root / "state"
        first = session_paths(state, seed="s", slot="A")
        again = session_paths(state, seed="s", slot="A")
        other_slot = session_paths(state, seed="s", slot="B")
        other_seed = session_paths(state, seed="t", slot="A")
        self.assertEqual(first, again)
        self.assertNotEqual(first.ledger, other_slot.ledger)
        self.assertNotEqual(first.ledger, other_seed.ledger)
        self.assertNotEqual(other_slot.ledger, other_seed.ledger)
        # The derivation is pinned: it matches the ledger's seed/slot keying.
        self.assertEqual(
            session_key("s", "A"),
            hashlib.sha256("s\x1fA".encode("utf-8")).hexdigest(),
        )
        with self.assertRaisesRegex(ValidationError, "non-empty"):
            session_paths(state, seed="", slot="A")

    def test_placeholders_substitute_and_unknown_tokens_fail_closed(self):
        paths = session_paths(self.root / "state", seed="s", slot="A")
        resolved = substitute_plan_arguments(
            ["localhost:38282", "A", "{runtime_config}", "--ledger={ledger}", "{bridge_root}"],
            paths,
        )
        self.assertEqual(
            resolved,
            (
                "localhost:38282",
                "A",
                str(paths.config),
                f"--ledger={paths.ledger}",
                str(paths.bridge_root),
            ),
        )
        with self.assertRaisesRegex(ValidationError, "unknown placeholder"):
            substitute_plan_arguments(["{confg}"], paths)
        with self.assertRaisesRegex(ValidationError, "vanilla launch"):
            substitute_plan_arguments(["{ledger}"], None)
        self.assertEqual(substitute_plan_arguments(["plain"], None), ("plain",))

        plan = ProcessPlan(
            shad_build="0.18.0",
            runtime_build="bb-runtime-r1",
            processes=(
                ProcessSpec("shadPS4", Path("shadPS4.exe"), ("{game_path}",)),
                ProcessSpec("AP client", Path("bb-ap-client.exe"), ("{runtime_config}", "{ledger}")),
            ),
        )
        game = self.root / "game" / "CUSA03173"
        resolved_plan = resolve_process_plan(plan, paths, game_path=game)
        self.assertEqual(resolved_plan.processes[0].arguments, (str(game),))
        self.assertEqual(
            resolved_plan.processes[1].arguments,
            (str(paths.config), str(paths.ledger)),
        )
        with self.assertRaisesRegex(ValidationError, "vanilla launch"):
            resolve_process_plan(plan, None, game_path=game)

    def test_switching_seeds_rewrites_the_config_and_keeps_both_ledgers(self):
        install, owner_a = self.activate("seed-a", b"suppressed-a")
        paths_a = write_client_runtime_config(
            self.root / "state",
            seed="seed-a",
            slot="Hunter",
            install=install,
            owner=owner_a,
            suppression_manifest=None,
            shad_log=None,
        )
        build_b = make_build(self.root / "seed-b", "seed-b", b"suppressed-b")
        owner_b = activate_build(install, build_b, process_is_running=lambda: False)
        paths_b = write_client_runtime_config(
            self.root / "state",
            seed="seed-b",
            slot="Hunter",
            install=install,
            owner=owner_b,
            suppression_manifest=None,
            shad_log=None,
        )
        # The new config points at the newly active binder; the previous
        # session's config and ledger path are untouched on disk.
        config_b = json.loads(paths_b.config.read_text(encoding="utf-8"))
        installed = install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        self.assertEqual(sha256_file(installed), owner_b["suppression"]["sha256"])
        self.assertEqual(config_b["installed_gameparam"], str(installed))
        config_a = json.loads(paths_a.config.read_text(encoding="utf-8"))
        self.assertEqual(config_a["installed_gameparam"], config_b["installed_gameparam"])
        self.assertNotEqual(paths_a.ledger, paths_b.ledger)
        self.assertTrue(paths_a.session.is_dir())

    def test_config_write_refuses_a_binder_that_does_not_match_the_owner(self):
        install, owner = self.activate("seed", b"suppressed")
        tampered = install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        # Same length as the original, so the size check passes and the hash
        # check is what proves the tamper.
        tampered.write_bytes(b"xxxxxxxxxx")
        with self.assertRaisesRegex(ValidationError, "hash changed"):
            write_client_runtime_config(
                self.root / "state",
                seed="seed",
                slot="Hunter",
                install=install,
                owner=owner,
                suppression_manifest=None,
                shad_log=None,
            )

    def test_randomize_and_launch_writes_the_config_and_substitutes_the_plan(self):
        install = make_install(self.root / "game")
        source = install.patch.joinpath(*SUPPRESSION_PATH.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"vanilla-param")
        for event_path in (CATHEDRAL_EVENT_PATH, COMMON_EVENT_PATH):
            event = install.patch.joinpath(*event_path.split("/"))
            event.parent.mkdir(parents=True, exist_ok=True)
            event.write_bytes(b"licensed-event")
        binder = self.root / "binder.parambnd.dcx"
        binder.write_bytes(b"suppressed-param")
        plan_hash = hashlib.sha256(b"plan").hexdigest()
        manifest = self.root / "build-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "format": "bb-vanilla-suppression-build-v1",
                    "output_relative_path": "param/gameparam/gameparam.parambnd.dcx",
                    "plan_sha256": plan_hash,
                    "source_gameparam_sha256": hashlib.sha256(b"vanilla-param").hexdigest(),
                    "output_gameparam_sha256": hashlib.sha256(b"suppressed-param").hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        request = self.root / "seed.bbseed.json"
        request.write_text(
            json.dumps(
                {
                    "format": "bb-seed-request-v1",
                    "player": 1,
                    "player_name": "Hunter",
                    "seed_name": "52100005",
                    "runtime_build": "bb-runtime-r1",
                    "world_version": "r1",
                    "enemizer_seed": "52100005:Hunter",
                    "suppression": {"plan_sha256": plan_hash},
                }
            ),
            encoding="utf-8",
        )
        client_exe = self.root / "bb-ap-client.exe"
        client_exe.write_bytes(b"client")
        plan_file = self.root / "process-plan.json"
        plan_file.write_text(
            json.dumps(
                {
                    "format": "bb-launcher-process-plan-v1",
                    "shad_build": "0.18.0",
                    "runtime_build": "bb-runtime-r1",
                    "processes": [
                        {
                            "name": "AP client",
                            "executable": str(client_exe),
                            "sha256": sha256_file(client_exe),
                            "arguments": [
                                "localhost:38282",
                                "Hunter",
                                "{runtime_config}",
                                "{ledger}",
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        settings = LauncherSettings(
            game_root=install.root,
            cache_root=self.root / "cache",
            ap_request=request,
            suppression_binder=binder,
            suppression_manifest=manifest,
            process_plan=plan_file,
            state_root=self.root / "state",
            shad_log=self.root / "shad_log.txt",
        )
        launched: list[tuple] = []

        def fake_launcher(specs):
            launched.extend(tuple(spec.arguments) for spec in specs)
            return [types.SimpleNamespace(pid=4321) for _ in specs]

        workflow = LauncherWorkflow(self.root, process_launcher=fake_launcher)
        def fake_event_build(**values):
            values["output"].parent.mkdir(parents=True, exist_ok=True)
            values["output"].write_bytes(b"verified-event-overlay")
            values["manifest"].write_text("{}", encoding="utf-8")

        with (patch("bb_launcher.workflow.EnemizerToolchain.write_cathedral_event",
                    side_effect=fake_event_build),
              patch("bb_launcher.workflow.EnemizerToolchain.write_common_event",
                    side_effect=fake_event_build)):
            result = workflow.randomize_and_launch(
                settings,
                EnemizerOptions(enabled=False),
                process_is_running=lambda: False,
            )
        config = json.loads(result.client_config.read_text(encoding="utf-8"))
        installed = install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        self.assertEqual(config["installed_gameparam"], str(installed))
        self.assertEqual(sha256_file(installed), hashlib.sha256(b"suppressed-param").hexdigest())
        self.assertEqual(config["suppression_manifest"], str(manifest.resolve()))
        self.assertEqual(
            launched,
            [
                (
                    "localhost:38282",
                    "Hunter",
                    str(result.client_config),
                    str(result.ledger),
                )
            ],
        )
        self.assertEqual(result.process_ids, (4321,))
        self.assertFalse(result.ledger.exists())
        self.assertEqual(result.client_config.parent.parent, (self.root / "state").resolve() / "sessions")


if __name__ == "__main__":
    unittest.main()
