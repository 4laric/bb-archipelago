from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from bb_launcher.core import (
    APP_VERSION,
    SESSION_HEADER_PREFIX,
    EXCLUDED_AP_OWNED,
    EXCLUDED_DEAD_PATH,
    EXCLUDED_RESERVED,
    MAP_PREFIX,
    MODS_DIR_NAME,
    OWNER_NAME,
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
    if with_maps:
        maps = inputs / f"{name}-maps"
        maps.mkdir()
        (maps / "m24_01_00_00.msb.dcx").write_bytes(b"map-" + content)
        seed = f"{name}:enemizer"
    cache = SeedCache(root / "cache")
    result = cache.build(identity(name, content, enemizer_seed=seed), binder, maps)
    return cache, result.path


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
        self.assertNotEqual(first.cache_key, identity("other").cache_key)

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


if __name__ == "__main__":
    unittest.main()
