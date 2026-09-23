# Fork bundle layout (BBLauncher-AP)

```
BBLauncher-AP.exe
ap_backend/
  bb-ap-backend(.exe)          # frozen backend: python -m bb_launcher integrated-backend
  suppression/
    gameparam.parambnd.dcx     # seed-owned suppression binder (release-built)
    build-manifest.json        # its build manifest
  ap-client/
    bb-ap-client(.exe)         # pinned native AP client
```

The Qt side (`modules/ApBackend.cpp`) discovers the backend in order:
frozen bundle path, `BB_AP_BACKEND` env override, then a source
checkout (`BB_AP_SOURCE_ROOT` + python, development only).

The backend resolves the rest at `prepare_play` time without extra
player steps:

- suppression binder/manifest: explicit params win, else
  `<backend>/suppression/{gameparam.parambnd.dcx,build-manifest.json}`;
- process plan: explicit path wins, else generated hash-pinned from the
  fork-reported shadPS4/AP-client executables + seed identity + server
  under `<state>/integrated/plans/` (identical to the manual `plan`
  command's output for the same inputs);
- client runtime config + ledger: per seed/slot session directories
  under the state root, as before.

No receipt paths cross the Qt/backend protocol; Qt passes opaque
play/arm handles. The game start itself goes through the fork's
emulator service after arming, and its process identity is cross-checked
by the backend at connection time.
