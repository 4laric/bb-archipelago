"""Pure helper for the client's ``/mark`` console command (issue #330).

CONTRIBUTING-LIVE-PROBES.md rule 3 requires a way to stamp an operator's label
into the capture stream at the moment it happens -- wall-clock recollection
after the fact is not a label. This is that stamp for the popup probe
(docs/NATIVE-ITEM-POPUPS.md): a small, append-only ``.jsonl`` file the client
writes to and the popup probe's summary reads from, kept deliberately separate
from the probe's own report so the client needs no import from
``tools/bb_native_delivery``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MARKS_FILENAME = "bb-probe-marks.jsonl"


def append_mark(path: Path, label: str, now=None) -> dict:
    """Append one ``{"kind": "mark", "label": ..., "at": ...}`` line.

    ``now`` is injectable for tests; it defaults to the current UTC time.
    Raises :class:`ValueError` on an empty label -- an unlabelled mark is not
    a label at all (CONTRIBUTING-LIVE-PROBES.md rule 3).
    """
    label = label.strip()
    if not label:
        raise ValueError("a mark needs a non-empty label")
    timestamp = (now or (lambda: datetime.now(timezone.utc)))()
    record = {"kind": "mark", "label": label, "at": timestamp.isoformat(timespec="seconds")}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_marks(path: Path) -> list[dict]:
    """Every mark in the file, ignoring blank and unparseable lines."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    marks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("kind") == "mark":
            marks.append(record)
    return marks
