"""Build the standard Archipelago Locations page from reviewed naming data."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAMES = ROOT / "worlds/bloodborne/location_names.tsv"
EVIDENCE = ROOT / "docs/location_landmark_evidence.tsv"
OUTPUT = ROOT / "worlds/bloodborne/docs/locations_en.md"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def render() -> str:
    evidence = {row["location_flag"]: row for row in rows(EVIDENCE)}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows(NAMES):
        grouped[row["region"]].append(row)

    lines = [
        "# Bloodborne Locations", "",
        "[Game Page] | [Items] | Locations", "",
        "[Game Page]: /games/Bloodborne/info/en",
        "[Items]: /tutorial/Bloodborne/items/en", "",
        "Tracker names retain the vanilla pickup as a recognizable handle. "
        "A parenthetical landmark tells you which physical spot the check replaces; "
        "numbered entries remain numbered so existing hints and spoilers stay stable.", "",
        "Landmarks are added only after the item lot, acquisition flag, map placement, "
        "and a human-readable source can be joined. A bare or numbered name means the "
        "exact landmark is still unresolved, not that the pickup is missing.", "",
    ]
    for region in sorted(grouped):
        lines.extend((f"## {region}", ""))
        for row in sorted(grouped[region], key=lambda item: item["name"]):
            detail = evidence.get(row["location_flag"])
            suffix = ""
            if detail:
                suffix = f" — {detail['landmark']}."
            lines.append(f"- {row['name']}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
