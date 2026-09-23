"""Fork identity, provenance and update-channel separation.

Upstream: rainmakerv3/BB_Launcher at the spec baseline
  ca12c2fc38b8ba485e508bde815e8ea8cb49ac10
(local checkout: work/BB_Launcher, branch codex/bblauncher-service-extraction).

The fork (proposed: 4laric/BB_Launcher-AP) is a distinct application with a
distinct configuration identity and update feed.  An update must never
replace the fork with upstream BBLauncher -- the updater channel below is
the mechanism, and fork builds are pinned explicitly rather than loosening
the existing exact-executable checks to accept arbitrary forks.
"""

from __future__ import annotations

from dataclasses import dataclass

UPSTREAM_REPO = "rainmakerv3/BB_Launcher"
UPSTREAM_BASELINE_COMMIT = "ca12c2fc38b8ba485e508bde815e8ea8cb49ac10"

FORK_REPO = "4laric/BB_Launcher-AP"
FORK_APP_NAME = "BBLauncher-AP"
FORK_CONFIG_DIR_NAME = "BBLauncher-AP"
FORK_UPDATE_FEED = "https://github.com/4laric/BB_Launcher-AP/releases/download/latest/fork-update.json"
UPSTREAM_UPDATE_ENDPOINTS = (
    "https://api.github.com/repos/rainmakerv3/BB_Launcher/releases",
)

# Explicitly accepted fork compatibility set, mirroring the companion's
# exact-build discipline: (fork commit, executable sha256) pairs only.
# Empty until a fork build completes live acceptance; membership is added
# by a reviewed change with acceptance evidence, never by loosening the
# check to "any 4laric build".
SUPPORTED_FORK_BUILDS: frozenset[tuple[str, str]] = frozenset()

SUPPORTED_GAMES = (("CUSA03173", "01.09"),)
SUPPORTED_PLATFORM = "win32-x64"
SUPPORTED_ACTIVATION_ROUTE = "copy"


@dataclass(frozen=True)
class ForkBuildPin:
    commit: str
    executable_sha256: str

    def normalized(self) -> "ForkBuildPin":
        from ..core import _require_sha256

        commit = self.commit.strip().lower()
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            from ..core import ValidationError

            raise ValidationError("fork build pin requires a full lowercase commit")
        return ForkBuildPin(
            commit, _require_sha256(self.executable_sha256.lower(), "fork executable")
        )


def is_supported_fork_build(commit: str, executable_sha256: str) -> bool:
    try:
        pin = ForkBuildPin(commit, executable_sha256).normalized()
    except Exception:
        return False
    return (pin.commit, pin.executable_sha256) in SUPPORTED_FORK_BUILDS


def fork_provenance_record() -> dict[str, str]:
    return {
        "upstream_repo": UPSTREAM_REPO,
        "upstream_baseline": UPSTREAM_BASELINE_COMMIT,
        "fork_repo": FORK_REPO,
        "fork_app": FORK_APP_NAME,
        "update_feed": FORK_UPDATE_FEED,
    }
