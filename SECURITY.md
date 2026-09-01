# Security policy

## What the software does

The Bloodborne Archipelago client opens the running shadPS4 process and reads
game memory to observe the supported save, event flags, inventory, and runtime
state. It writes to game-process memory only through the documented native item
delivery path. These capabilities can resemble those of malware to heuristic
scanners even though they are narrowly used to connect Bloodborne to an
Archipelago session.

The launcher creates and activates a seed-specific overlay in the configured
shadPS4 game directory. It records every managed file in manifests, verifies
ownership before replacing anything, and provides an undo path. It does not
modify the user's base or update game trees.

## Release provenance

Official releases are built by this repository's public GitHub Actions
workflow. Release notes identify the workflow run and list SHA-256 hashes for
the launcher archive and `bloodborne.apworld`. Release artifacts are also
covered by GitHub build attestations and linked VirusTotal scans.

After installing the GitHub CLI, verify a downloaded launcher archive with:

```text
gh attestation verify BloodborneAPLauncher-win-x64.zip --repo 4laric/bb-archipelago
```

Compare its SHA-256 hash with the value in the same release's notes. A small
number of heuristic detections can still occur for signed tooling that reads
another process's memory; watch the major engines, consistency between
releases, and the provenance checks above.

## Reporting a vulnerability

Please do not disclose a suspected vulnerability in a public issue. Report it
privately through this repository's **Security** tab using **Report a
vulnerability** (GitHub Security Advisories), or contact the maintainers in the
project Discord. Include the affected release or commit, reproduction steps,
and any logs or proof of concept that can be shared safely.
