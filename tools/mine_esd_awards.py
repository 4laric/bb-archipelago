#!/usr/bin/env python3
"""Mine item-lot awards from ESDLang-decompiled Bloodborne talk scripts.

This emits evidence, never suppression edits.  An award is safe to suppress only
after its lot, one-shot flag, interaction semantics, and a compilable ESD patch
have each been reviewed.  Unresolved calls remain in the report.
"""
from __future__ import annotations

import argparse
import ast
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.bb_inputs import DEFAULT_BUNDLE, read_prefix

AWARD_FUNCTIONS = {"AwardItemLot", "AwardItemLotWithoutAnyMessages"}
FLAG_FUNCTIONS = {"EventFlag", "GetEventFlag"}
MAX_DEPTH = 24


@dataclass(frozen=True, order=True)
class Award:
    source: str
    talk_id: str
    function: str
    line: int
    award_function: str
    item_lot: int | None
    resolution: str
    gate_flag: int | None
    gate_sense: int | None


def call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def integer(node: ast.AST, env: dict[str, int]) -> tuple[int | None, str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value, "literal"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value, how = integer(node.operand, env)
        return (-value, how) if value is not None else (None, how)
    if isinstance(node, ast.Name):
        return (env[node.id], "call_argument") if node.id in env else (None, "unresolved_name")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, _ = integer(node.left, env)
        right, _ = integer(node.right, env)
        if left is not None and right is not None:
            return left + right, "call_argument_expression"
    return None, "unresolved_runtime_expression"


def flag_test(node: ast.AST, env: dict[str, int]) -> tuple[int, int] | None:
    sense = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = flag_test(node.operand, env)
        return (inner[0], 1 - inner[1]) if inner else None
    target = node
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        target = node.left
        rhs, _ = integer(node.comparators[0], env)
        if rhs not in (0, 1):
            return None
        if isinstance(node.ops[0], ast.Eq):
            sense = rhs
        elif isinstance(node.ops[0], ast.NotEq):
            sense = 1 - rhs
        else:
            return None
    if isinstance(target, ast.Call) and call_name(target) in FLAG_FUNCTIONS and target.args:
        value, _ = integer(target.args[0], env)
        return (value, sense) if value is not None else None
    return None


class Miner:
    def __init__(self, source: str, text: str):
        self.source = source
        self.talk_id = re.sub(r"\D", "", Path(source).stem) or Path(source).stem
        tree = ast.parse(text, filename=source)
        self.defs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        called = {call_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        self.roots = [name for name in self.defs if name not in called] or list(self.defs)
        self.awards: list[Award] = []

    def run(self) -> list[Award]:
        for root in self.roots:
            self.walk(self.defs[root].body, {}, (), (root,), root)
        # Preserve direct sites unreachable through the decompiler's call graph.
        visited = {(a.function, a.line) for a in self.awards}
        for name, function in self.defs.items():
            direct = [(call_name(n), n.lineno) for n in ast.walk(function)
                      if isinstance(n, ast.Call) and call_name(n) in AWARD_FUNCTIONS]
            if any((name, line) not in visited for _, line in direct):
                self.walk(function.body, {}, (), (name,), name)
        return sorted(set(self.awards))

    def walk(self, nodes, env, gates, stack, owner):
        for node in nodes:
            if isinstance(node, ast.If):
                gate = flag_test(node.test, env)
                self.walk(node.body, env, gates + ((gate,) if gate else ()), stack, owner)
                opposite = (gate[0], 1 - gate[1]) if gate else None
                self.walk(node.orelse, env, gates + ((opposite,) if opposite else ()), stack, owner)
                continue
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                name = call_name(call)
                if name in AWARD_FUNCTIONS:
                    value, resolution = integer(call.args[0], env) if call.args else (None, "missing_argument")
                    gate = gates[-1] if gates else (None, None)
                    self.awards.append(Award(self.source, self.talk_id, owner, call.lineno,
                                             name, value, resolution, gate[0], gate[1]))
                elif name in self.defs and name not in stack and len(stack) < MAX_DEPTH:
                    child_env = {}
                    for keyword in call.keywords:
                        if keyword.arg:
                            value, _ = integer(keyword.value, env)
                            if value is not None:
                                child_env[keyword.arg] = value
                    self.walk(self.defs[name].body, child_env, gates, stack + (name,), name)


def sources(root: Path | None, bundle: Path) -> dict[str, str]:
    if root:
        return {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8-sig")
                for path in sorted(root.rglob("*.py")) if path.stat().st_size}
    return {name: blob.decode("utf-8-sig")
            for name, blob in read_prefix(bundle, "talk/").items()}


def write(rows: list[Award], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        fields = ["source", "talk_id", "function", "line", "award_function", "item_lot",
                  "resolution", "gate_flag", "gate_sense", "suppression_status"]
        writer = csv.DictWriter(handle, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            data = row.__dict__.copy()
            data.update({"item_lot": "" if row.item_lot is None else row.item_lot,
                         "gate_flag": "" if row.gate_flag is None else row.gate_flag,
                         "gate_sense": "" if row.gate_sense is None else row.gate_sense,
                         "suppression_status": "review_required"})
            writer.writerow(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="directory of ESDLang *.py files")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=Path("research/esd/talk_awards.tsv"))
    parser.add_argument("--allow-empty", action="store_true", help="diagnostic use only")
    args = parser.parse_args(argv)
    corpus = sources(args.root, args.bundle)
    if not corpus:
        print("no talk corpus found; rebuild research/bb_inputs.db or pass --root", file=sys.stderr)
        return 0 if args.allow_empty else 2
    rows = [award for name, text in corpus.items() for award in Miner(name, text).run()]
    if not rows and not args.allow_empty:
        print("talk corpus contained zero recognized award calls", file=sys.stderr)
        return 2
    write(rows, args.output)
    unresolved = sum(row.item_lot is None for row in rows)
    print(f"mined {len(rows)} award paths from {len(corpus)} scripts; {unresolved} unresolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
