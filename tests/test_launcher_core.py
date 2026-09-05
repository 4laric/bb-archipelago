from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from bb_launcher import core
from bb_launcher.core import (
    APP_VERSION,
    CATHEDRAL_EVENT_PATH,
    SESSION_HEADER_PREFIX,
    EXCLUDED_AP_OWNED,
    EXCLUDED_DEAD_PATH,
    EXCLUDED_RESERVED,
    MAP_PREFIX,
    MODS_DIR_NAME,
    OWNER_NAME,
    SEED_MANIFEST_FORMAT,
    SERIAL,
    SUPPRESSION_PATH,
    USER_MODS_DIR_NAME,
    ConflictError,
    DiscoveryError,
    EarlyExit,
    GameInstall,
    LaunchError,
    ProcessSpec,
    SeedCache,
    SeedIdentity,
    ValidationError,
    activate_build,
    canonical_overlay_case,
    collect_user_mod_files,
    deactivate_overlay,
    discover_game_install,
    discover_shad_executable,
    launch_processes,
    dead_path_warnings,
    dead_path_wrappers,
    plan_user_merge,
    recover_activation,
    require_no_stray_cheat_engine,
    restore_previous_build,
    sha256_file,
    read_session_log_tail,
    stray_cheat_engine_names,
    user_merge_summary,
    wait_for_early_exit,
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


def make_install(root: Path, *, serial: str = SERIAL, version: str = APP_VERSION) -> GameInstall:
    base = root / SERIAL
    patch = root / f"{SERIAL}-patch"
    write_sfo(base / "sce_sys" / "param.sfo", {"TITLE_ID": serial, "APP_VER": "01.00"})
    write_sfo(patch / "sce_sys" / "param.sfo", {"TITLE_ID": serial, "APP_VER": version})
    return GameInstall.from_root(root)


def identity(
    name: str,
    source: bytes = b"source",
    *,
    options: dict | None = None,
    enemizer_seed: str | None = None,
) -> SeedIdentity:
    return SeedIdentity(
        seed=name,
        slot="Hunter",
        world_build="bb-world-r1",
        runtime_build="bb-runtime-r1",
        shad_build="0.18.0",
        source_hashes={SUPPRESSION_PATH: hashlib.sha256(source).hexdigest()},
        options=options or {"enemy_randomizer": enemizer_seed is not None},
        enemizer_seed=enemizer_seed,
        suppression_plan_sha256=hashlib.sha256(b"plan").hexdigest(),
        suppression_binder_sha256=hashlib.sha256(source).hexdigest(),
    )


def make_build(
    root: Path,
    name: str,
    content: bytes,
    *,
    with_maps: bool = False,
) -> tuple[SeedCache, Path]:
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    binder = inputs / f"{name}.parambnd.dcx"
    binder.write_bytes(content)
    maps = None
    seed = None
    plan = None
    if with_maps:
        maps = inputs / f"{name}-maps"
        maps.mkdir()
        (maps / "m24_01_00_00.msb.dcx").write_bytes(b"map-" + content)
        seed = f"{name}:enemizer"
        plan = inputs / f"{name}-plan.json"
        plan.write_text(json.dumps(sample_plan(seed)), encoding="utf-8")
    cache = SeedCache(root / "cache")
    result = cache.build(
        identity(name, content, enemizer_seed=seed), binder, maps, enemizer_plan=plan
    )
    return cache, result.path


def sample_plan(seed: str) -> dict:
    """A minimal bb-enemizer-plan-v2 with one enriched swap (bb-archipelago#321)."""
    return {
        "format": "bb-enemizer-plan-v2",
        "seed": seed,
        "dry_run": True,
        "options": {"allow_tier_mixing": False, "preserve_locomotion": False},
        "stress": None,
        "swaps": [
            {
                "logical_key": "m24_01_00_00:c1000_0000",
                "destination_keys": ["m24_01_00_00:c1000_0000"],
                "destinations": {
                    "m24_01_00_00:c1000_0000": {
                        "map_name": "m24_01_00_00", "entity_id": 2410100,
                        "x": 1.0, "y": 2.0, "z": 3.0,
                    }
                },
                "source": {"model_name": "c1000", "npc_param_id": 100000,
                           "think_param_id": 100000, "chara_init_id": 0},
                "target": {"model_name": "c4060", "npc_param_id": 406000,
                           "think_param_id": 406000, "chara_init_id": 0},
                "source_tag": {"size_class": "M", "tier": "common",
                               "locomotion": "move_type_3", "scaling_hp": 1.0},
                "target_tag": {"size_class": "XL", "tier": "elite",
                               "locomotion": "move_type_3", "scaling_hp": 1.0},
                "source_facts": {"name": "huntsman", "echoes": 120, "hp": 100},
                "target_facts": {"name": "fishman large", "echoes": 4514, "hp": 400},
                "warnings": ["size-up at limit: +1"],
            }
        ],
    }


def snapshot_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


class LauncherCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_game_validation_requires_exact_serial_and_update_version(self):
        valid = make_install(self.root / "valid")
        self.assertEqual(valid.serial, SERIAL)
        self.assertEqual(valid.app_version, APP_VERSION)
        wrong = self.root / "wrong-version"
        base = wrong / SERIAL
        patch = wrong / f"{SERIAL}-patch"
        write_sfo(base / "sce_sys" / "param.sfo", {"TITLE_ID": SERIAL})
        write_sfo(patch / "sce_sys" / "param.sfo", {"TITLE_ID": SERIAL, "APP_VER": "01.08"})
        with self.assertRaisesRegex(ValidationError, "AppVer 01.09"):
            GameInstall.from_root(wrong)

    def test_game_validation_names_a_foreign_serial_install(self):
        foreign = self.root / "foreign-install"
        (foreign / "CUSA00900").mkdir(parents=True)
        (foreign / "CUSA00900-patch").mkdir()
        with self.assertRaisesRegex(
            ValidationError, r"found CUSA00900.*only CUSA03173 AppVer 01\.09"
        ):
            GameInstall.from_root(foreign)
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValidationError, "missing base game directory"):
            GameInstall.from_root(empty)

    def test_merged_dump_without_patch_directory_is_accepted(self):
        merged = self.root / "merged"
        write_sfo(
            merged / SERIAL / "sce_sys" / "param.sfo",
            {"TITLE_ID": SERIAL, "APP_VER": APP_VERSION},
        )
        install = GameInstall.from_root(merged)
        self.assertIsNone(install.patch)
        self.assertEqual(install.app_version, APP_VERSION)
        relative = "dvdroot_ps4/test/file.bin"
        install.base.joinpath(*relative.split("/")).parent.mkdir(parents=True, exist_ok=True)
        install.base.joinpath(*relative.split("/")).write_bytes(b"merged")
        backend, path = install.resolve_file(relative, include_mods=False)
        self.assertEqual((backend, path.read_bytes()), ("base", b"merged"))
        self.assertEqual(
            [name for name, _layer in install.content_backends()], ["base"]
        )

    def test_merged_dump_at_the_wrong_version_is_rejected(self):
        stale = self.root / "stale"
        write_sfo(
            stale / SERIAL / "sce_sys" / "param.sfo",
            {"TITLE_ID": SERIAL, "APP_VER": "01.00"},
        )
        with self.assertRaisesRegex(ValidationError, "merged base reports '01.00'"):
            GameInstall.from_root(stale)

    def test_patch_directory_without_param_sfo_is_not_a_merged_dump(self):
        broken = self.root / "broken"
        write_sfo(
            broken / SERIAL / "sce_sys" / "param.sfo",
            {"TITLE_ID": SERIAL, "APP_VER": APP_VERSION},
        )
        (broken / f"{SERIAL}-patch").mkdir(parents=True)
        with self.assertRaisesRegex(ValidationError, "PARAM.SFO"):
            GameInstall.from_root(broken)

    def test_backend_resolution_is_mods_then_patch_then_base(self):
        install = make_install(self.root / "game")
        relative = "dvdroot_ps4/test/file.bin"
        for directory, content in ((install.base, b"base"), (install.patch, b"patch"), (install.mods, b"mods")):
            path = directory / "dvdroot_ps4" / "test" / "file.bin"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        backend, path = install.resolve_file(relative)
        self.assertEqual((backend, path.read_bytes()), ("mods", b"mods"))
        install.mods.joinpath(*relative.split("/")).unlink()
        backend, path = install.resolve_file(relative)
        self.assertEqual((backend, path.read_bytes()), ("patch", b"patch"))
        install.patch.joinpath(*relative.split("/")).unlink()
        backend, path = install.resolve_file(relative)
        self.assertEqual((backend, path.read_bytes()), ("base", b"base"))

    def test_source_validation_ignores_mods_and_refuses_update_hash_drift(self):
        install = make_install(self.root / "game")
        relative = SUPPRESSION_PATH
        base = install.base.joinpath(*relative.split("/"))
        patch = install.patch.joinpath(*relative.split("/"))
        mods = install.mods.joinpath(*relative.split("/"))
        for path, content in ((base, b"base"), (patch, b"patch"), (mods, b"mods")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        expected = {relative: hashlib.sha256(b"patch").hexdigest()}
        self.assertEqual(install.verify_source_hashes(expected), expected)
        with self.assertRaisesRegex(ValidationError, "source game hash mismatch"):
            install.verify_source_hashes(
                {relative: hashlib.sha256(b"different").hexdigest()}
            )

    def test_discovery_is_validated_and_refuses_ambiguous_setups(self):
        first = make_install(self.root / "one")
        nested = self.root / "nested" / "emulator" / "games"
        second = make_install(nested)
        found = discover_game_install([first.root])
        self.assertEqual(found.root, first.root)
        with self.assertRaisesRegex(DiscoveryError, "multiple valid"):
            discover_game_install([self.root])
        self.assertNotEqual(first.root, second.root)

    def test_shad_discovery_requires_one_unambiguous_executable(self):
        first = self.root / "shad-a" / "shadPS4.exe"
        first.parent.mkdir()
        first.write_bytes(b"exe")
        self.assertEqual(discover_shad_executable([first.parent]), first.resolve())
        second = self.root / "shad-b" / "shadPS4.exe"
        second.parent.mkdir()
        second.write_bytes(b"exe")
        with self.assertRaisesRegex(DiscoveryError, "multiple shadPS4"):
            discover_shad_executable([self.root])

    def test_cache_identity_is_stable_order_independent_and_input_complete(self):
        first = identity("seed", options={"b": 2, "a": 1})
        second = identity("seed", options={"a": 1, "b": 2})
        changed = identity("seed", options={"a": 1, "b": 3})
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertNotEqual(first.cache_key, changed.cache_key)
        self.assertEqual(
            first.cache_key,
            identity("other", options={"b": 2, "a": 1}).cache_key,
        )

    def test_cache_identity_tracks_binder_bytes_but_not_seed_or_slot(self):
        first = identity("seed-a", b"binder-a")
        other_seed = identity("seed-b", b"binder-a")
        other_slot = SeedIdentity.from_dict({**first.as_dict(), "slot": "Other Hunter"})
        changed_binder = identity("seed-a", b"binder-b")
        self.assertEqual(first.cache_key, other_seed.cache_key)
        self.assertEqual(first.cache_key, other_slot.cache_key)
        self.assertNotEqual(first.cache_key, changed_binder.cache_key)

    def test_cache_identity_tracks_overlay_build_format(self):
        material = identity("seed").cache_material()
        self.assertEqual(material["overlay_build_format"], SEED_MANIFEST_FORMAT)

    def test_cache_composes_only_suppression_and_optional_map_outputs(self):
        cache, build_path = make_build(self.root, "seed", b"suppressed", with_maps=True)
        result = cache.verify(build_path)
        paths = {record["path"] for record in result.manifest["files"]}
        self.assertEqual(
            paths,
            {SUPPRESSION_PATH, f"{MAP_PREFIX}m24_01_00_00.msb.dcx"},
        )
        self.assertEqual(result.manifest["suppression"]["plan_sha256"], hashlib.sha256(b"plan").hexdigest())
        self.assertTrue(result.manifest["enemizer"]["enabled"])

    def test_cache_reuses_verified_build_and_refuses_hash_drift(self):
        inputs = self.root / "inputs"
        inputs.mkdir()
        binder = inputs / "binder.dcx"
        binder.write_bytes(b"first")
        cache = SeedCache(self.root / "cache")
        seed = identity("seed", b"first")
        first = cache.build(seed, binder)
        second = cache.build(seed, binder)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        output = first.path.joinpath(*SUPPRESSION_PATH.split("/"))
        output.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValidationError, "changed"):
            cache.verify(first.path)

    def test_cache_refuses_outputs_outside_the_overlay_contract(self):
        binder = self.root / "binder.dcx"
        binder.write_bytes(b"binder")
        maps = self.root / "maps"
        maps.mkdir()
        (maps / "notes.txt").write_text("not a map", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "non-MSB"):
            SeedCache(self.root / "cache").build(
                identity("seed", enemizer_seed="12345"), binder, maps
            )

    def test_cache_carries_verified_cathedral_event_into_activation(self):
        binder = self.root / "binder.dcx"
        binder.write_bytes(b"suppressed")
        cathedral = self.root / "m24_00_00_00.emevd.dcx"
        cathedral.write_bytes(b"compiled owned events 12400760 and 12401803")
        cache = SeedCache(self.root / "cache")
        build = cache.build(identity("seed", b"suppressed"), binder,
                            cathedral_event=cathedral)
        witness = build.manifest["cathedral_event"]
        self.assertEqual(CATHEDRAL_EVENT_PATH, witness["path"])
        self.assertEqual(hashlib.sha256(cathedral.read_bytes()).hexdigest(),
                         witness["sha256"])
        install = make_install(self.root / "game")
        owner = activate_build(install, build.path, process_is_running=lambda: False)
        self.assertEqual(12401898,
                         owner["cathedral_event"]["laurence_witness_flag"])
        self.assertEqual(12401803,
                         owner["cathedral_event"]["suppressed_password_flag"])
        active = install.mods.joinpath(*CATHEDRAL_EVENT_PATH.split("/"))
        self.assertEqual(cathedral.read_bytes(), active.read_bytes())

    def test_cache_refuses_forged_cathedral_witness_contract(self):
        binder = self.root / "binder.dcx"
        binder.write_bytes(b"suppressed")
        cathedral = self.root / "m24_00_00_00.emevd.dcx"
        cathedral.write_bytes(b"compiled")
        cache = SeedCache(self.root / "cache")
        build = cache.build(identity("seed", b"suppressed"), binder,
                            cathedral_event=cathedral)
        manifest_path = build.path / core.SEED_MANIFEST_NAME
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutations = (
            ("both be present", lambda value: value.__setitem__("cathedral_event", None)),
            ("wrong component", lambda value: next(
                record for record in value["files"]
                if record["path"] == CATHEDRAL_EVENT_PATH
            ).__setitem__("component", "enemizer")),
            ("unexpected owned events", lambda value: value["cathedral_event"].__setitem__(
                "events", [12401803])),
            ("wrong Laurence flag", lambda value: value["cathedral_event"].__setitem__(
                "laurence_witness_flag", 12401897)),
            ("wrong password flag", lambda value: value["cathedral_event"].__setitem__(
                "suppressed_password_flag", 12401804)),
        )
        for message, mutate in mutations:
            with self.subTest(message=message):
                forged = json.loads(json.dumps(original))
                mutate(forged)
                manifest_path.write_text(json.dumps(forged), encoding="utf-8")
                with self.assertRaisesRegex(ValidationError, message):
                    cache.verify(build.path)
        manifest_path.write_text(json.dumps(original), encoding="utf-8")

    def test_cache_refuses_cathedral_witness_without_event_file_record(self):
        binder = self.root / "binder.dcx"
        binder.write_bytes(b"suppressed")
        cache = SeedCache(self.root / "cache")
        build = cache.build(identity("seed", b"suppressed"), binder)
        manifest_path = build.path / core.SEED_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["cathedral_event"] = {
            "path": CATHEDRAL_EVENT_PATH,
            "sha256": "0" * 64,
            "events": [12400760, 12401803],
            "laurence_witness_flag": 12401898,
            "suppressed_password_flag": 12401803,
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "both be present"):
            cache.verify(build.path)

    def test_activation_refuses_preexisting_unowned_mods_without_moving_it(self):
        install = make_install(self.root / "game")
        install.mods.mkdir()
        user_file = install.mods / "user-mod.bin"
        user_file.write_bytes(b"mine")
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        with self.assertRaisesRegex(ConflictError, "without a Bloodborne AP ownership"):
            activate_build(install, build, process_is_running=lambda: False)
        self.assertEqual(user_file.read_bytes(), b"mine")
        self.assertFalse((install.mods / OWNER_NAME).exists())

    def test_activation_writes_owner_and_never_mutates_base_or_update(self):
        install = make_install(self.root / "game")
        source = install.patch.joinpath(*SUPPRESSION_PATH.split("/"))
        source.parent.mkdir(parents=True)
        source.write_bytes(b"vanilla-update")
        before_base = snapshot_tree(install.base)
        before_patch = snapshot_tree(install.patch)
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        owner = activate_build(install, build, process_is_running=lambda: False)
        self.assertEqual(owner["cache_key"], json.loads((install.mods / OWNER_NAME).read_text())["cache_key"])
        backend, active = install.resolve_file(SUPPRESSION_PATH)
        self.assertEqual((backend, active.read_bytes()), ("mods", b"suppressed"))
        self.assertEqual(snapshot_tree(install.base), before_base)
        self.assertEqual(snapshot_tree(install.patch), before_patch)

    def test_activation_refuses_while_shad_is_running(self):
        install = make_install(self.root / "game")
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        with self.assertRaisesRegex(ConflictError, "shadPS4 is running"):
            activate_build(install, build, process_is_running=lambda: True)
        self.assertFalse(install.mods.exists())

    def test_interrupted_activation_finishes_from_verified_stage(self):
        install = make_install(self.root / "game")
        _cache_a, build_a = make_build(self.root / "a", "seed-a", b"A")
        _cache_b, build_b = make_build(self.root / "b", "seed-b", b"B")
        activate_build(install, build_a, process_is_running=lambda: False)

        def interrupt(phase: str) -> None:
            if phase == "previous_moved":
                raise RuntimeError("simulated power loss")

        with self.assertRaisesRegex(RuntimeError, "power loss"):
            activate_build(
                install,
                build_b,
                process_is_running=lambda: False,
                failpoint=interrupt,
            )
        self.assertFalse(install.mods.exists())
        self.assertEqual(recover_activation(install, process_is_running=lambda: False), "completed")
        active = install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        self.assertEqual(active.read_bytes(), b"B")

    def test_vanilla_deactivation_preserves_cache_and_uses_update_backend(self):
        install = make_install(self.root / "game")
        update = install.patch.joinpath(*SUPPRESSION_PATH.split("/"))
        update.parent.mkdir(parents=True)
        update.write_bytes(b"update")
        cache, build = make_build(self.root / "build", "seed", b"randomized")
        activate_build(install, build, process_is_running=lambda: False)
        disabled = deactivate_overlay(install, process_is_running=lambda: False)
        self.assertIsNotNone(disabled)
        self.assertFalse(install.mods.exists())
        backend, selected = install.resolve_file(SUPPRESSION_PATH)
        self.assertEqual((backend, selected.read_bytes()), ("patch", b"update"))
        cache.verify(build)

    def test_restore_previous_reactivates_exact_cached_seed(self):
        install = make_install(self.root / "game")
        common_cache = SeedCache(self.root / "cache")
        binder_a = self.root / "a.dcx"
        binder_b = self.root / "b.dcx"
        binder_a.write_bytes(b"A")
        binder_b.write_bytes(b"B")
        build_a = common_cache.build(identity("seed-a", b"A"), binder_a).path
        build_b = common_cache.build(identity("seed-b", b"B"), binder_b).path
        activate_build(install, build_a, process_is_running=lambda: False)
        activate_build(install, build_b, process_is_running=lambda: False)
        owner = restore_previous_build(
            install, common_cache, process_is_running=lambda: False
        )
        self.assertEqual(owner["identity"]["seed"], "seed-a")
        self.assertEqual(install.mods.joinpath(*SUPPRESSION_PATH.split("/")).read_bytes(), b"A")

    def test_unowned_file_added_to_managed_overlay_blocks_next_operation(self):
        install = make_install(self.root / "game")
        _cache_a, build_a = make_build(self.root / "a", "seed-a", b"A")
        _cache_b, build_b = make_build(self.root / "b", "seed-b", b"B")
        activate_build(install, build_a, process_is_running=lambda: False)
        (install.mods / "surprise.bin").write_bytes(b"user")
        with self.assertRaisesRegex(ConflictError, "unowned"):
            activate_build(install, build_b, process_is_running=lambda: False)
        self.assertEqual((install.mods / "surprise.bin").read_bytes(), b"user")

    def test_process_launch_validates_every_executable_before_starting_any(self):
        executable = self.root / "shadPS4.exe"
        executable.write_bytes(b"exe")
        started: list[tuple[list[str], str | None]] = []

        class Started:
            pid = 42

        def fake_popen(command, cwd=None):
            started.append((command, cwd))
            return Started()

        specs = [
            ProcessSpec("shadPS4", executable, ("--game", SERIAL), executable.parent),
            ProcessSpec("client", self.root / "missing.exe"),
        ]
        with self.assertRaisesRegex(LaunchError, "client executable does not exist"):
            launch_processes(specs, popen=fake_popen)
        self.assertEqual(len(started), 0)
        processes = launch_processes(specs[:1], popen=fake_popen)
        self.assertEqual(processes[0].pid, 42)
        self.assertEqual(started[0][0], [str(executable.resolve()), "--game", SERIAL])

    def test_a_client_that_exits_at_startup_reports_its_message_verbatim(self):
        # bb-archipelago#171 motivating case: the client refuses at startup and
        # its console dies with it.  The captured log must carry the reason.
        message = "OpenProcess error 5: run the launcher as administrator"
        log = self.root / "session" / "client.log"
        specs = [
            ProcessSpec(
                "AP client",
                Path(sys.executable),
                (
                    "-c",
                    f"import sys; sys.stderr.write({message!r} + chr(10)); sys.exit(1)",
                ),
                log_path=log,
            )
        ]
        started = launch_processes(specs)
        early = wait_for_early_exit(started, specs, timeout=30.0, interval=0.05)
        self.assertIsInstance(early, EarlyExit)
        self.assertEqual(early.name, "AP client")
        self.assertEqual(early.returncode, 1)
        self.assertIn(message, early.log_tail)
        report = early.describe()
        self.assertIn(message, report)
        self.assertIn("exit code 1", report)
        self.assertIn(str(log), report)
        self.assertIn(message, log.read_text(encoding="utf-8"))

    def test_launch_tees_child_output_to_both_console_and_log(self):
        # bb-archipelago#179: output must be TEE'd, not redirected -- a live
        # console window AND the session log both receive the child's lines, so
        # the client#422 banner is visible again instead of a blank window.
        line = "client#422 banner: starting up"
        log = self.root / "session" / "client.log"
        console = io.StringIO()
        spec = ProcessSpec(
            "AP client",
            Path(sys.executable),
            ("-c", f"import sys; sys.stdout.write({line!r} + chr(10))"),
            log_path=log,
        )
        started = launch_processes([spec], console=console)
        wait_for_early_exit(started, [spec], timeout=30.0, interval=0.05)
        self.assertIn(line, console.getvalue())
        self.assertIn(line, log.read_text(encoding="utf-8"))

    def test_immediate_exit_still_tees_its_tail_to_console_and_log(self):
        # The tee must not regress #171: a child that dies at once still leaves
        # its refusal in the file for EarlyExit, and now also on the console.
        message = "startup refusal: bad server address"
        log = self.root / "session" / "client.log"
        console = io.StringIO()
        spec = ProcessSpec(
            "AP client",
            Path(sys.executable),
            (
                "-c",
                f"import sys; sys.stderr.write({message!r} + chr(10)); sys.exit(1)",
            ),
            log_path=log,
        )
        started = launch_processes([spec], console=console)
        early = wait_for_early_exit(started, [spec], timeout=30.0, interval=0.05)
        self.assertIsInstance(early, EarlyExit)
        self.assertEqual(early.returncode, 1)
        self.assertIn(message, early.log_tail)
        self.assertIn(message, log.read_text(encoding="utf-8"))
        self.assertIn(message, console.getvalue())

    def test_launch_without_log_path_inherits_console_and_starts_no_pump(self):
        # With no log_path the child inherits the console exactly as before:
        # no pipe kwargs, no pump thread, nothing teed into the console sink.
        executable = self.root / "client.exe"
        executable.write_bytes(b"exe")
        calls: list[dict] = []

        class Started:
            pass

        def fake_popen(command, cwd=None, **kwargs):
            calls.append(kwargs)
            return Started()

        console = io.StringIO()
        spec = ProcessSpec("AP client", executable)
        started = launch_processes([spec], popen=fake_popen, console=console)
        self.assertEqual(calls, [{}])
        self.assertEqual(console.getvalue(), "")
        self.assertFalse(hasattr(started[0], "_bb_output_pump"))

    def test_a_self_logging_client_is_neither_piped_nor_pumped(self):
        # bb-archipelago#181: the client writes log_path ITSELF (clients#425),
        # so the launcher must hand it the console untouched -- no pipe kwargs,
        # no pump thread, and no launcher-written header.  log_path stays set
        # because it still names the file the early-exit dialog reads.
        executable = self.root / "client.exe"
        executable.write_bytes(b"exe")
        log = self.root / "session" / "client.log"
        calls: list[dict] = []

        class Started:
            pass

        def fake_popen(command, cwd=None, **kwargs):
            calls.append(kwargs)
            return Started()

        console = io.StringIO()
        spec = ProcessSpec("AP client", executable, log_path=log, self_logging=True)
        started = launch_processes([spec], popen=fake_popen, console=console)
        self.assertEqual(calls, [{}], "a self-logging child must inherit the console")
        self.assertFalse(hasattr(started[0], "_bb_output_pump"))
        self.assertEqual(console.getvalue(), "")
        self.assertFalse(log.exists(), "the launcher must not open the child's own log")

    def test_a_self_logging_client_that_dies_reports_the_log_it_wrote_itself(self):
        # The #171 early-exit dialog is unchanged in shape: read_session_log_tail
        # slices on the last header and reports the refusal.  The only thing that
        # moved is WHO wrote the file -- here a stub standing in for the client,
        # writing its own header and refusal exactly as clients#425 does.
        message = "OpenProcess error 5: run the launcher as administrator"
        log = self.root / "session" / "client.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        # A previous session's output is already in the file: the tail must not
        # report it.
        log.write_text(
            f"\n{SESSION_HEADER_PREFIX} 2026-08-24 10:00:00 UTC ===\nan older run\n",
            encoding="utf-8",
        )
        script = (
            "import sys\n"
            "path = sys.argv[1]\n"
            "with open(path, 'a', encoding='utf-8') as handle:\n"
            f"    handle.write('\\n{SESSION_HEADER_PREFIX} 2026-08-25 11:00:00 UTC ===\\n')\n"
            f"    handle.write({message!r} + chr(10))\n"
            "sys.exit(1)\n"
        )
        specs = [
            ProcessSpec(
                "AP client",
                Path(sys.executable),
                ("-c", script, str(log)),
                log_path=log,
                self_logging=True,
            )
        ]
        started = launch_processes(specs)
        early = wait_for_early_exit(started, specs, timeout=30.0, interval=0.05)
        self.assertIsInstance(early, EarlyExit)
        self.assertEqual(early.name, "AP client")
        self.assertEqual(early.returncode, 1)
        self.assertEqual(early.log_path, log)
        self.assertIn(message, early.log_tail)
        self.assertNotIn("an older run", early.log_tail)
        report = early.describe()
        self.assertIn(message, report)
        self.assertIn(str(log), report)
        # Exactly the two headers that were written: the launcher added none.
        contents = log.read_text(encoding="utf-8")
        self.assertEqual(contents.count(SESSION_HEADER_PREFIX), 2)

    def test_a_shadps4_boot_crash_names_shadps4_and_carries_its_output(self):
        # bb-archipelago#175 motivating case: shadPS4, not the client, exits 1
        # right after launch.  The report must name shadPS4 and carry what the
        # emulator wrote, from shadPS4's own session log.
        message = "Fatal: failed to load mod file at boot"
        log = self.root / "session" / "shadps4.log"
        specs = [
            ProcessSpec(
                "shadPS4",
                Path(sys.executable),
                (
                    "-c",
                    f"import sys; sys.stderr.write({message!r} + chr(10)); sys.exit(1)",
                ),
                log_path=log,
            )
        ]
        started = launch_processes(specs)
        early = wait_for_early_exit(started, specs, timeout=30.0, interval=0.05)
        self.assertIsInstance(early, EarlyExit)
        self.assertEqual(early.name, "shadPS4")
        self.assertEqual(early.returncode, 1)
        self.assertEqual(early.log_path, log)
        self.assertIn(message, early.log_tail)
        report = early.describe()
        self.assertTrue(report.startswith("shadPS4 exited with exit code 1"))
        self.assertIn(message, report)
        self.assertIn(str(log), report)
        self.assertNotIn("AP client", report)

    def test_each_launch_appends_a_dated_session_header_to_the_same_log(self):
        log = self.root / "session" / "client.log"
        def spec(text: str) -> ProcessSpec:
            return ProcessSpec(
                "AP client",
                Path(sys.executable),
                ("-c", f"import sys; sys.stdout.write({text!r} + chr(10))"),
                log_path=log,
            )

        for text in ("first-run", "second-run"):
            started = launch_processes([spec(text)])
            wait_for_early_exit(started, [spec(text)], timeout=30.0, interval=0.05)
        contents = log.read_text(encoding="utf-8")
        self.assertEqual(contents.count(SESSION_HEADER_PREFIX), 2)
        self.assertIn("first-run", contents)
        self.assertIn("second-run", contents)
        # The reported tail is this session only, never the previous run's.
        tail = read_session_log_tail(log)
        self.assertIn("second-run", tail)
        self.assertNotIn("first-run", tail)

    def test_the_early_exit_watch_gives_up_when_every_child_stays_alive(self):
        class Alive:
            def poll(self):
                return None

        slept: list[float] = []
        clock = iter([0.0, 1.0, 2.0, 99.0])
        result = wait_for_early_exit(
            [Alive(), Alive()],
            [ProcessSpec("shadPS4", self.root), ProcessSpec("AP client", self.root)],
            timeout=10.0,
            sleep=slept.append,
            monotonic=lambda: next(clock),
        )
        self.assertIsNone(result)
        self.assertTrue(slept)

    def test_process_launch_refuses_an_incompatible_executable_hash(self):
        executable = self.root / "shadPS4.exe"
        executable.write_bytes(b"0.18.0")
        wrong = hashlib.sha256(b"other-build").hexdigest()
        with self.assertRaisesRegex(LaunchError, "executable hash mismatch"):
            launch_processes(
                [ProcessSpec("shadPS4", executable, expected_sha256=wrong)],
                popen=lambda *_args, **_kwargs: self.fail("hash mismatch started a process"),
            )


    def test_stray_cheat_engine_guard_only_fires_for_a_pinned_bridge(self):
        executable = self.root / "cheatengine.exe"
        executable.write_bytes(b"ce")
        bridge = [ProcessSpec("CE bridge", executable, ["grant.CT"])]
        plain = [ProcessSpec("shadPS4", executable, [SERIAL])]
        running = lambda name: name == "cheatengine-i386.exe"
        # witness: the probe really does see the process the guard looks for
        self.assertEqual(stray_cheat_engine_names(running), ["cheatengine-i386.exe"])
        with self.assertRaisesRegex(ConflictError, "Cheat Engine is already running"):
            require_no_stray_cheat_engine(bridge, running)
        self.assertIsNone(require_no_stray_cheat_engine(plain, running))
        self.assertIsNone(require_no_stray_cheat_engine(bridge, lambda _name: False))

    def test_stray_cheat_engine_refusal_is_ascii_and_names_the_remedy(self):
        executable = self.root / "cheatengine.exe"
        executable.write_bytes(b"ce")
        with self.assertRaises(ConflictError) as raised:
            require_no_stray_cheat_engine(
                [ProcessSpec("CE bridge", executable, ["grant.CT"])],
                lambda name: name == "cheatengine.exe",
            )
        message = str(raised.exception)
        message.encode("ascii")  # in-game and console text stays ASCII
        self.assertIn("Close Cheat Engine and press Launch again", message)
        self.assertIn("no items could be delivered", message)


def write_user_mod(install, relative: str, content: bytes) -> Path:
    path = install.user_mods.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def digests(*paths: str) -> dict[str, str]:
    return {path: hashlib.sha256(path.encode()).hexdigest() for path in paths}


class UserModMergePolicyTests(unittest.TestCase):
    """Pure file-set policy: what merges, what is excluded, and why.

    These assert on a populated input every time -- an empty user set would
    satisfy every "nothing was merged" claim vacuously.
    """

    def test_ordinary_user_files_merge(self):
        user = digests("dvdroot_ps4/chr/c0000.bnd.dcx", "dvdroot_ps4/action/script/c0000.hks")
        merge = plan_user_merge(user, [SUPPRESSION_PATH])
        self.assertEqual(set(merge.merged), set(user))
        self.assertEqual(len(merge.merged), 2)
        self.assertFalse(merge.excluded, "nothing here collides with an owned path")

    def test_ap_owned_path_is_excluded_and_reported_not_dropped(self):
        user = digests(SUPPRESSION_PATH, "dvdroot_ps4/parts/wp.partsbnd.dcx")
        merge = plan_user_merge(user, [SUPPRESSION_PATH])
        self.assertEqual(set(merge.merged), {"dvdroot_ps4/parts/wp.partsbnd.dcx"})
        self.assertEqual(
            [(item.path, item.reason) for item in merge.excluded],
            [(SUPPRESSION_PATH, EXCLUDED_AP_OWNED)],
        )

    def test_owned_map_collision_is_case_insensitive(self):
        owned = f"{MAP_PREFIX}m24_01_00_00.msb.dcx"
        user = digests(owned.upper(), f"{MAP_PREFIX}m99_99_99_99.msb.dcx")
        merge = plan_user_merge(user, [owned])
        self.assertEqual(set(merge.merged), {f"{MAP_PREFIX}m99_99_99_99.msb.dcx"})
        self.assertEqual([item.reason for item in merge.excluded], [EXCLUDED_AP_OWNED])

    def test_launcher_reserved_names_are_excluded(self):
        user = digests(OWNER_NAME, ".bb-ap-anything/inside.bin", "dvdroot_ps4/chr/ok.dcx")
        merge = plan_user_merge(user, [SUPPRESSION_PATH])
        self.assertEqual(set(merge.merged), {"dvdroot_ps4/chr/ok.dcx"})
        self.assertEqual(
            sorted(item.reason for item in merge.excluded),
            [EXCLUDED_RESERVED, EXCLUDED_RESERVED],
        )

    def test_wrapper_folder_mod_tree_is_excluded_as_dead_paths(self):
        """oz's playtest.9 tree: one wrapper folder per mod, each with dvdroot_ps4.

        Every one of these paths lands outside dvdroot_ps4/ in the overlay, so
        shadPS4 never resolves them (bb-archipelago#173).
        """

        user = digests(
            "Boczkek's FPS boost Lite/dvdroot_ps4/param/gameparam/x.dcx",
            "Boczkek's FPS boost Lite/dvdroot_ps4/chr/c0000.bnd.dcx",
            "Half Cloth Physics with Blood/dvdroot_ps4/chr/c1000.bnd.dcx",
            "dvdroot_ps4/parts/wp.partsbnd.dcx",
        )
        merge = plan_user_merge(user, [SUPPRESSION_PATH])
        self.assertEqual(set(merge.merged), {"dvdroot_ps4/parts/wp.partsbnd.dcx"})
        self.assertEqual(
            sorted(item.reason for item in merge.excluded),
            [EXCLUDED_DEAD_PATH] * 3,
        )

    def test_dead_path_detection_is_case_insensitive_like_the_owned_rule(self):
        user = digests("DVDRoot_PS4/chr/c0000.bnd.dcx", "wrapper/DVDRoot_PS4/chr/c1000.bnd.dcx")
        merge = plan_user_merge(user, [SUPPRESSION_PATH])
        self.assertEqual(set(merge.merged), {"DVDRoot_PS4/chr/c0000.bnd.dcx"})
        self.assertEqual(
            [(item.path, item.reason) for item in merge.excluded],
            [("wrapper/DVDRoot_PS4/chr/c1000.bnd.dcx", EXCLUDED_DEAD_PATH)],
        )

    def test_dead_path_wrappers_group_by_wrapper_largest_first(self):
        user = digests(
            "Mod A/dvdroot_ps4/one.dcx",
            "Mod A/dvdroot_ps4/two.dcx",
            "Mod B/dvdroot_ps4/three.dcx",
            "loose.txt",
            "dvdroot_ps4/chr/kept.dcx",
        )
        merge = plan_user_merge(user, [SUPPRESSION_PATH])
        self.assertEqual(
            dead_path_wrappers(merge.excluded),
            (("Mod A", 2), ("Mod B", 1), ("loose.txt", 1)),
        )

    def test_dead_paths_change_the_fingerprint(self):
        clean = plan_user_merge(digests("dvdroot_ps4/chr/a.dcx"), [SUPPRESSION_PATH])
        wrapped = plan_user_merge(
            digests("dvdroot_ps4/chr/a.dcx", "Mod A/dvdroot_ps4/chr/a.dcx"),
            [SUPPRESSION_PATH],
        )
        self.assertEqual(len(wrapped.excluded), 1)
        self.assertNotEqual(clean.fingerprint, wrapped.fingerprint)

    def test_fingerprint_tracks_both_the_merged_and_excluded_sets(self):
        base = plan_user_merge(digests("dvdroot_ps4/chr/a.dcx"), [SUPPRESSION_PATH])
        same = plan_user_merge(digests("dvdroot_ps4/chr/a.dcx"), [SUPPRESSION_PATH])
        added = plan_user_merge(
            digests("dvdroot_ps4/chr/a.dcx", "dvdroot_ps4/chr/b.dcx"), [SUPPRESSION_PATH]
        )
        collided = plan_user_merge(
            digests("dvdroot_ps4/chr/a.dcx", SUPPRESSION_PATH), [SUPPRESSION_PATH]
        )
        self.assertEqual(base.fingerprint, same.fingerprint)
        self.assertNotEqual(base.fingerprint, added.fingerprint)
        self.assertNotEqual(base.fingerprint, collided.fingerprint)

    def test_unsafe_user_paths_are_refused_outright(self):
        with self.assertRaisesRegex(ValidationError, "unsafe game-relative path"):
            plan_user_merge(digests("../escape.bin"), [SUPPRESSION_PATH])


class UserModMergeActivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.install = make_install(self.root / "game")

    def tearDown(self):
        self.temporary.cleanup()

    def test_user_files_merge_into_the_overlay_and_are_owned_by_the_manifest(self):
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        write_user_mod(self.install, "dvdroot_ps4/action/script/c0000.hks", b"jump")
        before = snapshot_tree(self.install.user_mods)
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        owner = activate_build(self.install, build, process_is_running=lambda: False)
        merged, excluded = user_merge_summary(owner)
        self.assertEqual((merged, excluded), (2, ()))
        self.assertEqual(
            self.install.mods.joinpath("dvdroot_ps4", "chr", "c0000.bnd.dcx").read_bytes(),
            b"user-chr",
        )
        self.assertEqual(
            self.install.mods.joinpath(*SUPPRESSION_PATH.split("/")).read_bytes(), b"suppressed"
        )
        # The user's directory is an input, never a target.
        self.assertEqual(snapshot_tree(self.install.user_mods), before)
        self.assertEqual(len(before), 2)

    def test_user_gameparam_is_excluded_reported_and_the_ap_binder_wins(self):
        write_user_mod(self.install, SUPPRESSION_PATH, b"USER-GAMEPARAM")
        write_user_mod(self.install, "dvdroot_ps4/parts/wp.partsbnd.dcx", b"parts")
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        owner = activate_build(self.install, build, process_is_running=lambda: False)
        merged, excluded = user_merge_summary(owner)
        self.assertEqual(merged, 1)
        self.assertEqual(
            [(item.path, item.reason) for item in excluded],
            [(SUPPRESSION_PATH, EXCLUDED_AP_OWNED)],
        )
        backend, active = self.install.resolve_file(SUPPRESSION_PATH)
        self.assertEqual((backend, active.read_bytes()), ("mods", b"suppressed"))
        self.assertEqual(
            self.install.user_mods.joinpath(*SUPPRESSION_PATH.split("/")).read_bytes(),
            b"USER-GAMEPARAM",
        )

    def test_user_msb_colliding_with_an_enemizer_map_is_excluded(self):
        colliding = f"{MAP_PREFIX}m24_01_00_00.msb.dcx"
        write_user_mod(self.install, colliding, b"user-map")
        write_user_mod(self.install, f"{MAP_PREFIX}m99_99_99_99.msb.dcx", b"other-map")
        _cache, build = make_build(self.root / "build", "seed", b"suppressed", with_maps=True)
        owner = activate_build(self.install, build, process_is_running=lambda: False)
        merged, excluded = user_merge_summary(owner)
        self.assertEqual(merged, 1)
        self.assertEqual([item.path for item in excluded], [colliding])
        self.assertEqual(
            self.install.mods.joinpath(*colliding.split("/")).read_bytes(), b"map-suppressed"
        )

    def test_wrapper_folder_mods_merge_nothing_and_the_activation_says_so(self):
        write_user_mod(
            self.install, "Boczkek's FPS boost Lite/dvdroot_ps4/chr/c0000.bnd.dcx", b"fps"
        )
        write_user_mod(
            self.install, "Boczkek's FPS boost Lite/dvdroot_ps4/chr/c1000.bnd.dcx", b"fps2"
        )
        write_user_mod(self.install, "dvdroot_ps4/parts/wp.partsbnd.dcx", b"parts")
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        owner = activate_build(self.install, build, process_is_running=lambda: False)
        merged, excluded = user_merge_summary(owner)
        self.assertEqual(merged, 1)
        self.assertEqual(
            sorted(item.reason for item in excluded), [EXCLUDED_DEAD_PATH] * 2
        )
        self.assertFalse(
            self.install.mods.joinpath("Boczkek's FPS boost Lite").exists(),
            "a dead wrapper folder must not be copied into the overlay",
        )
        warnings = dead_path_warnings(owner)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Boczkek's FPS boost Lite", warnings[0])
        self.assertIn("2 file(s)", warnings[0])
        self.assertIn("move the contents of", warnings[0])

    def test_a_clean_activation_emits_no_dead_path_warning(self):
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        owner = activate_build(self.install, build, process_is_running=lambda: False)
        self.assertEqual(user_merge_summary(owner)[0], 1)
        # Witnessed against its sibling above, which produces exactly one line
        # from the same call for the wrapper-folder tree.
        self.assertEqual(len(dead_path_warnings(owner)), 0)

    def test_changing_the_user_directory_reactivates_the_same_seed(self):
        _cache, build = make_build(self.root / "build", "seed", b"suppressed")
        first = activate_build(self.install, build, process_is_running=lambda: False)
        self.assertEqual(user_merge_summary(first)[0], 0)
        write_user_mod(self.install, "dvdroot_ps4/chr/late.bnd.dcx", b"added-later")
        second = activate_build(self.install, build, process_is_running=lambda: False)
        self.assertEqual(user_merge_summary(second)[0], 1)
        self.assertEqual(second["cache_key"], first["cache_key"])
        self.assertTrue(
            self.install.mods.joinpath("dvdroot_ps4", "chr", "late.bnd.dcx").is_file()
        )
        # Unchanged inputs still short-circuit rather than churn the overlay.
        again = activate_build(self.install, build, process_is_running=lambda: False)
        self.assertEqual(again["user_merge"]["fingerprint"], second["user_merge"]["fingerprint"])

    def test_a_merged_overlay_still_fails_closed_on_an_unowned_addition(self):
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        _cache_a, build_a = make_build(self.root / "a", "seed-a", b"A")
        _cache_b, build_b = make_build(self.root / "b", "seed-b", b"B")
        activate_build(self.install, build_a, process_is_running=lambda: False)
        surprise = self.install.mods / "dvdroot_ps4" / "chr" / "surprise.bin"
        surprise.write_bytes(b"dropped in by hand")
        with self.assertRaisesRegex(ConflictError, "unowned"):
            activate_build(self.install, build_b, process_is_running=lambda: False)
        self.assertEqual(surprise.read_bytes(), b"dropped in by hand")

    def test_editing_a_merged_file_in_place_is_detected(self):
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        _cache_a, build_a = make_build(self.root / "a", "seed-a", b"A")
        _cache_b, build_b = make_build(self.root / "b", "seed-b", b"B")
        activate_build(self.install, build_a, process_is_running=lambda: False)
        self.install.mods.joinpath("dvdroot_ps4", "chr", "c0000.bnd.dcx").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValidationError, "hash changed"):
            activate_build(self.install, build_b, process_is_running=lambda: False)

    def test_game_manager_file_link_is_accepted_only_when_owned_bytes_match(self):
        _cache_a, build_a = make_build(self.root / "a", "seed-a", b"A")
        _cache_b, build_b = make_build(self.root / "b", "seed-b", b"B")
        activate_build(self.install, build_a, process_is_running=lambda: False)
        owned = self.install.mods / SUPPRESSION_PATH
        backing = self.root / "game-manager-copy.dcx"
        backing.write_bytes(owned.read_bytes())
        owned.unlink()
        try:
            owned.symlink_to(backing)
        except (OSError, NotImplementedError):
            self.skipTest("this platform does not allow creating symbolic links")

        # The existing overlay still verifies and can be replaced atomically;
        # the freshly staged overlay contains regular files again.
        activate_build(self.install, build_b, process_is_running=lambda: False)
        self.assertFalse((self.install.mods / SUPPRESSION_PATH).is_symlink())

    def test_game_manager_file_link_with_changed_bytes_fails_closed(self):
        _cache_a, build_a = make_build(self.root / "a", "seed-a", b"A")
        _cache_b, build_b = make_build(self.root / "b", "seed-b", b"B")
        activate_build(self.install, build_a, process_is_running=lambda: False)
        owned = self.install.mods / SUPPRESSION_PATH
        backing = self.root / "game-manager-copy.dcx"
        backing.write_bytes(b"tampered")
        owned.unlink()
        try:
            owned.symlink_to(backing)
        except (OSError, NotImplementedError):
            self.skipTest("this platform does not allow creating symbolic links")

        with self.assertRaisesRegex(ValidationError, "owned overlay file size changed"):
            activate_build(self.install, build_b, process_is_running=lambda: False)

    def test_deactivate_and_restore_leave_the_user_directory_untouched(self):
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        before = snapshot_tree(self.install.user_mods)
        cache = SeedCache(self.root / "cache")
        binder_a = self.root / "a.dcx"
        binder_b = self.root / "b.dcx"
        binder_a.write_bytes(b"A")
        binder_b.write_bytes(b"B")
        build_a = cache.build(identity("seed-a", b"A"), binder_a).path
        build_b = cache.build(identity("seed-b", b"B"), binder_b).path
        activate_build(self.install, build_a, process_is_running=lambda: False)
        activate_build(self.install, build_b, process_is_running=lambda: False)
        restore_previous_build(self.install, cache, process_is_running=lambda: False)
        self.assertEqual(snapshot_tree(self.install.user_mods), before)
        deactivate_overlay(self.install, process_is_running=lambda: False)
        self.assertFalse(self.install.mods.exists())
        self.assertEqual(snapshot_tree(self.install.user_mods), before)
        self.assertEqual(len(before), 1)

    def test_a_symlink_in_the_user_directory_fails_closed(self):
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        link = self.install.user_mods / "dvdroot_ps4" / "chr" / "link.dcx"
        try:
            link.symlink_to(self.install.base)
        except (OSError, NotImplementedError):
            self.skipTest("this platform does not allow creating symbolic links")
        with self.assertRaisesRegex(ValidationError, "symbolic links are not allowed"):
            collect_user_mod_files(self.install.user_mods)

    def test_the_user_directory_is_the_documented_sibling_and_may_be_absent(self):
        self.assertEqual(self.install.user_mods.name, USER_MODS_DIR_NAME)
        self.assertEqual(self.install.user_mods.parent, self.install.root)
        self.assertFalse(self.install.user_mods.exists())
        # Witness that the collector is the one reporting nothing: the same
        # call finds the file once the directory exists.
        self.assertFalse(collect_user_mod_files(self.install.user_mods))
        write_user_mod(self.install, "dvdroot_ps4/chr/c0000.bnd.dcx", b"user-chr")
        self.assertEqual(
            list(collect_user_mod_files(self.install.user_mods)),
            ["dvdroot_ps4/chr/c0000.bnd.dcx"],
        )


class OverlayOwnershipCaseTests(unittest.TestCase):
    """The overlay lives on a case-insensitive filesystem; the manifest must too.

    An activation refused with the same map listed as both ``missing`` (spelled
    ``map/mapstudio``) and ``unowned`` (spelled ``map/MapStudio``), because
    ownership verification compared relative paths case-sensitively while
    Windows had folded the two spellings into one directory.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.install = make_install(self.root / "game")
        _cache, self.build = make_build(self.root / "build", "seed", b"sup", with_maps=True)
        self.owner = activate_build(self.install, self.build, process_is_running=lambda: False)
        self.owner_path = self.install.mods / OWNER_NAME
        self.map_relative = f"{MAP_PREFIX}m24_01_00_00.msb.dcx"

    def tearDown(self):
        self.temporary.cleanup()

    def _rewrite_owner(self, replace: str, with_: str) -> None:
        text = self.owner_path.read_text(encoding="utf-8")
        self.assertIn(replace, text)
        self.owner_path.write_text(text.replace(replace, with_), encoding="utf-8")

    def _rename_disk_map(self, spelling: str) -> None:
        maps = self.install.mods / "dvdroot_ps4" / "map"
        (maps / "MapStudio").rename(maps / f".tmp-{spelling}")
        (maps / f".tmp-{spelling}").rename(maps / spelling)

    def test_a_lowercase_recorded_map_verifies_against_a_mapstudio_disk_tree(self):
        # The live report: a manifest written before recording was canonical.
        self._rewrite_owner("map/MapStudio/", "map/mapstudio/")
        # Verification passes: the record and the disk file are one file.
        reloaded = core._load_owner(self.install.mods)
        self.assertEqual(
            [
                canonical_overlay_case(record["path"])
                for record in reloaded["files"]
                if record["path"] != SUPPRESSION_PATH
            ],
            [self.map_relative],
        )

    def test_a_lowercase_merged_user_record_verifies_against_the_folded_directory(self):
        write_user_mod(self.install, "dvdroot_ps4/map/MapStudio/m21_00_00_00.msb.dcx", b"user-map")
        owner = activate_build(self.install, self.build, process_is_running=lambda: False)
        self.assertEqual(
            [record["path"] for record in owner["user_merge"]["files"]],
            [f"{MAP_PREFIX}m21_00_00_00.msb.dcx"],
        )
        self._rewrite_owner(
            f"{MAP_PREFIX}m21_00_00_00.msb.dcx", "dvdroot_ps4/map/mapstudio/m21_00_00_00.msb.dcx"
        )
        reloaded = core._load_owner(self.install.mods)
        self.assertEqual(len(reloaded["user_merge"]["files"]), 1)

    def test_a_canonical_record_verifies_against_a_lowercase_disk_tree(self):
        self._rename_disk_map("mapstudio")
        reloaded = core._load_owner(self.install.mods)
        self.assertEqual(reloaded["cache_key"], self.owner["cache_key"])

    def test_recording_is_canonical_whatever_case_the_source_spelled(self):
        self.assertEqual(
            canonical_overlay_case("dvdroot_ps4/map/MAPSTUDIO/m21_00_00_00.msb.dcx"),
            f"{MAP_PREFIX}m21_00_00_00.msb.dcx",
        )
        self.assertEqual(
            canonical_overlay_case("DVDROOT_PS4/PARAM/GAMEPARAM/gameparam.parambnd.dcx"),
            SUPPRESSION_PATH,
        )
        write_user_mod(self.install, "dvdroot_ps4/map/mapstudio/m21_00_00_00.msb.dcx", b"user-map")
        owner = activate_build(self.install, self.build, process_is_running=lambda: False)
        self.assertEqual(
            [record["path"] for record in owner["user_merge"]["files"]],
            [f"{MAP_PREFIX}m21_00_00_00.msb.dcx"],
        )

    def test_a_genuinely_missing_owned_file_still_refuses(self):
        self.install.mods.joinpath(*self.map_relative.split("/")).unlink()
        with self.assertRaisesRegex(ConflictError, "missing=..dvdroot_ps4/map/MapStudio/"):
            core._load_owner(self.install.mods)

    def test_a_genuinely_unowned_file_still_refuses(self):
        intruder = self.install.mods / "dvdroot_ps4" / "map" / "MapStudio" / "m29_00_00_00.msb.dcx"
        intruder.write_bytes(b"not ours")
        with self.assertRaisesRegex(ConflictError, "unowned=..dvdroot_ps4/map/MapStudio/m29"):
            core._load_owner(self.install.mods)
        self.assertEqual(intruder.read_bytes(), b"not ours")

    def test_two_disk_files_differing_only_by_case_are_refused_not_folded(self):
        # Case-insensitivity must not silently accept a tree that could only
        # exist on a case-sensitive filesystem: one of the two is unowned.
        twin = self.install.mods / "dvdroot_ps4" / "map" / "mapstudio" / "m24_01_00_00.msb.dcx"
        twin.parent.mkdir(parents=True, exist_ok=True)
        twin.write_bytes(b"twin")
        with self.assertRaisesRegex(ConflictError, "differing only by case"):
            core._load_owner(self.install.mods)


if __name__ == "__main__":
    unittest.main()


class EnemizerPlanRetentionTests(unittest.TestCase):
    """bb-archipelago#321: the seed cache keeps the plan that built its maps."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_plan_is_retained_recorded_and_kept_out_of_the_overlay_file_set(self):
        cache, build_path = make_build(self.root, "seed", b"content", with_maps=True)
        result = cache.verify(build_path)
        record = result.manifest["enemizer"]["plan"]
        retained = build_path / core.ENEMIZER_PLAN_NAME
        self.assertTrue(retained.is_file())
        self.assertEqual(record["sha256"], sha256_file(retained))
        self.assertEqual(record["swap_count"], 1)
        self.assertEqual(record["options"], {"allow_tier_mixing": False, "preserve_locomotion": False})
        self.assertNotIn(core.ENEMIZER_PLAN_NAME, {r["path"] for r in result.manifest["files"]})

    def test_tampered_or_unrecorded_plan_refuses_verification(self):
        cache, build_path = make_build(self.root, "seed", b"content", with_maps=True)
        retained = build_path / core.ENEMIZER_PLAN_NAME
        retained.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "plan hash changed"):
            cache.verify(build_path)
        retained.unlink()
        with self.assertRaisesRegex(ValidationError, "missing its retained enemizer plan"):
            cache.verify(build_path)
        # A build made before retention (no record, no file) still verifies.
        manifest_path = build_path / core.SEED_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["enemizer"]["plan"] = None
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIsNone(cache.verify(build_path).manifest["enemizer"]["plan"])
        retained.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "manifest does not record"):
            cache.verify(build_path)

    def test_maps_without_their_plan_are_refused(self):
        inputs = self.root / "inputs"
        inputs.mkdir()
        binder = inputs / "binder.dcx"
        binder.write_bytes(b"binder")
        maps = inputs / "maps"
        maps.mkdir()
        (maps / "m24_01_00_00.msb.dcx").write_bytes(b"map")
        cache = SeedCache(self.root / "cache")
        with self.assertRaisesRegex(ValidationError, "require the enemizer plan"):
            cache.build(identity("seed", b"binder", enemizer_seed="x"), binder, maps)
        plan = inputs / "plan.json"
        plan.write_text(json.dumps(sample_plan("x")), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "without MapStudio outputs"):
            cache.build(identity("seed", b"binder"), binder, enemizer_plan=plan)
