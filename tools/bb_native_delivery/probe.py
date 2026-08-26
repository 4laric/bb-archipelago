"""The storage-routing probe: a guided, stepwise session (#202, clients#445).

What it is for
--------------
oz's two full-seed clears left four questions about *where* a native grant
lands, and none of them can be answered by reading memory alone -- the
destination (held inventory vs the Hunter's Dream storage box) is visible only
in the game's UI. So this is a **guided operator session**: each step names what
to do in game first, then delivers exactly one controlled grant, records the
request/result cells and the held-stack read-back on both sides of it, and asks
the operator what the game showed.

The four questions, verbatim from clients#445 and its follow-up comment:

``H1`` -- return-value semantics
    The routine returns the new *held count* on a normal add (``native_result=8``,
    clients#443) and ``1`` when the item overflowed to storage
    (``native_result=1`` twice, at the pebble and molotov caps). ``inferred`` from
    two data points; this probe is what promotes or refutes it.
``H2`` -- a unique-item insert delivered idle in normal gameplay lands HELD.
    oz's Cheat-Engine-era control says yes for the Saw Spear; nothing has
    re-run it on the native stack.
``H3`` -- STICKY.
    After a vial/consumable add overflows at cap, does the *next* add -- a
    unique item, which no cap can explain -- also go to storage.
``H4`` -- state dependence.
    A delivery in the post-boss window, or while not in gameplay-idle.

Every step also records ``uses_persistent_source(raw)``, so the insert **source
lane** (persistent vs in_frame) can be ruled in or out as the explanation
(comment item 4).

What this module does NOT do
----------------------------
It changes no contract. ``research/runtime/bb-native-grant-contract.v5.json`` is
deserialized and guarded by the clients crate; a semantic edit is a cross-repo
step and ``tools/check_contract_drift.py`` would red it. Findings land in
``research/runtime/ASSUMPTIONS.md`` and in the pasteable summary this module
renders.

Every grant goes through the ordinary :class:`~.delivery.GrantSession`, so the
probe inherits the fail-closed policies rather than restating them: the
descriptor allowlist (#146), the image asserts, ``--expected-before`` semantics,
the loop-wide Ctrl+C disarm (#147), and the post-#434 rule that nothing outside
the guest ever writes a guest data page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .descriptor import (
    DescriptorError,
    describe_validated_descriptor,
    uses_persistent_source,
)

#: The only descriptors a probe step may name. Deliberately a *subset* of what
#: :func:`~.descriptor.describe_validated_descriptor` would accept: the probe is
#: a research session on a live save, so it names its three items by hand rather
#: than inheriting a formula. It is not a second allowlist with more reach --
#: every entry is checked against the real one too, and there is no escape hatch
#: on this subcommand at all (``--unvalidated-descriptor`` is a ``grant`` flag).
PEBBLE = (0xB000_04CE, 0x4000_04CE, "Pebble")
BLOOD_VIAL = (0xB000_03E8, 0x4000_03E8, "Blood Vial")
SAW_SPEAR = (0x806C_5660, 0x006C_5660, "Saw Spear")

PROBE_ITEMS = {name: (raw, normalized) for raw, normalized, name in (PEBBLE, BLOOD_VIAL, SAW_SPEAR)}

#: The held cap oz measured for both stackable canaries (clients#445: pebbles 20,
#: molotovs 10). Wording only -- nothing here depends on the number.
PEBBLE_HELD_CAP = 20
VIAL_HELD_CAP = 20

HELD = "held"
STORAGE = "storage"
SPLIT = "split"
UNKNOWN = "unknown"
OBSERVATIONS = (HELD, STORAGE, SPLIT, UNKNOWN)

SUPPORTED = "supported"
REFUTED = "refuted"
UNCLEAR = "unclear"

#: A step that has reached one of these is done and is skipped on resume.
TERMINAL_PROBE_STATUS = frozenset({"recorded", "skipped"})


class ProbeError(Exception):
    """A probe step is malformed, or the session cannot honestly continue."""


@dataclass(frozen=True)
class ProbeStep:
    """One question, one in-game setup, one grant, one observation."""

    step_id: str
    hypothesis: str
    item: str
    quantity: int
    #: What the operator must do IN GAME before the grant is armed.
    setup: str
    #: What to look at afterwards, in the words the prompt will use.
    observe: str
    #: Why this step exists, for the report and the runbook.
    rationale: str
    #: A unique item can be inserted only once per save (RESEARCH-BASELINE.md),
    #: so a session may contain at most one of these, and the pass that contains
    #: it is ordered around it.
    consumes_unique: bool = False
    #: ``a`` (idle-first) or ``b`` (sticky-first). See :data:`PROBE_PASSES`.
    pass_name: str = "a"

    @property
    def descriptor(self) -> tuple[int, int]:
        try:
            return PROBE_ITEMS[self.item]
        except KeyError:  # pragma: no cover - guarded by validate_steps
            raise ProbeError(f"{self.step_id}: {self.item!r} is not a probe item")

    @property
    def uses_persistent_source(self) -> bool:
        return uses_persistent_source(self.descriptor[0])

    @property
    def lane(self) -> str:
        return "persistent" if self.uses_persistent_source else "in_frame"

    def tag(self, save_id: str) -> str:
        return f"probe-{save_id}-{self.step_id}"


# -- the step list
#
# ORDERING IS EVIDENCE, not presentation. Two constraints set it:
#
#   * a unique item inserts once per save, so the two hypotheses that need a
#     unique insert (H2 idle, H3 sticky) cannot share a save. Hence two passes,
#     each on its own throwaway save;
#   * H2 wants a state with NO recent overflow, so in pass A the unique insert
#     comes BEFORE the deliberate cap overflow, not after. Running the overflow
#     first would confound H2 with H3 -- exactly the confound the sticky
#     hypothesis proposes.

PASS_A = "a"
PASS_B = "b"

PROBE_PASSES = {
    PASS_A: (
        "idle-first (throwaway save A): baseline return value, then the unique "
        "insert while nothing has overflowed, then the deliberate cap overflow, "
        "then the state cases."
    ),
    PASS_B: (
        "sticky-first (throwaway save B, a DIFFERENT save -- the unique item "
        "cannot insert twice): overflow a vial stack at cap and see where the "
        "very next adds go."
    ),
}

PROBE_STEPS: tuple[ProbeStep, ...] = (
    ProbeStep(
        step_id="a1-normal-add",
        hypothesis="H1",
        item="Pebble",
        quantity=1,
        pass_name=PASS_A,
        setup=(
            f"Hold BETWEEN 2 AND {PEBBLE_HELD_CAP - 2} Pebbles -- comfortably below the "
            f"held cap ({PEBBLE_HELD_CAP}). Stand at a lantern, in gameplay, nothing "
            "else happening. Do not open the storage box first."
        ),
        observe=(
            "Where did the Pebble go, and what is the held Pebble count now"
        ),
        rationale=(
            "The control row. A normal add that cannot overflow: this is the case "
            "clients#443 read as native_result=8, i.e. the FINAL HELD COUNT. Without "
            "it the overflow number below is a derived number with no base."
        ),
    ),
    ProbeStep(
        step_id="a2-unique-idle",
        hypothesis="H2",
        item="Saw Spear",
        quantity=1,
        pass_name=PASS_A,
        consumes_unique=True,
        setup=(
            "Still at the lantern, still idle, and NOTHING has overflowed this "
            "session (do not run a2 after a3). No boss killed since the last load. "
            "The save must never have received a Saw Spear."
        ),
        observe=(
            "Is the Saw Spear in held inventory, or in the storage box"
        ),
        rationale=(
            "oz's Cheat-Engine-era control, re-run on the native stack: the same "
            "Saw Spear, drip-delivered mid-normal-play, landed HELD. If it lands in "
            "storage here, the flood-order story in clients#445 loses its control "
            "and the destination is not about tempo at all."
        ),
    ),
    ProbeStep(
        step_id="a3-cap-overflow",
        hypothesis="H1",
        item="Pebble",
        quantity=1,
        pass_name=PASS_A,
        setup=(
            f"Fill Pebbles to EXACTLY the held cap ({PEBBLE_HELD_CAP}/{PEBBLE_HELD_CAP}). "
            "Buy from the Messengers if you need to. Still idle at the lantern. "
            "Check the storage box's Pebble count and write it down BEFORE this step."
        ),
        observe=(
            "Held Pebble count now, and the storage box's Pebble count now"
        ),
        rationale=(
            "The deliberate at-cap case. H1 predicts native_result=1 here while a "
            "normal add returns the final held count -- two live data points said so; "
            "this is the third, taken on purpose instead of found in a flood."
        ),
    ),
    ProbeStep(
        step_id="a4-post-boss",
        hypothesis="H4",
        item="Pebble",
        quantity=1,
        pass_name=PASS_A,
        setup=(
            "Empty the Pebble stack back down BELOW the cap first (throw some). Then "
            "kill a boss and return here WITHOUT reloading. Arm this step while the "
            "post-kill state is still current -- during the kill cutscene or the "
            "moments after it, before the lantern warp settles."
        ),
        observe=(
            "Where did the Pebble go, and what is the held Pebble count now"
        ),
        rationale=(
            "The release in oz's clear fired immediately after the BSB kill, so the "
            "flood crossed post-boss/cutscene/warp states. Same item and same "
            "sub-cap held count as a1: if the destination differs, the STATE is what "
            "differs, not the item or the cap."
        ),
    ),
    ProbeStep(
        step_id="a5-non-gameplay",
        hypothesis="H4",
        item="Pebble",
        quantity=1,
        pass_name=PASS_A,
        setup=(
            "Pebbles still below the cap. Now leave gameplay-idle: open the inventory "
            "menu (or stand in a load/warp) and stay there while this step runs."
        ),
        observe=(
            "Where did the Pebble go, and what is the held Pebble count now"
        ),
        rationale=(
            "Separates 'post-boss' from 'not gameplay-idle' inside H4. If a4 diverges "
            "and a5 does not, the boss state is the term; if both diverge, "
            "gameplay-idle is."
        ),
    ),
    ProbeStep(
        step_id="b1-vial-normal-add",
        hypothesis="H1",
        item="Blood Vial",
        quantity=1,
        pass_name=PASS_B,
        setup=(
            f"FRESH throwaway save B. Hold some Blood Vials but stay below the cap "
            f"({VIAL_HELD_CAP}) -- at least one, because absent-Vial insertion is "
            "refused outright (the live ?ItemInfo? reproduction). Idle at a lantern."
        ),
        observe=(
            "Where did the Vial go, and what is the held Vial count now"
        ),
        rationale=(
            "Pass B's own control row. The sticky verdict below is a comparison, and "
            "a comparison needs its base measured in the same save and the same "
            "session as the thing it is compared against."
        ),
    ),
    ProbeStep(
        step_id="b2-vial-overflow",
        hypothesis="H1",
        item="Blood Vial",
        quantity=1,
        pass_name=PASS_B,
        setup=(
            f"Fill Blood Vials to EXACTLY the cap ({VIAL_HELD_CAP}/{VIAL_HELD_CAP}). "
            "Write down the storage box's Vial count before this step. Stay idle. "
            "Do NOT do anything else in game between this step and b3."
        ),
        observe=(
            "Held Vial count now, and the storage box's Vial count now"
        ),
        rationale=(
            "The overflow that arms the sticky hypothesis, and independently a second "
            "witness for H1 on a different goods id than a3."
        ),
    ),
    ProbeStep(
        step_id="b3-unique-after-overflow",
        hypothesis="H3",
        item="Saw Spear",
        quantity=1,
        pass_name=PASS_B,
        consumes_unique=True,
        setup=(
            "IMMEDIATELY after b2, touching nothing in between. Save B must never "
            "have received a Saw Spear."
        ),
        observe=(
            "Is the Saw Spear in held inventory, or in the storage box"
        ),
        rationale=(
            "THE load-bearing step. A unique weapon has no held cap that could explain "
            "a storage placement, so if it lands in storage right after a vial "
            "overflow -- and landed HELD in a2 under the same lane and the same "
            "insert shape -- the routing is STICKY and the fix is pacing, not lane "
            "selection. If it lands held, sticky is refuted and clients#445 needs "
            "another term."
        ),
    ),
    ProbeStep(
        step_id="b4-reoverflow",
        hypothesis="H3",
        item="Blood Vial",
        quantity=1,
        pass_name=PASS_B,
        setup=(
            f"Refill Blood Vials to the cap again ({VIAL_HELD_CAP}/{VIAL_HELD_CAP}) and "
            "run this step to overflow a second time. Then, without touching anything, "
            "continue straight to b5."
        ),
        observe=(
            "Held Vial count now, and the storage box's Vial count now"
        ),
        rationale="Re-arms the sticky window for b5, and is a third H1 overflow witness.",
    ),
    ProbeStep(
        step_id="b5-goods-after-overflow",
        hypothesis="H3",
        item="Pebble",
        quantity=1,
        pass_name=PASS_B,
        setup=(
            "IMMEDIATELY after b4, touching nothing in between. Pebbles must be BELOW "
            f"their cap ({PEBBLE_HELD_CAP}) -- check the count first; a Pebble at cap "
            "here proves nothing."
        ),
        observe=(
            "Where did the Pebble go, and what is the held Pebble count now"
        ),
        rationale=(
            "Whether stickiness (if b3 shows it) is about unique items or about the "
            "add path as a whole. A sub-cap Pebble routed to storage says the whole "
            "path went sticky."
        ),
    ),
)


def steps_for(pass_name: str | None = None) -> tuple[ProbeStep, ...]:
    if pass_name is None:
        return PROBE_STEPS
    if pass_name not in PROBE_PASSES:
        raise ProbeError(f"unknown pass {pass_name!r}; known passes: {sorted(PROBE_PASSES)}")
    return tuple(step for step in PROBE_STEPS if step.pass_name == pass_name)


def validate_steps(steps=PROBE_STEPS) -> None:
    """Fail closed on a malformed step list, before anything attaches.

    Three properties, each of which has a way of going wrong quietly:
    every descriptor is one the real allowlist accepts (#146), no pass spends
    the once-per-save unique insert twice, and no two steps share an id (which
    would collide their journal tags and silently resume the wrong one).
    """
    seen: set[str] = set()
    uniques: dict[str, list[str]] = {}
    for step in steps:
        if step.step_id in seen:
            raise ProbeError(f"duplicate probe step id {step.step_id!r}")
        seen.add(step.step_id)
        if step.item not in PROBE_ITEMS:
            raise ProbeError(
                f"{step.step_id}: {step.item!r} is not one of the probe items "
                f"{sorted(PROBE_ITEMS)}. The probe has no escape hatch: add a live "
                "dump and an allowlist row first (issue #146)."
            )
        raw, normalized = step.descriptor
        try:
            describe_validated_descriptor(raw, normalized)
        except DescriptorError as exc:  # pragma: no cover - PROBE_ITEMS are all valid
            raise ProbeError(f"{step.step_id}: {exc}") from exc
        if step.consumes_unique:
            uniques.setdefault(step.pass_name, []).append(step.step_id)
    for pass_name, ids in uniques.items():
        if len(ids) > 1:
            raise ProbeError(
                f"pass {pass_name!r} spends the once-per-save unique insert more than "
                f"once ({', '.join(ids)}). A unique item inserts once per save; split "
                "the pass instead."
            )


# -- observation parsing

_OBSERVATION_WORDS = {
    "h": HELD, "held": HELD, "inventory": HELD, "1": HELD,
    "s": STORAGE, "storage": STORAGE, "box": STORAGE, "2": STORAGE,
    "b": SPLIT, "both": SPLIT, "split": SPLIT, "3": SPLIT,
    "?": UNKNOWN, "u": UNKNOWN, "unknown": UNKNOWN, "": UNKNOWN,
}


def parse_observation(text: str) -> str:
    """The operator's answer, normalized. Anything unrecognised is ``unknown``.

    Fail closed in the epistemic sense too: an answer the parser cannot read
    must not become a verdict. ``unknown`` propagates all the way to an
    ``unclear`` hypothesis rather than being guessed at.
    """
    return _OBSERVATION_WORDS.get(text.strip().lower(), UNKNOWN)


def parse_count(text: str) -> int | None:
    """An operator-typed count, or ``None`` for 'I did not look'."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return int(stripped, 10)
    except ValueError:
        return None


# -- one step's record


@dataclass
class DeliveryResult:
    """What the ordinary grant machinery reported for one probe grant."""

    status: str
    detail: str = ""
    native_result: int | None = None
    expected_before: int | None = None
    expected_after: int | None = None


@dataclass
class ProbeContext:
    """Everything a step needs that is not the step. Injectable, so the engine
    is host-testable end to end and only the live half is the operator's."""

    save_id: str
    read_stack: object  # (normalized_id) -> int | None
    deliver: object     # (step, expected_before) -> DeliveryResult
    prompt: object      # (question) -> str
    now: object         # () -> str
    emit: object = print
    journal: dict = field(default_factory=dict)


def run_step(step: ProbeStep, context: ProbeContext) -> dict:
    """Read back, deliver one grant, read back, ask. Returns the report record.

    The order is the evidence: the held count is sampled immediately before the
    grant so ``expected_before`` is the number the tool actually saw, and again
    immediately after so the record can say what moved without trusting the
    operator's arithmetic.
    """
    raw, normalized = step.descriptor
    held_before = context.read_stack(normalized)
    result = context.deliver(step, held_before)
    held_after = context.read_stack(normalized)

    observation = parse_observation(
        context.prompt(f"[{step.step_id}] {step.observe}? (held / storage / both / ?): ")
    )
    held_count = parse_count(
        context.prompt(f"[{step.step_id}] held count for {step.item} now (blank if not checked): ")
    )
    storage_count = parse_count(
        context.prompt(f"[{step.step_id}] storage-box count for {step.item} now (blank if not checked): ")
    )
    notes = context.prompt(f"[{step.step_id}] anything else worth recording (blank for none): ").strip()

    return {
        "format": "bb-storage-probe-v1",
        "recorded_at": context.now(),
        "save_id": context.save_id,
        "step_id": step.step_id,
        "hypothesis": step.hypothesis,
        "pass": step.pass_name,
        "item": step.item,
        "raw_id": f"{raw:#010x}",
        "normalized_id": f"{normalized:#010x}",
        "quantity": step.quantity,
        "lane": step.lane,
        "uses_persistent_source": step.uses_persistent_source,
        "consumes_unique": step.consumes_unique,
        "held_before": held_before,
        "held_after": held_after,
        "delivery_status": result.status,
        "delivery_detail": result.detail,
        "native_result": result.native_result,
        "expected_before": result.expected_before,
        "expected_after": result.expected_after,
        "observation": observation,
        "operator_held_count": held_count,
        "operator_storage_count": storage_count,
        "operator_notes": notes,
    }


def append_record(report_path: Path, record: dict) -> None:
    """Append-only JSON lines. The report is evidence; nothing rewrites it."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_records(report_path: Path) -> list[dict]:
    """Every record in a report, ignoring blank and unparseable lines."""
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return []
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


# -- classification
#
# Deliberately separated from everything that touches a process: given a list of
# recorded cells, these functions decide the verdict, and the tests drive them
# with recorded cells alone.


@dataclass(frozen=True)
class Verdict:
    hypothesis: str
    verdict: str
    reason: str
    witnesses: tuple[str, ...] = ()


def _by_step(records: list[dict]) -> dict[str, dict]:
    """Last record wins: a redone step supersedes its earlier attempt."""
    latest: dict[str, dict] = {}
    for record in records:
        step_id = record.get("step_id")
        if step_id:
            latest[step_id] = record
    return latest


def _landed(record: dict | None) -> str | None:
    return record.get("observation") if record else None


def classify_return_semantics(records: list[dict]) -> Verdict:
    """H1: final held count on a normal add, ``1`` on overflow-to-storage."""
    latest = _by_step(records)
    normal = [
        record for step_id, record in latest.items()
        if record.get("hypothesis") == "H1" and _landed(record) == HELD
    ]
    overflow = [
        record for step_id, record in latest.items()
        if record.get("hypothesis") == "H1" and _landed(record) == STORAGE
    ]
    if not normal or not overflow:
        missing = "a normal add landing held" if not normal else "an at-cap add landing in storage"
        return Verdict(
            "H1", UNCLEAR,
            f"no witness for {missing}; the hypothesis is a contrast between two cases "
            "and one of them was not recorded.",
            tuple(sorted(record["step_id"] for record in normal + overflow)),
        )
    witnesses = tuple(sorted(record["step_id"] for record in normal + overflow))
    bad_normal = [
        record["step_id"] for record in normal
        if record.get("native_result") != record.get("held_after")
        or record.get("held_after") is None
    ]
    bad_overflow = [
        record["step_id"] for record in overflow if record.get("native_result") != 1
    ]
    if bad_normal or bad_overflow:
        parts = []
        if bad_normal:
            parts.append(
                "normal adds whose result cell is not the final held count: "
                + ", ".join(sorted(bad_normal))
            )
        if bad_overflow:
            parts.append(
                "overflow adds whose result cell is not 1: " + ", ".join(sorted(bad_overflow))
            )
        return Verdict("H1", REFUTED, "; ".join(parts) + ".", witnesses)
    return Verdict(
        "H1", SUPPORTED,
        f"{len(normal)} normal add(s) returned the final held count and {len(overflow)} "
        "at-cap add(s) returned 1, with the storage destination observed in game.",
        witnesses,
    )


def classify_idle_unique(records: list[dict]) -> Verdict:
    """H2: a unique-item insert delivered idle in normal gameplay lands held."""
    latest = _by_step(records)
    record = latest.get("a2-unique-idle")
    if record is None:
        return Verdict("H2", UNCLEAR, "a2-unique-idle was not run.")
    landed = _landed(record)
    if landed == HELD:
        return Verdict(
            "H2", SUPPORTED,
            f"the unique insert landed held ({record['lane']} lane), reproducing oz's "
            "Cheat-Engine-era control on the native stack.",
            ("a2-unique-idle",),
        )
    if landed == STORAGE:
        return Verdict(
            "H2", REFUTED,
            "the unique insert landed in STORAGE even idle, with nothing overflowed "
            "and no boss killed. Order/tempo cannot be the term; the insert path "
            "itself places uniques in storage.",
            ("a2-unique-idle",),
        )
    return Verdict("H2", UNCLEAR, f"the observation was {landed!r}.", ("a2-unique-idle",))


def classify_sticky(records: list[dict]) -> Verdict:
    """H3: after an overflow at cap, the next add also goes to storage."""
    latest = _by_step(records)
    overflow = latest.get("b2-vial-overflow")
    unique = latest.get("b3-unique-after-overflow")
    idle_unique = latest.get("a2-unique-idle")
    if unique is None:
        return Verdict("H3", UNCLEAR, "b3-unique-after-overflow was not run.")
    if overflow is None or _landed(overflow) != STORAGE:
        return Verdict(
            "H3", UNCLEAR,
            "b3 ran without a witnessed overflow immediately before it "
            f"(b2 observation: {_landed(overflow)!r}), so the sticky window was never "
            "armed and b3's destination says nothing about stickiness.",
            ("b3-unique-after-overflow",),
        )
    landed = _landed(unique)
    followup = latest.get("b5-goods-after-overflow")
    scope = ""
    if followup is not None and _landed(followup) is not None:
        scope = (
            " A sub-cap Pebble delivered straight after a second overflow landed "
            f"{_landed(followup)}, so the effect is "
            + ("not specific to unique items." if _landed(followup) == STORAGE
               else "specific to the unique insert, not the add path as a whole.")
        )
    if landed == STORAGE:
        control = ""
        if _landed(idle_unique) == HELD:
            control = (
                " The same item on the same lane landed HELD when delivered idle "
                "(a2-unique-idle), so the difference is the preceding overflow, not "
                "the item."
            )
        elif idle_unique is not None:
            control = (
                " NOTE: the idle control (a2-unique-idle) did not land held "
                f"({_landed(idle_unique)!r}), so this is a single observation without "
                "its control and cannot separate sticky from always-storage."
            )
        return Verdict("H3", SUPPORTED,
                       "the unique insert went to storage immediately after a vial "
                       "overflow at cap." + control + scope,
                       ("b2-vial-overflow", "b3-unique-after-overflow"))
    if landed == HELD:
        return Verdict("H3", REFUTED,
                       "the unique insert landed HELD immediately after a witnessed "
                       "overflow at cap, so an overflow does not make the next add "
                       "sticky." + scope,
                       ("b2-vial-overflow", "b3-unique-after-overflow"))
    return Verdict("H3", UNCLEAR, f"the observation was {landed!r}.",
                   ("b3-unique-after-overflow",))


def classify_state(records: list[dict]) -> Verdict:
    """H4: the destination depends on the game state at delivery time."""
    latest = _by_step(records)
    baseline = latest.get("a1-normal-add")
    if baseline is None or _landed(baseline) != HELD:
        return Verdict(
            "H4", UNCLEAR,
            "the idle baseline a1-normal-add is missing or did not land held, so a "
            "state case has nothing to differ FROM.",
        )
    cases = {
        step_id: latest[step_id]
        for step_id in ("a4-post-boss", "a5-non-gameplay")
        if step_id in latest
    }
    if not cases:
        return Verdict("H4", UNCLEAR, "neither state case was run.", ("a1-normal-add",))
    diverged = sorted(step_id for step_id, record in cases.items() if _landed(record) == STORAGE)
    same = sorted(step_id for step_id, record in cases.items() if _landed(record) == HELD)
    witnesses = ("a1-normal-add",) + tuple(sorted(cases))
    if diverged:
        return Verdict(
            "H4", SUPPORTED,
            f"the same sub-cap Pebble add landed held idle but in storage in: "
            f"{', '.join(diverged)}. State is a term in the routing."
            + (f" It did NOT diverge in: {', '.join(same)}." if same else ""),
            witnesses,
        )
    if same and len(same) == len(cases):
        return Verdict(
            "H4", REFUTED,
            f"the same add landed held in every state case ({', '.join(same)}) as well "
            "as idle, so state alone does not route to storage.",
            witnesses,
        )
    return Verdict("H4", UNCLEAR, "at least one state case has no readable observation.",
                   witnesses)


def classify_lane(records: list[dict]) -> Verdict:
    """Whether the insert source lane separates held from storage at all.

    Not one of the four hypotheses; it is the term that would make this OUR bug
    rather than the game's, so it is reported alongside them. Its verdict is a
    correlation and is labelled as one.
    """
    latest = _by_step(records)
    lanes: dict[str, set[str]] = {}
    for record in latest.values():
        landed = _landed(record)
        if landed in (HELD, STORAGE):
            lanes.setdefault(record.get("lane", "?"), set()).add(landed)
    if not lanes:
        return Verdict("lane", UNCLEAR, "no step produced a readable destination.")
    mixed = sorted(lane for lane, seen in lanes.items() if len(seen) > 1)
    if mixed:
        return Verdict(
            "lane", REFUTED,
            f"lane(s) {', '.join(mixed)} produced BOTH destinations, so the source "
            "lane cannot be what decides where an item lands.",
            tuple(sorted(latest)),
        )
    if len(lanes) < 2:
        lane, seen = next(iter(lanes.items()))
        return Verdict(
            "lane", UNCLEAR,
            f"only the {lane} lane produced readable destinations ({', '.join(sorted(seen))}); "
            "one lane cannot separate anything.",
            tuple(sorted(latest)),
        )
    mapping = ", ".join(f"{lane}->{next(iter(seen))}" for lane, seen in sorted(lanes.items()))
    return Verdict(
        "lane", SUPPORTED,
        f"each lane produced exactly one destination ({mapping}). CORRELATION ONLY: "
        "every lane also differs in item and in step order, so this is a lead to "
        "test by delivering the same item on both lanes, not a cause.",
        tuple(sorted(latest)),
    )


CLASSIFIERS = (
    classify_return_semantics,
    classify_idle_unique,
    classify_sticky,
    classify_state,
    classify_lane,
)

HYPOTHESIS_TITLES = {
    "H1": "return-value semantics (final held count vs 1 on overflow)",
    "H2": "a unique-item insert delivered idle lands held",
    "H3": "STICKY: an overflow routes the NEXT add to storage too",
    "H4": "state dependence (post-boss / not gameplay-idle)",
    "lane": "does the insert source lane separate the outcomes",
}


def summarize(records: list[dict]) -> list[Verdict]:
    return [classifier(records) for classifier in CLASSIFIERS]


def render_summary(records: list[dict], *, save_ids: tuple[str, ...] = ()) -> str:
    """The markdown block the operator pastes into clients#445."""
    latest = _by_step(records)
    lines = [
        "## Storage-routing probe results (clients#445)",
        "",
        f"`tools/bb_native_delivery probe-storage`, {len(latest)} step(s) recorded"
        + (f" across save(s) {', '.join(save_ids)}" if save_ids else "")
        + ".",
        "",
        "| step | H | item | lane | held before/after | native_result | landed | held/storage counts |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for step_id in sorted(latest):
        record = latest[step_id]
        lines.append(
            "| {step} | {hypothesis} | {item} | {lane} | {before}/{after} | {result} | "
            "{landed} | {held}/{storage} |".format(
                step=step_id,
                hypothesis=record.get("hypothesis", "?"),
                item=record.get("item", "?"),
                lane=record.get("lane", "?"),
                before=record.get("held_before"),
                after=record.get("held_after"),
                result=record.get("native_result"),
                landed=record.get("observation", UNKNOWN),
                held=record.get("operator_held_count"),
                storage=record.get("operator_storage_count"),
            )
        )
    lines += ["", "### Verdicts", ""]
    for verdict in summarize(records):
        title = HYPOTHESIS_TITLES.get(verdict.hypothesis, verdict.hypothesis)
        lines.append(f"- **{verdict.hypothesis} {verdict.verdict.upper()}** — {title}.")
        lines.append(f"  {verdict.reason}")
        if verdict.witnesses:
            lines.append(f"  Witnesses: {', '.join(verdict.witnesses)}")
    lines += [
        "",
        "Every `unclear` above is a step that was skipped or an observation the tool "
        "could not read — not a weak result. Re-run those steps before treating the "
        "picture as settled.",
        "",
        "Recorded by a developer tool on a throwaway save; one emulator build "
        "(shadPS4, CUSA03173 01.09). Nothing here changes the guarded contract JSON.",
    ]
    return "\n".join(lines)


# -- resume


def pending_steps(steps, journal: dict, save_id: str) -> tuple[list[ProbeStep], list[ProbeStep]]:
    """Split ``steps`` into (to run, already done) against the grant journal.

    Resume reuses the #147 journal rather than keeping a second store: probe
    grants are grants, they take journal tags like every other grant, and a step
    whose tag already carries a terminal probe status is one the operator has
    already answered. That also means the reused-tag refusal in the CLI covers
    probe steps for free -- rerunning a landed step without ``--expected-before``
    is refused by the same gate that refuses it for ``grant``.
    """
    todo, done = [], []
    for step in steps:
        entry = journal.get(step.tag(save_id))
        status = entry.get("probe_status") if isinstance(entry, dict) else None
        (done if status in TERMINAL_PROBE_STATUS else todo).append(step)
    return todo, done


def runbook(steps=PROBE_STEPS) -> str:
    """The operator runbook, generated from the steps so it cannot drift."""
    lines = [
        "STORAGE-ROUTING PROBE — operator runbook (clients#445)",
        "",
        "Run on a THROWAWAY save. A unique item can be inserted only once per save,",
        "so the session is split into two passes on two different throwaway saves.",
        "",
    ]
    for pass_name, description in sorted(PROBE_PASSES.items()):
        selected = [step for step in steps if step.pass_name == pass_name]
        if not selected:
            # A filtered run (one pass, --only, a resume) must not print an empty
            # heading that reads as "this pass has nothing to do".
            continue
        lines += [f"PASS {pass_name.upper()} — {description}", ""]
        for step in selected:
            lines += [
                f"  [{step.step_id}]  {step.hypothesis}  {step.item} x{step.quantity}  "
                f"({step.lane} lane)"
                + ("  ** spends the once-per-save unique insert **" if step.consumes_unique else ""),
                f"     BEFORE: {step.setup}",
                f"     AFTER:  {step.observe}?",
                f"     WHY:    {step.rationale}",
                "",
            ]
    lines += [
        "Finally: `probe-storage --summary` and paste the rendered block into clients#445.",
    ]
    return "\n".join(lines)
