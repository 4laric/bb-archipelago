from __future__ import annotations

import sys
from pathlib import Path


def _self_check() -> int | None:
    """Run the frozen-package check before importing any desktop UI code."""
    if "--self-check" not in sys.argv[1:]:
        return None
    index = sys.argv.index("--self-check")
    try:
        report = Path(sys.argv[index + 1])
    except IndexError as error:
        raise SystemExit("--self-check requires a report path") from error
    from bb_launcher.self_check import run_self_check

    return run_self_check(report)


if __name__ == "__main__":
    result = _self_check()
    if result is None:
        from bb_launcher.ui import main

        result = main()
    raise SystemExit(result)
