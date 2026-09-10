"""Build isolated multi-seed AI overlays from original inputs; never activate them."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.bb_enemizer.cli import main as plan
from tools.bb_enemizer.model import canonical_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dotnet", "writer", "inventory", "gameparam", "paramdef", "scripts", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--prefix", default="offline-audit")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count must be positive")
    # Refuse reuse rather than mixing this run's evidence with older outputs.
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
              for name in ("writer", "inventory", "gameparam", "paramdef")}
    results = []
    pairs = set()
    failed = False
    for index in range(args.count):
        seed = f"{args.prefix}-{index}"
        manifest = args.output / f"plan-{index}.json"
        status = plan(["--seed", seed, "--inventory", str(args.inventory), "--output", str(manifest)])
        if status:
            raise RuntimeError(f"planner failed for {seed}: {status}")
        document = json.loads(manifest.read_text(encoding="utf-8"))
        for swap in document["swaps"]:
            for destination in swap["destination_keys"]:
                pairs.add((canonical_map(destination.split(":")[0].split(".")[0]),
                           swap["target"]["think_param_id"]))
        output = args.output / f"scripts-{index}"
        command = [str(args.dotnet), str(args.writer), "--ai", str(manifest),
                   str(args.gameparam), str(args.paramdef), str(args.scripts), str(output), "--apply"]
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (args.output / f"writer-{index}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        result = {"seed": seed, "swaps": len(document["swaps"]), "passed": process.returncode == 0}
        if process.returncode == 0:
            receipt = json.loads(Path(str(output) + ".json").read_text(encoding="utf-8"))
            maps = receipt["maps"]
            result["maps"] = len(maps)
            result["scripts_added"] = sum(len(m["scripts_added"]) for m in maps)
            result["passed"] = all(m["missing_goals_after"] == 0 and
                hashlib.sha256((output / m["map"]).read_bytes()).hexdigest() == m["output_sha256"]
                for m in maps)
        failed |= not result["passed"]
        results.append(result)
        (args.output / "summary.json").write_text(json.dumps({
            "format": "bb-enemizer-seed-audit-v1", "passed": not failed,
            "input_sha256": inputs, "map_think_pairs": len(pairs), "seeds": results,
        }, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
