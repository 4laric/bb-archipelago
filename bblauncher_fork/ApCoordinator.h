// SPDX-FileCopyrightText: Copyright 2024 BBLauncher Project
// SPDX-License-Identifier: GPL-3.0-or-later
//
// BBLauncher-AP fork: AP session coordinator (AP-specific; not for upstream).
// The coordinator sequences Inspect -> Prepare -> Plan -> Activate ->
// Verify/arm -> Start -> Connect -> Playing against the machine-readable
// backend (bb_launcher/integrated, protocol bb-ap-integration-v1) over a
// QProcess-managed backend with JSON-lines on stdin/stdout. Stdout is
// protocol-only; logs use stderr/files. Requests carry protocol version,
// operation id and sequence; Qt passes opaque play/arm handles, never
// receipt paths.
//
// Ownership recap: ModService alone writes the overlay; the backend alone
// owns preparation, receipts, boot proof, runtime config, ledgers and
// client supervision; the native client stays a separate process. Final
// process/activation checks and client spawning stay together in the
// backend to avoid a handoff gap. All startup paths (RunGame,
// RestartEmulator, IPC, no-GUI/shortcuts) funnel through AP preflight;
// repeated Play reuses the live session instead of spawning duplicates.
// The GUI-owned command backend and the persistent session supervisor
// have distinct lifetimes: destroying the GUI QProcess must not destroy
// the supervisor, and reattachment validates executable, process creation
// identity and session, not PID alone.

#pragma once

#include <string>

// Starts the bundled backend (argument array, no shell), negotiates
// capabilities, and runs one Play operation to completion. Returns a
// stable error code from docs/SPEC-bblauncher-integrated-ap.md recovery
// table on failure; Qt maps codes to player-facing copy with recovery
// actions. Red states always include a recovery action; ordinary waits
// (title/loading/reconnect/first discovery) stay neutral and never ask
// the player to consume an item.
struct ApPlayRequest {
    std::string gameRoot;
    std::string seedPath;   // .zip (MVP) accepted directly
    std::string playerName; // only when the seed is multi-slot
    std::string server;     // only when seed metadata does not supply it
    std::string password;   // only when needed; never logged, never in argv
};

std::string ApCoordinatorPlay(const ApPlayRequest& request);
std::string ApCoordinatorReturnToGame(const std::string& playId);
std::string ApCoordinatorQuitToRegularPlay(); // removes AP package via ModService
