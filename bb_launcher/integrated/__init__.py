"""Integrated BBLauncher/Archipelago backend (spec: docs/SPEC-bblauncher-integrated-ap.md).

This package is the machine-readable AP backend the forked BBLauncher Qt
interface drives.  Qt owns player choices and progress display; this package
owns preparation, receipts, boot proof, runtime configuration, ledgers and
client supervision.  It never writes BBLauncher's overlay directly -- the
fork's extracted native mod service is the sole writer of active mod
folders, overlay files and conflict backups.

Protocol summary (JSON-lines on stdin/stdout, protocol version +
operation id + sequence on every message; logs on stderr/files only):

  capabilities | inspect_install | inspect_seed | prepare_play |
  verify_and_arm | connect_and_start_client |
  session_status | stop_client | cancel_operation

Qt passes opaque play/arm handles.  Receipt paths never appear in
protocol traffic.
"""

from __future__ import annotations
