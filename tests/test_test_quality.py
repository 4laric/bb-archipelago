"""Ratchets for test assertions that can pass without proving they saw data."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# These forms are not automatically wrong: several deliberately test empty
# results or validate every member of a separately witnessed collection. They
# are review debt, though, because the assertion itself cannot distinguish an
# empty input from complete coverage. Fourteen was the reviewed ceiling when
# this guard was requested; additions must replace or explicitly witness one.
WITNESSLESS_ASSERTION_CEILING = 14


def _empty_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"dict", "list", "set", "tuple"} and not node.args)


def witnessless_assertions(path: Path) -> list[tuple[int, str]]:
    """Find the narrow syntactic family covered by the ceiling."""
    hits: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        first = node.args[0] if node.args else None
        if method == "assertEqual" and any(_empty_literal(arg) for arg in node.args[:2]):
            hits.append((node.lineno, "empty equality"))
        elif (method in {"assertTrue", "assertFalse"} and isinstance(first, ast.Call)
              and isinstance(first.func, ast.Name)
              and (method, first.func.id) in {("assertTrue", "all"), ("assertFalse", "any")}):
            hits.append((node.lineno, f"{method}({first.func.id}(...))"))
    return hits


class WitnesslessAssertionRatchetTests(unittest.TestCase):
    def test_witnessless_assertion_family_stays_below_the_reviewed_ceiling(self):
        findings = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            if path == Path(__file__):
                continue
            findings.extend(f"{path.name}:{line} ({kind})"
                            for line, kind in witnessless_assertions(path))
        self.assertLessEqual(
            len(findings), WITNESSLESS_ASSERTION_CEILING,
            "witnessless-assertion ceiling exceeded; add a non-empty witness or reduce the family:\n"
            + "\n".join(findings),
        )

    def test_detector_covers_each_ratcheted_idiom(self):
        fixture = Path(__file__).with_name("fixtures") / "witnessless_assertions.py"
        self.assertEqual(
            ["empty equality", "assertTrue(all(...))", "assertFalse(any(...))"],
            [kind for _, kind in witnessless_assertions(fixture)],
        )
