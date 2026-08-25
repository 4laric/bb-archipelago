#!/usr/bin/env python3
"""Fail if this repo's native-grant contract has drifted from the clients copy.

The clients repo (from-software-archipelago-clients) vendors a copy of
``bb-native-grant-contract.v5.json`` and guards it with
``Contract::assert_agrees_with_crate``. That guard only runs when the *clients*
CI runs, so a contract change made here reds nothing until someone touches the
client. This script closes that gap: it fetches the clients repo's vendored copy
and compares it, semantically, against this repo's source of truth, so drift reds
in the PR that creates it.

The comparison is canonical: both files are parsed as JSON and compared by value,
so key-order or whitespace differences never produce a false red. A fetch failure
is a failure, never a silent pass -- an unreachable clients copy is not evidence
of agreement.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# This repo's source of truth.
LOCAL_PATH = "research/runtime/bb-native-grant-contract.v5.json"

# The clients repo's vendored copy (public; unauthenticated raw fetch).
CLIENTS_REPO = "4laric/from-software-archipelago-clients"
CLIENTS_PATH = "crates/bb-archipelago/contract/bb-native-grant-contract.v5.json"
CLIENTS_URL = (
    f"https://raw.githubusercontent.com/{CLIENTS_REPO}/main/{CLIENTS_PATH}"
)


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _load_local(path: str) -> object:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_clients(url: str, file: str | None) -> object:
    if file is not None:
        # Local override, used only to exercise the comparison logic offline.
        with open(file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        # Fail loud: an unfetchable clients copy is not a green.
        sys.stderr.write(
            "ERROR: could not fetch the clients repo's vendored contract from\n"
            f"  {url}\n"
            f"  ({exc})\n"
            "This job fails closed: a fetch failure is not evidence of agreement.\n"
            "If raw.githubusercontent.com is rate-limited in Actions, re-run the job.\n"
        )
        raise SystemExit(2)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(
            f"ERROR: the clients copy fetched from {url} is not valid JSON: {exc}\n"
        )
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local",
        default=LOCAL_PATH,
        help="this repo's contract (default: %(default)s)",
    )
    parser.add_argument(
        "--url",
        default=CLIENTS_URL,
        help="raw URL of the clients repo's vendored copy",
    )
    parser.add_argument(
        "--clients-file",
        default=None,
        help="read the clients copy from a local file instead of fetching "
        "(for offline testing of the comparison logic only)",
    )
    args = parser.parse_args()

    local = _load_local(args.local)
    clients = _load_clients(args.url, args.clients_file)

    if _canonical(local) == _canonical(clients):
        print(
            "OK: the native-grant contract agrees with the clients repo's "
            "vendored copy."
        )
        return 0

    sys.stderr.write(
        "ERROR: native-grant contract drift detected.\n"
        f"  this repo:    {args.local}\n"
        f"  clients copy: {CLIENTS_REPO}:{CLIENTS_PATH}\n"
        "The two copies differ in value. If this repo's contract changed on\n"
        "purpose, re-vendor the clients copy (copy this repo's file over the\n"
        "clients path above and land it in the clients repo). Until then the\n"
        "clients crate's Contract::assert_agrees_with_crate guard is stale.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
