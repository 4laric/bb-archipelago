#!/usr/bin/env python3
"""
install_apworld.py -- install worlds/bloodborne into an Archipelago checkout, without PowerShell.

`build.ps1 -Apworld` packages the world into `build/bloodborne.apworld`, and it is the only
packaging path this repo had. That is a problem for anything that is not a Windows developer
box: the deploy image's `bbtools` stage builds on Linux and needs the world laid out in an
Archipelago tree, and CI would otherwise have to shell out to pwsh to get it. This is the Linux
and Windows equivalent, and the direct analogue of er-archipelago's `tools/gf_test.py
--install-only --ap-dir DIR`.

WHAT GETS COPIED, AND WHY IT MATCHES build.ps1 EXACTLY. `build.ps1 -Apworld` takes every file
under `worlds\\bloodborne` except `__pycache__` directories and `.pyc` / `.pyo` / `.bak` files.
Two packagers with two different ideas of what a world contains is how a data table ends up in
the zip but not in the image, so the exclusion rule is stated once here in the same terms and
asserted by tests/test_site_assets.py against build.ps1's own text.

    python tools/install_apworld.py --ap-dir /opt/archipelago
    python tools/install_apworld.py --ap-dir . --dry-run

The destination is `<ap-dir>/worlds/bloodborne`, replaced wholesale: an install that merged into
an existing directory would leave a file deleted upstream sitting in the tree, still importable,
for exactly as long as it takes to cause a confusing bug.
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "worlds", "bloodborne")

EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".bak")


def files():
    """Every packaged file, as a path relative to worlds/bloodborne, sorted for determinism."""
    out = []
    for base, dirnames, filenames in os.walk(SOURCE):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if name.endswith(EXCLUDED_SUFFIXES):
                continue
            out.append(os.path.relpath(os.path.join(base, name), SOURCE).replace("\\", "/"))
    return sorted(out)


def install(ap_dir, dry_run=False):
    worlds = os.path.join(ap_dir, "worlds")
    if not os.path.isdir(worlds):
        # Refuse a plausible-looking wrong directory rather than creating `worlds/` inside it:
        # an apworld installed next to nothing generates nothing, and says so only much later.
        raise SystemExit("[FAIL] %s has no worlds/ directory -- is that an Archipelago checkout?"
                         % ap_dir)

    destination = os.path.join(worlds, "bloodborne")
    names = files()
    if dry_run:
        print("[dry-run] would install %d file(s) into %s" % (len(names), destination))
        return names

    if os.path.exists(destination):
        shutil.rmtree(destination)
    for name in names:
        target = os.path.join(destination, name.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(SOURCE, name.replace("/", os.sep)), target)
    print("[ok] installed %d file(s) into %s" % (len(names), destination))
    return names


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--ap-dir", required=True,
                        help="the Archipelago checkout to install into")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be installed and change nothing")
    args = parser.parse_args(argv)
    install(os.path.abspath(args.ap_dir), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
