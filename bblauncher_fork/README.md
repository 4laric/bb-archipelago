# BBLauncher-AP fork records

Upstream: `rainmakerv3/BB_Launcher` at baseline
`ca12c2fc38b8ba485e508bde815e8ea8cb49ac10`.
Local checkout: `work/BB_Launcher` (ignored, not vendored), branch
`codex/bblauncher-service-extraction`. Proposed fork remote:
`4laric/BB_Launcher-AP`.

The round-1 sketch headers that lived here were superseded by the real
implementation. What is implemented, where, and how it was validated:

- Generic service extraction (upstream-offerable, no AP logic):
  `modules/ModService.*` (Qt-free activation owner with journaling),
  `modules/EmulatorService.*` (single launch funnel with process
  identity + preflight gate), `ModManager` rewritten as a thin dialog,
  `IpcClient::emulatorProcess()` accessor. Proven by
  `tests_cpp/modservice_test.cpp` (compiled with MSVC `cl`, no Qt):
  SHA-256 vectors, activate/deactivate with backup restore, conflict
  report, reverse-order rule, user-change refusal, reset, missing-backup
  path.
- AP integration (fork-only): `modules/ApFork.*` (fork identity +
  fork-only update channel), `modules/ApBackend.*` (JSON-lines protocol
  client), `modules/ApCoordinator.*` (choose-seed-to-Play flow + headless
  `--ap-seed`), `modules/ApPage.*` (usable AP dialog), `main.cpp`
  headless option, `CheckUpdate` fork retarget (fork assets require the
  `BBLauncher-AP` marker), `BB_AP_FORK` / `BB_AP_BUILD_TESTS` CMake
  options, `tests_cpp/apbackend_test.cpp` (QtTest harness driving the
  real backend, source and frozen).
- Backend (`bb_launcher/integrated/` in this repo + `python -m
  bb_launcher integrated-backend`): extended this round with
  fork-claimed process cross-checks, bundle suppression/plan resolution
  and plan auto-generation. Frozen via pinned PyInstaller 6.22.2
  (`packaging/backend_entry.py` -> `ap_backend/bb-ap-backend`); the
  frozen bundle reports world `0.1.0` / runtime `bb-0.1.0-r10`.
- Bundle layout: `BUNDLE-LAYOUT.md`. Update feed example:
  `fork-update.json`. License audit: `LICENSE-INVENTORY.md` (open items
  flagged; no public build may ship yet).

Local build (all under `work/toolchain/`, MSVC 19.44 + LLVM clang-cl
21.1.0 + Qt 6.10.0 + ninja 1.13.2): Debug + `BB_AP_FORK=ON` +
`BB_AP_BUILD_TESTS=ON` configures and builds clean; `ctest` passes;
the app launches offscreen and stays alive. Local-only cache flags
(`CRYPTOPP_DISABLE_ASM=ON`, absolute `ml64` path attempts) are
environment workarounds, not source changes. No game, saves, installs
or user launcher trees were touched; no live acceptance has run.
