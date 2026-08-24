"""Parse and match the byte strings the Cheat Engine tables use as gates.

Cheat Engine's ``assert(address, bytes)`` and ``AOBScan(pattern)`` share one
textual form: space-separated hex byte pairs, with ``??`` or ``*`` for a
wildcard. Reimplementing that parser is the whole of the "trivial, and it is the
AOB seed" row in the spec.
"""

from __future__ import annotations

from dataclasses import dataclass


class PatternError(ValueError):
    """The pattern text is not a legal Cheat Engine byte string."""


@dataclass(frozen=True)
class BytePattern:
    """A byte string with optional wildcards."""

    values: tuple[int | None, ...]

    def __len__(self) -> int:
        return len(self.values)

    @property
    def has_wildcards(self) -> bool:
        return any(value is None for value in self.values)

    def matches(self, data: bytes) -> bool:
        if len(data) < len(self.values):
            return False
        return all(
            expected is None or expected == actual
            for expected, actual in zip(self.values, data)
        )

    def find_all(self, haystack: bytes) -> list[int]:
        width = len(self.values)
        if width == 0:
            raise PatternError("cannot scan for an empty pattern")
        return [
            offset
            for offset in range(0, len(haystack) - width + 1)
            if self.matches(haystack[offset : offset + width])
        ]

    def to_text(self) -> str:
        return " ".join("??" if value is None else f"{value:02X}" for value in self.values)


def parse(text: str) -> BytePattern:
    tokens = text.replace(",", " ").split()
    if not tokens:
        raise PatternError("empty pattern")
    values: list[int | None] = []
    for token in tokens:
        if token in {"??", "**", "?", "*"}:
            values.append(None)
            continue
        if len(token) != 2:
            raise PatternError(f"expected a two-digit hex byte, got {token!r}")
        try:
            values.append(int(token, 16))
        except ValueError as error:
            raise PatternError(f"{token!r} is not a hex byte") from error
    return BytePattern(tuple(values))
