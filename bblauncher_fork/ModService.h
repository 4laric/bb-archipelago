// SPDX-FileCopyrightText: Copyright 2024 BBLauncher Project
// SPDX-License-Identifier: GPL-3.0-or-later
//
// BBLauncher-AP fork: generic mod-service extraction (no AP logic).
// Extracted from modules/ModManager.cpp at upstream baseline ca12c2f so
// both the Mod Manager dialog and the AP coordinator share one owner of
// activation state. Dialog slots in ModManager become thin wrappers over
// this service; no UI button automation is involved.

#pragma once

#include <filesystem>
#include <functional>
#include <string>
#include <vector>

struct ModOperation {
    std::string modName;
    // Ordered file mutations with expected before/after digests; the
    // coordinator journals this plan outside movable mod folders before
    // committing, because a multi-file swap is not atomic.
    struct Mutation {
        std::filesystem::path relative;
        std::string expectedBefore; // empty when the path must be absent
        std::string expectedAfter;  // empty when the path will be removed
        bool reverseLast = false;   // restore in reverse commit order
    };
    std::vector<Mutation> mutations;
    // Exact reversible conflict plan: named third-party mods only.
    std::vector<std::string> conflictingMods;
};

struct ModServiceResult {
    bool ok = false;
    std::string error; // stable machine-readable code, not dialog prose
    std::vector<std::string> committed; // relative paths, commit order
};

class ModService {
  public:
    using Progress = std::function<void(int done, int total)>;
    using Cancelled = std::function<bool()>;

    ModService(std::filesystem::path modsRoot, std::filesystem::path installMods,
               std::filesystem::path backupRoot, std::filesystem::path activeRoot);

    // Read-only: enumerate inactive/active packages, conflicts, backup metadata.
    std::vector<std::string> InactiveMods() const;
    std::vector<std::string> ActiveMods() const;
    // "relative path, owning mod" pairs across active packages except ExcludeMod.
    std::vector<std::string> ModifiedFileList(const std::string& excludeMod) const;

    // Planned activation/deactivation. The service alone writes active mod
    // folders, overlay files and conflict backups. AP-owned packages must
    // not go through the Mod Merger.
    ModOperation PlanActivate(const std::string& modName, std::string* error) const;
    ModOperation PlanDeactivate(const std::string& modName, std::string* error) const;
    ModServiceResult Activate(const ModOperation& plan, Progress progress,
                              Cancelled cancelled);
    ModServiceResult Deactivate(const ModOperation& plan, Progress progress,
                                Cancelled cancelled);

    // Crash recovery: replay the external journal (written by the AP
    // backend under <state>/integrated/journal); restore only files with
    // established ownership and expected bytes; report user changes
    // instead of overwriting them. Never a whole-install reset.
    ModServiceResult Recover(const std::string& journalPath, Progress progress);

  private:
    std::filesystem::path m_modsRoot;
    std::filesystem::path m_installMods;
    std::filesystem::path m_backupRoot;
    std::filesystem::path m_activeRoot;
};
