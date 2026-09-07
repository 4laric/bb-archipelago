#!/usr/bin/env python3
"""
gen_latest_json.py -- generate release/latest.json from the channel ledger and the contract.

The published feed a client update check reads: which version stable points at, which native
grant contract that build speaks, and where to get it.

    {"version": "0.1.0-beta.5", "contract": "441a8b0f", "url": "https://github.com/..."}

The ER verdict logic (`Current`, `SafeUpdate`, `ContractMoved`) transfers directly whenever a
Bloodborne client consumer is written: the client compares its own contract hash against
`contract`, and a change there means "this update is not a drop-in".

WHICH FILE THE CONTRACT HASH COMES FROM, AND WHY IT IS THE LOCAL ONE
--------------------------------------------------------------------
The spec names the clients repo's copy at
`crates/bb-archipelago/contract/bb-native-grant-contract.v5.json`. This tool hashes THIS repo's
copy at `research/runtime/bb-native-grant-contract.v5.json` instead, which is the same document:

  * `packaging/client-ref.txt` pins the exact clients commit every release is built against
    (currently `fcbdf5d37c5d32374c9047622f09f1391c7e8028`), and at that pin the two files are
    canonically identical -- verified when this tool was written;
  * `tools/check_contract_drift.py` fails CI the moment they stop agreeing.

So the local copy IS the contract as built into the release, and reading it keeps this tool
hermetic: no network, no second checkout, and a `--check` that a unit test can run.

The hash is over the CANONICAL JSON (`sort_keys`, compact separators), not the raw bytes, for the
same reason `check_contract_drift.py` compares canonically: a reformat of the file is not a change
of contract, and a client that decided otherwise would tell every player to reinstall over a
trailing newline.

Usage:
    python tools/gen_latest_json.py            # write release/latest.json
    python tools/gen_latest_json.py --check    # exit 1 if it is stale
"""
import argparse
import hashlib
import json
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNELS = os.path.join(ROOT, "release", "CHANNELS.tsv")
CONTRACT = os.path.join(ROOT, "research", "runtime", "bb-native-grant-contract.v5.json")
CLIENT_PIN = os.path.join(ROOT, "packaging", "client-ref.txt")
OUT = os.path.join(ROOT, "release", "latest.json")

REPO = "4laric/bb-archipelago"
# First N hex of the digest. The spec asks for "8+"; eight is what the ER feed publishes and what
# an ER-shaped consumer compares, so the two feeds stay comparable by eye.
CONTRACT_PREFIX = 8


def rows(path):
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            if line.strip() and not line.lstrip().startswith("#"):
                yield [part.strip() for part in line.rstrip("\n").split("\t")]


def stable_tag():
    """The LAST `stable` row wins: the ledger is append-only, so promotion is a new row."""
    tag = None
    for row in rows(CHANNELS):
        if len(row) >= 2 and row[0] == "stable":
            tag = row[1]
    if not tag or not tag.startswith("v"):
        raise SystemExit("release/CHANNELS.tsv has no tagged stable channel")
    return tag


def contract_hash():
    with open(CONTRACT, encoding="utf-8") as fh:
        document = json.load(fh)
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:CONTRACT_PREFIX]


def render():
    tag = stable_tag()
    payload = {
        "version": tag[1:],
        "contract": contract_hash(),
        "url": "https://github.com/%s/releases/tag/%s" % (REPO, tag),
    }
    return json.dumps(payload, separators=(", ", ": ")) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()

    if args.check:
        current = open(OUT, encoding="utf-8").read() if os.path.isfile(OUT) else None
        if current != text:
            print("DRIFT: release/latest.json is stale; run python tools/gen_latest_json.py")
            return 1
        print("--check: release/latest.json matches the channel ledger and the contract")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".latest.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(temporary, OUT)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    print("wrote release/latest.json (%s)" % text.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
