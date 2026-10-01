# Two local Bloodborne co-op sessions: staged test plan

Status: prepared; **no game session has been run or authorized by this plan**.
Follow [the live-probe contract](CONTRIBUTING-LIVE-PROBES.md). This is a sequence
of bounded experiments, not a request to play through the game. Stop at each
stage and review its bundle before scheduling the next.

## Question and evidence boundary

Can this laptop sustain two usable clients, pair them through the experimental
fork, and preserve the expected state through disconnect/reload? Shared world
progression is a separate hypothesis, not a prerequisite we assume.

Read-only hardware inventory on 2026-09-27: Core Ultra 9 275HX (24 logical CPUs),
32 GB RAM, RTX 5070 Ti Laptop with 12,227 MiB VRAM. Only about 7 GiB RAM was
available with no game running. Capacity is unmeasured; close nonessential
applications before the eventual session. Do not terminate anything automatically.

Static review targets:

- [shadp2p 6e97b404](https://github.com/Wozzardman/shadp2p/tree/6e97b404d6f89e7dab58f98c69678b69af9a3c4f)
- [shadnet-p2p 5a849a19](https://github.com/Wozzardman/shadnet-p2p/tree/5a849a192fd4450593c57b10697316ac324c856e)
- CUSA03173, AppVer 01.09; record the actual eboot hash before any run.

The author's [paired-run notes](https://github.com/Wozzardman/shadp2p/blob/6e97b404d6f89e7dab58f98c69678b69af9a3c4f/documents/bloodborne-seamless-re.md#validated-paired-cross-map-run)
report Dream-to-Great-Bridge joining and synchronized combat. They do not
establish our hardware capacity, persistent shared boss progression, or working
lantern travel. No local paired-session capture bundle was produced in this task;
upstream prose is not a substitute for one. No raw upstream capture was replayed.

## Instrument prepared now

`tools/coop_diagnostics.py` and `tools/coop_resource_snapshot.ps1` are an external,
read-only OS sampler. They never launch a game/server, inject a hook, write game
memory, alter configuration, or touch saves. Python 3.11+ and Windows PowerShell
or pwsh are required. NVIDIA metrics use `nvidia-smi` when available.

Each fresh JSONL records:

- logger/sampler SHA-256, role-to-PID mapping, executable path/hash and process
  creation time; PID reuse or process disappearance ends the capture;
- total/available system RAM, per-process working set, private bytes and
  cumulative CPU seconds, and whole-device GPU VRAM/utilization/temperature/power;
- UTC milliseconds (compatible with upstream trace timestamps), monotonic
  timestamps, a writer sequence, polling lag/duration and skipped polling slots;
- labeled operator markers in that same stream and an explicit final reason.

This is **not** an event-flag, inventory, FPS, frame-time, or per-process GPU
probe. GPU readings include every application on that device. Unsupported GPU
fields are null, not zero. CPU seconds are cumulative; divide their difference
by elapsed seconds for cores consumed, or additionally by logical CPU count
for machine-normalized utilization. Working sets can share pages; do not sum
them as an exact machine memory requirement. Monitor available RAM as well.

Samples are not simultaneous across all providers. Read their start/end times.
Input markers are timestamped immediately when received, then written by the
single writer; file sequence reflects write order. Sort by monotonic timestamp
when a marker arrives during a sample. A provider call can take up to 20 seconds
across its two bounded subprocesses. A sampling gap is never a count of missed
game calls. Missing footer, unavailable telemetry, identity failure, or a gap
covering the relevant action makes that portion inconclusive.

Offline controls: `python -m unittest discover -s tests -p test_coop_diagnostics.py`.
The Windows control samples the test process, plants a 64 MiB allocation, and
requires at least a 48 MiB private-byte increase. Other tests cover missing
processes, PID reuse, failed installation, marker clocks, unavailable GPU data,
failure footers and refusing to overwrite a capture. These validate the resource
instrument only. They do not validate the fork's game hooks.

Preparation result on 2026-09-27: the Windows planted-allocation control passed
on this laptop without launching a game. Repeat it after logger changes; it
does not replace the in-session PID/marker/device controls below.

Event investigations may use the fork's existing flags in **both process-local
environments**, not global Windows environment variables:

```text
SHADPS4_BLOODBORNE_SEAMLESS_COOP=1
SHADPS4_CAPTURE_BLOODBORNE_SUMMON=1
SHADPS4_BLOODBORNE_RE_TRACE=1
```

Keep RE_TRACE and HTTP capture **off during the initial capacity baseline**;
measure their overhead separately before using an instrumented performance result.
The existing RE trace samples sites after their first 64/2048 hits (then every
300th), and a partial hook installation can still leave a capture file. Its
sequence is not proof of complete event coverage. Require a matching log line
showing all hooks installed, the expected patch flags and eboot base in the
header, and a positive control in that run. Never infer absence of a game event
from this trace. No new native hook or GPL source is copied into this repository.

## Preparation gate for the future run

1. Record a manifest in a new `work/coop/<session>/` directory: date; repository
   commits and dirty state; both emulator and server executable hashes; eboot
   hash/serial/version; enabled patches; renderer/resolution/FPS target; driver
   version; A/B profile IDs, account aliases, UDP ports, cache/save paths; and
   hashes of the disposable starting save copies. Never put passwords in it.
2. Use two disposable local profiles/saves and distinct shadNet accounts. Keep
   the normal player's save outside the test profiles. Record a rollback copy
   while both clients are stopped. Verify the profile/save mapping before loading.
3. The inspected fork supports per-process `--user-id` and `--cache-dir`.
   Create distinct existing cache directories; do not let two processes write
   one pipeline cache. Verify actual CLI help on the selected build before use.
   Set distinct process-local `SHADPS4_P2P_PORT` values, e.g. 31401 and 31402,
   after checking they are free. Server uses its separate 31313/31314/31315 ports.
4. Run both clients on the NVIDIA GPU, plugged in, at 720p and 30 FPS initially.
   Use existing reviewed performance patches only; keep patch sets identical.
   Disable pause-on-focus-loss if enabled; verify the unfocused client keeps
   simulating. Start with AP client/bridge and randomized overlays disabled.
5. For local pairing, start with server endpoints on loopback on this same
   machine. Verify the actual P2P endpoints advertised in logs are reachable;
   local NAT/signaling behavior is still a test variable. Do not expose ports
   publicly or change firewall rules as a speculative fix. A connection failure
   with ample resources is not a hardware failure.
6. Preserve A/B emulator logs, server log, resource JSONL and optional
   `captures/bloodborne-re/` and `captures/bloodborne-summon/` outputs separately.
   Raw network captures can contain account/session identifiers; review before
   sharing. Do not commit saves, game files, credentials, or raw captures.

## Operator markers and capture commands (future use only)

Use the real emulator PID, not the launcher PID. Omit guest PID for a single
client baseline. Start a new capture for each process restart/role change;
never reattach silently to a reused PID.

```powershell
python -m tools.coop_diagnostics record --host-pid <A_PID> --output work/coop/<session>/single.jsonl --duration 300
python -m tools.coop_diagnostics record --host-pid <A_PID> --guest-pid <B_PID> --output work/coop/<session>/paired.jsonl --duration 600
```

In the capture console, enter `mark A <label>`, `mark B <label>`,
`mark both <label>`, or `stop`. These are operator reports, not automated game
witnesses. For every action below: five seconds quiet, `<action>_before` marker,
action, `<action>_after` marker, five seconds quiet. Use `mark operator
control_begin` as the first marker and confirm it appears in the JSONL before
continuing. Record observed FPS/stalls as marker text or a timestamped video;
the resource sampler cannot supply them.

## Stage 0: capacity and instrument controls

Budget: 12 minutes including loading/capture; two launches, zero restarts;
disposable saves required. Decision: is one-machine testing usable at 720p/30?
Use the nearest safe area already available on the disposable saves; no boss
travel is justified for a resource question.

Prediction: two loaded clients remain interactive with adequate RAM/VRAM margin.

1. Start only A when a run is explicitly authorized. Begin `single.jsonl`.
   Positive control: `ready` identifies A's correct executable/hash/PID and
   nonzero memory, marker round-trip works, GPU reports the expected device.
   An unavailable NVIDIA memory reading blocks the GPU-capacity conclusion.
2. Label `A_idle`, idle 30 seconds; label `A_move`, move 30 seconds; label
   `A_reload`, perform one ordinary safe load and observe 30 seconds. Record FPS.
3. Stop single capture, start B, begin paired capture. Verify both PID identities.
   Label `both_idle` and observe 60 seconds; label `A_active_B_background` and
   move A 30 seconds; swap focus and repeat `B_active_A_background`.
4. Stop at the budget or earlier thresholds below. No co-op server is required.

Thresholds below are conservative **project test choices**, not emulator facts.
Three consecutive valid samples at five-second intervals define sustained
memory pressure. One sample plus a severe stall is sufficient to stop early.

| Result | Distinguishing evidence | Decision |
| --- | --- | --- |
| Capacity provisionally passes | Both active/background sessions move normally; roughly 30 FPS by observation; available RAM stays above 4 GiB and at least 1 GiB VRAM free during sampled windows | Proceed to bounded pairing; not a whole-game performance guarantee |
| Resource pressure | Available RAM below 2 GiB or GPU memory above 95% sustained, allocation error, or severe stalls concurrent with pressure | Stop both manually; analyze what dominates before choosing a lower setting or another machine |
| Intermediate/partial | 2–4 GiB RAM margin, less than 1 GiB VRAM margin, or poor FPS without memory pressure | Inconclusive capacity; inspect CPU/GPU load, focus behavior and trace settings offline |
| Instrument failure | Wrong PID, unavailable metrics, identity failure, missing marker/footer, large sample gaps | Stop, preserve bundle, repair instrument; no capacity conclusion |

Stop immediately on save/profile mismatch, an allocation crash, unresponsive
system, or any unexpected behavior. Never keep running to reproduce a crash.

## Stage 1: same-map connection and instrumentation

Budget: 8 minutes including server/setup once prepared; two client launches,
zero retries/restarts. Decision: can two processes on this host form and sustain
one session? Use the nearest ordinary co-op-enabled area, with its boss alive,
and both characters already equipped with bells. No AP overlay/client.

1. Start the server and both clients with matching seamless mode and the
   diagnostic flags. Confirm distinct accounts authenticate, distinct P2P ports,
   and correct profiles. The `/status` response controls server HTTP reachability.
2. Step 0 control: all hooks must report installation, with matching header/base;
   both resource identities and the marker round-trip must pass. The bell
   actions in step 3 are also the native/HTTP positive controls: require the
   corresponding labeled action in each native trace and HTTP capture. A missing
   control stops the test; it does not mean the bell action did not happen.
3. Label A `beckoning`, then B `resonant`, ringing each bell once. Do not ring
   again for a separate control (that can change bell state). Allow 60 seconds to join. Once joined,
   label and move A, then B, and observe each on the other client. Hold two minutes.
   Record whether diagnostic overhead changed the capacity result.

| Result | Distinguishing evidence | Decision |
| --- | --- | --- |
| Connected | Broker match/claim, room join/signaling, and bilateral visible movement | Same-machine pairing observed; proceed to cross-map test |
| No match | Authentication/HTTP controls pass but broker returns no eligible candidate before deadline | Inspect account/password/map/mode configuration offline |
| Match but no gameplay | Broker claims candidate but room/P2P fails or only one client sees movement | Transport/insertion defect; preserve endpoint logs; do not blame graphics |
| Control/timeout/unexpected | Missing controls, partial hook installation, crash, or any other result | Stop; no retry without a revised explanation and outcome table |

## Stage 2: cross-map summon

Budget: 8 minutes; two launches, zero retries. Use prepared disposable saves to
reproduce the author's Dream-to-Great-Bridge pair if available; otherwise name
and justify the nearest prepared map pair in the manifest. Do not spend a session
playing to acquire a fixture. Decision: does cross-map relocation work locally?

Repeat stage 1 installation/marker controls, using this summon's one pair of
bell actions as the native/HTTP controls. Label each initial map, A's beckoning and B's response.
Allow 90 seconds. Require broker Preparing, host-placement header, guest stage
transition, renewed advertisement at destination, room join, then bilateral
movement. Record the actual host/guest coordinates/maps from traces.

| Result | Evidence | Decision |
| --- | --- | --- |
| Full success | All transitions above and both players visibly present | Cross-map joining observed for this map pair only |
| Preparation only | Header delivered, but guest does not arrive | Guest warp/resume lane; inspect native trace |
| Arrival only | Guest at destination, but no bilateral session | Matchmaking/P2P/insertion lane |
| Wrong placement/loop | Wrong map, out-of-bounds placement, repeated unsolicited warp | Stop immediately; placement/consumption defect |
| Missing control/timeout | No trustworthy trace of the relevant step | Diagnostic miss; repair offline, no speculative retry |

## Stage 3: death and resummon, then lantern behavior

Budget: 10 minutes per independently scheduled experiment; two launches and
at most one planned reload, no retries. Repeat the instrumentation controls.
Use a safe prepared area and a nearby reliable death/reset opportunity.

Death hypothesis: a guest death ends its visit but a fresh summon can succeed.
Label guest death, respawn, and fresh bells. Allow 60 seconds after fresh bells.
Disconnect plus successful resummon establishes recoverability; a retained
broker record with failed rejoin points to cleanup; a crash or invalid capture
stops the session. Never infer persistent session survival from retained broker
records alone. Host death is a separate future experiment.

Lantern hypothesis: the inspected build still lacks the host's prompt while
joined. Control the same lamp's visible prompt while solo first. After joining,
label host approach/interact and guest approach/interact. If neither prompt
appears, while solo control and live session both passed, the user-visible
limitation is reproduced. If host travel works but guest stays, classify
host-only travel. If both travel and remain joined, record the destination and
test one movement each. A hook reporting `applied` alone proves none of these.
Do not patch an additional gate during the session.

## Stage 4: persistent progression (design gate, not ready to run)

Budget ceiling: 15 minutes with prepared pre-boss saves; two launches plus one
solo reload per client (four client starts total). No long boss approach.
Decision: whether shared progression exists for one named boss and which AP
check owner policy we need. This phase requires a separately reviewed **read-only**
flag snapshot instrument for two explicitly selected PIDs. Do not use a tool
that picks the first process named shadPS4. No new flag reader is claimed here.

Candidate fixture: Cleric Beast at Great Bridge, flag `12411700`, sourced from
`worlds/bloodborne/runtime_bindings.py` and the committed EMEVD evidence. This
is a proposed fixture, not proof the flag behaves identically for a guest.
Before scheduling, review existing captures and require a positive/negative
flag-reader control using known defeated/undefeated disposable fixtures on
**each** PID, verified image/base, and explicit read errors. Capture flags, not
just entire-save hashes (position/autosave changes also change those hashes).

With those gates passed: both initially undefeated; mark before/after the
single boss kill; snapshot both flags; leave normally and save; close both;
reload each separately offline; snapshot again and inspect both boss arenas.
No AP delivery/client runs, so it cannot supply the state under investigation.

| Persistent result after separate solo reloads | Interpretation |
| --- | --- |
| Host true, guest false, matching arena states | Host-only progression for this boss |
| Both true, both boss arenas completed | Shared boss progression for this fixture only |
| Guest true during session, false after reload | Transient synchronization, not durable shared progression |
| Flags/arena disagree, neither changes, or controls fail | Invalid/unresolved; inspect save-slot and flag semantics offline |

AP testing comes later with identical seed/overlay witnesses on both clients,
explicit ownership of checks and received items, and checks for host-only event
paths. Include the [altar witness](LAURENCE-SKULL-WITNESS.md) and
[Hemwick multiplayer boundary](HEMWICK-ACCESS-GATE.md); never globally remove
multiplayer-client guards to make a test pass.

## Stop, restore, report

Stop captures with `stop`; close both clients normally, then server. Archive the
manifest/logs/JSONL and exact binary hashes before changes. Restore only the
disposable save copies while clients are stopped; never overwrite the normal
profile. Process-local environment changes end with those launch terminals.
Keep caches separate. No global settings/firewall changes are part of this plan.

Each report lists the stage, positive controls, actual elapsed time, labels,
observations, missing telemetry, chosen outcome-table row, and next engineering
decision. For native trace interpretation restate each process's eboot base.
Call unverified static conclusions inferred, runtime sightings observed, and
only controlled persistent results validated within the tested fixture/build.
