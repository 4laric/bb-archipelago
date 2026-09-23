"""PyInstaller entry point for the fork's frozen AP backend.

Produces `bb-ap-backend` (console, onedir): the machine-readable
JSON-lines backend the forked launcher spawns. See
bblauncher_fork/BUNDLE-LAYOUT.md for where the frozen output ships.
"""

import sys

from bb_launcher.cli import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "integrated-backend", *sys.argv[1:]]
    raise SystemExit(main())
