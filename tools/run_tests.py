#!/usr/bin/env python3
"""Run the test suite and assert what it actually examined.

A green exit is not evidence. A gate that collects zero tests, or that silently
skips a whole tier because an import failed, passes exactly as loudly as one
that ran everything — and then the question is retired, because CI is green.

So this asserts the shape of the run, not just its result:

  --min-tests N        fail if fewer than N tests were collected
  --max-skips N        fail if more than N were skipped
  --require MODULE=N   fail unless MODULE contributed at least N tests and
                       skipped none of them

The third is the one that matters. tests/test_bloodborne_client.py skips itself
when Archipelago is not importable, which is correct locally and a silent hole
in CI. `--require test_bloodborne_client=12` turns that hole into a red.
"""

from __future__ import annotations

import argparse
import sys
import unittest
import os
from collections import defaultdict


def module_of(test: unittest.TestCase) -> str:
    return type(test).__module__.rsplit(".", 1)[-1]


class CountingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ran_by_module: dict[str, int] = defaultdict(int)
        self.skipped_by_module: dict[str, int] = defaultdict(int)

    def startTest(self, test):
        self.ran_by_module[module_of(test)] += 1
        super().startTest(test)

    def addSkip(self, test, reason):
        self.skipped_by_module[module_of(test)] += 1
        super().addSkip(test, reason)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-dir", default="tests")
    parser.add_argument("--top-level", default=None,
                        help="defaults to the start dir, matching `python -m unittest discover`")
    parser.add_argument("--min-tests", type=int, default=0)
    parser.add_argument("--max-skips", type=int, default=None)
    parser.add_argument("--require", action="append", default=[],
                        metavar="MODULE=N",
                        help="MODULE must contribute >= N tests and skip none")
    parser.add_argument("--expect-file", default=None,
                        help="TSV ledger of expected counts: 'total N' and 'module NAME N' rows. "
                             "Keeping it in the repo means raising the bar is a one-line data "
                             "edit in the commit that earns it, not a workflow rewrite.")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    args = parser.parse_args(argv)

    if args.expect_file:
        for number, line in enumerate(open(args.expect_file, encoding="utf-8"), 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            fields = line.split()
            try:
                if fields[0] == "total" and len(fields) == 2:
                    args.min_tests = max(args.min_tests, int(fields[1]))
                elif fields[0] == "max_skips" and len(fields) == 2:
                    args.max_skips = int(fields[1]) if args.max_skips is None else args.max_skips
                elif fields[0] == "module" and len(fields) == 3:
                    int(fields[2])
                    args.require.append(f"{fields[1]}={fields[2]}")
                else:
                    raise ValueError("unknown row shape")
            except (ValueError, IndexError) as exc:
                print(f"{args.expect_file}:{number}: malformed row {line!r}: {exc}", file=sys.stderr)
                return 2

    # The suite imports `worlds.bloodborne`, so the repo root has to be importable
    # regardless of where this was invoked from.
    root = os.path.abspath(args.top_level or os.getcwd())
    if root not in sys.path:
        sys.path.insert(0, root)

    suite = unittest.defaultTestLoader.discover(args.start_dir, top_level_dir=args.top_level)
    if unittest.defaultTestLoader.errors:
        for error in unittest.defaultTestLoader.errors:
            print(error, file=sys.stderr)
        print("COLLECTION ERROR: a test module failed to import", file=sys.stderr)
        return 2

    runner = unittest.TextTestRunner(verbosity=args.verbose, resultclass=CountingResult)
    result = runner.run(suite)

    print()
    print(f"collected {result.testsRun} tests, {len(result.skipped)} skipped")
    for module in sorted(result.ran_by_module):
        ran = result.ran_by_module[module]
        skipped = result.skipped_by_module.get(module, 0)
        print(f"  {module:<34} ran {ran - skipped:>3}  skipped {skipped:>3}")

    problems: list[str] = []
    if not result.wasSuccessful():
        problems.append("tests failed")
    if result.testsRun < args.min_tests:
        problems.append(f"collected {result.testsRun} tests, expected at least {args.min_tests}. "
                        "If tests were deliberately removed, lower --min-tests in the same commit.")
    if args.max_skips is not None and len(result.skipped) > args.max_skips:
        problems.append(f"{len(result.skipped)} skipped, at most {args.max_skips} allowed")
    for requirement in args.require:
        module, _, raw = requirement.partition("=")
        minimum = int(raw or 1)
        ran = result.ran_by_module.get(module, 0)
        skipped = result.skipped_by_module.get(module, 0)
        effective = ran - skipped
        if effective < minimum:
            problems.append(
                f"{module} contributed {effective} executed tests ({skipped} skipped), "
                f"expected at least {minimum}. This tier is not running — a skipped "
                f"test proves nothing, and CI is the only place it was going to run.")

    if problems:
        print()
        for problem in problems:
            print(f"GATE FAILED: {problem}", file=sys.stderr)
        return 1

    print("\nall gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
