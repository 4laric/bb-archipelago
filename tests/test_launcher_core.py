from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from bb_launcher.core import (
    APP_VERSION,
    MAP_PREFIX,
    MODS_DIR_NAME,
    OWNER_NAME,
    SERIAL,
    SUPPRESSION_PATH,
    ConflictError,
    DiscoveryError,
    GameInstall,
    LaunchError,
    ProcessSpec,
    SeedCache,
    SeedIdentity,
    ValidationError,
    activate_build,
    deactivate_overlay,
    discover_game_install,
    discover_shad_executable,
    launch_processes,
    recover_activation,
    restore_previous_build,
    sha256_file,
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
        foreign = self.root / "eu-install"
        (foreign / "CUSA00900").mkdir(parents=True)
        (foreign / "CUSA00900-patch").mkdir()
        with self.assertRaisesRegex(
            ValidationError, r"found CUSA00900.*only CUSA03173 \(US\)"
        ):
            GameInstall.from_root(foreign)
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValidationError, "missing base game directory"):
            GameInstall.from_root(empty)

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

    def test_process_launch_refuses_an_incompatible_executable_hash(self):
        executable = self.root / "shadPS4.exe"
        executable.write_bytes(b"0.18.0")
        wrong = hashlib.sha256(b"other-build").hexdigest()
        with self.assertRaisesRegex(LaunchError, "executable hash mismatch"):
            launch_processes(
                [ProcessSpec("shadPS4", executable, expected_sha256=wrong)],
                popen=lambda *_args, **_kwargs: self.fail("hash mismatch started a process"),
            )


if __name__ == "__main__":
    unittest.main()
