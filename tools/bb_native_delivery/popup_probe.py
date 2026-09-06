"""The native-item-popup probe (issue #330, docs/NATIVE-ITEM-POPUPS.md).

What it is for
--------------
Nobody has recorded whether a received AP item ever makes Bloodborne show its
own lower-corner pickup popup. Two lanes exist: the native ``ItemGrant``
descriptor lane (writes the inventory record directly, no known presentation
hook) and the event-award lane used for category-8 runes/gems (a token good
consumed by a ``Restart`` event that calls ``AwardItemLot`` -- the same call
vanilla pickups use). This module is the guided operator session that answers
it, mirroring :mod:`tools.bb_native_delivery.probe` (the storage-routing
probe) rather than inventing a second engine shape.

Positive control first: step 0 is a vanilla pickup with a *known* result
(popup). If the control fails, the session is a probe defect, not a data
point (docs/CONTRIBUTING-LIVE-PROBES.md, rule 1). Every step after it is a
pre-registered prediction: docs/NATIVE-ITEM-POPUPS.md states, for each
hypothesis, what true / false / probe-broken look like and how they are told
apart.

What this module does NOT do
-----------------------------
It arms no new descriptor and no new RVA. The ``itemgrant`` step reuses the
ordinary :class:`~.delivery.GrantSession` (via the CLI's ``_probe_deliver``),
and the ``event_award`` steps deliver the same category-8 token good the
client already grants; ``AwardItemLot`` runs inside the game's own Restart
event, never a direct call from the cave.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .descriptor import DescriptorError, describe_validated_descriptor, goods_descriptor_ids
from .probe import PROBE_ITEMS, append_record, read_records  # re-exported, not reimplemented

# -- the Communion token descriptor, derived statically
#
# worlds/bloodborne/category8_awards.py's first pilot row is the Communion
# rune (rune id 102901): token_goods_id=9800. worlds/bloodborne/
# runtime_bindings.py binds every category-8 token through the same category-4
# goods formula every other goods canary uses (raw=0xB0000000|id,
# normalized=0x40000000|id) -- see ITEM_BINDINGS.update(...) there. So the
# descriptor is derivable without a live dump or an operator-supplied flag.
COMMUNION_TOKEN_GOODS_ID = 9_800
COMMUNION_RAW, COMMUNION_NORMALIZED = goods_descriptor_ids(COMMUNION_TOKEN_GOODS_ID)

POPUP_ITEMS: dict[str, tuple[int, int]] = dict(PROBE_ITEMS)
POPUP_ITEMS["Communion"] = (COMMUNION_RAW, COMMUNION_NORMALIZED)

LANE_VANILLA = "vanilla"
LANE_ITEMGRANT = "itemgrant"
LANE_EVENT_AWARD = "event_award"
LANES = (LANE_VANILLA, LANE_ITEMGRANT, LANE_EVENT_AWARD)

# -- observation vocabulary
POPUP = "popup"
MODAL = "modal"
NONE_OBS = "none"
DEFERRED = "deferred"
UNKNOWN = "unknown"
POPUP_OBSERVATIONS = (POPUP, MODAL, NONE_OBS, DEFERRED, UNKNOWN)

SUPPORTED = "supported"
REFUTED = "refuted"
UNCLEAR = "unclear"
PROBE_DEFECT = "probe_defect"

TERMINAL_PROBE_STATUS = frozenset({"recorded", "skipped"})


class PopupProbeError(Exception):
    """A popup-probe step is malformed, or the session cannot honestly continue."""


_OBSERVATION_WORDS = {
    "p": POPUP, "popup": POPUP, "1": POPUP,
    "m": MODAL, "modal": MODAL, "2": MODAL,
    "n": NONE_OBS, "none": NONE_OBS, "nothing": NONE_OBS, "3": NONE_OBS,
    "d": DEFERRED, "deferred": DEFERRED, "4": DEFERRED,
    "?": UNKNOWN, "u": UNKNOWN, "unknown": UNKNOWN, "": UNKNOWN,
}


def parse_observation(text: str) -> str:
    """The operator's answer, normalized. Anything unrecognised is ``unknown``."""
    return _OBSERVATION_WORDS.get(text.strip().lower(), UNKNOWN)


_YES_NO_WORDS = {"y": "y", "yes": "y", "n": "n", "no": "n"}


def parse_yes_no(text: str) -> str:
    """``y`` / ``n`` / ``unknown`` -- the persistence and nonblocking questions."""
    return _YES_NO_WORDS.get(text.strip().lower(), UNKNOWN)


@dataclass(frozen=True)
class PopupStep:
    """One question, one lane, at most one grant, one popup observation."""

    step_id: str
    hypothesis: str
    lane: str
    item: str
    quantity: int
    #: What the operator must do IN GAME before (and, for the control, instead
    #: of) any grant.
    setup: str
    #: What to look at afterwards, in the words the prompt will use.
    observe: str
    #: The pre-registered prediction if the hypothesis under test is TRUE.
    expected: str
    #: Why this step exists, for the report and the runbook.
    rationale: str
    #: An extra yes/no question this step asks beyond the popup observation
    #: (``nonblocking`` for the menu-open step, ``persisted`` for the reload
    #: step), or ``None`` for steps that ask only the popup question.
    extra_question: str | None = None
    extra_key: str | None = None

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise PopupProbeError(f"{self.step_id}: {self.lane!r} is not one of {LANES}")
        if self.quantity > 0 and self.item not in POPUP_ITEMS:
            raise PopupProbeError(
                f"{self.step_id}: {self.item!r} is not a popup-probe item "
                f"{sorted(POPUP_ITEMS)}"
            )
        if (self.extra_question is None) != (self.extra_key is None):
            raise PopupProbeError(
                f"{self.step_id}: extra_question and extra_key must both be set or both absent"
            )

    @property
    def descriptor(self) -> tuple[int, int]:
        try:
            return POPUP_ITEMS[self.item]
        except KeyError:  # pragma: no cover - guarded by __post_init__
            raise PopupProbeError(f"{self.step_id}: {self.item!r} is not a popup-probe item")

    def tag(self, save_id: str) -> str:
        return f"popup-probe-{save_id}-{self.step_id}"


POPUP_STEPS: tuple[PopupStep, ...] = (
    PopupStep(
        step_id="control-vanilla-pickup",
        hypothesis="control",
        lane=LANE_VANILLA,
        item="(no delivery)",
        quantity=0,
        setup=(
            "No delivery this step. In game, walk up to any physical item lot you "
            "can reach (a glowing pickup, a chest, a corpse) and pick it up -- any "
            "item is fine, it does not have to be one of the probe's own items. "
            "Type `mark control-vanilla-pickup` in the CLIENT console the moment before you pick it up."
        ),
        observe="Did the game show its own lower-corner pickup popup for it",
        expected=POPUP,
        rationale=(
            "The positive control (CONTRIBUTING-LIVE-PROBES.md rule 1): a vanilla "
            "pickup ALWAYS produces this popup. If this step's observation is not "
            "`popup`, the instrument -- or the operator's reading of the screen -- is "
            "broken, and nothing downstream in this session is evidence of anything."
        ),
    ),
    PopupStep(
        step_id="itemgrant-pebble",
        hypothesis="itemgrant_presents_popup",
        lane=LANE_ITEMGRANT,
        item="Pebble",
        quantity=1,
        setup=(
            "Idle at a lantern, nothing else happening. This step delivers 1 Pebble "
            "through the ordinary native ItemGrant lane (the same descriptor lane "
            "goods/weapons/attire grants use) -- watch the corner of the screen the "
            "whole time the grant is in flight."
        ),
        observe="Did a pickup popup appear for the delivered Pebble",
        expected=NONE_OBS,
        rationale=(
            "Pre-registered prediction: the ItemGrant lane writes the inventory "
            "record directly and never calls the game's own acquisition path, so it "
            "should present nothing. This is the prediction under test, not a known "
            "fact -- see docs/NATIVE-ITEM-POPUPS.md."
        ),
    ),
    PopupStep(
        step_id="award-rune-token",
        hypothesis="award_presents_popup",
        lane=LANE_EVENT_AWARD,
        item="Communion",
        quantity=1,
        setup=(
            "Idle at a lantern. This step delivers the category-8 token good for "
            "Communion (rune 102901); the client's Restart event in common.emevd "
            "will consume it and call AwardItemLot, the same call vanilla pickups "
            "use. Watch the corner of the screen; type `mark award-rune-token` the "
            "moment you deliver it."
        ),
        observe="Did a pickup popup appear for Communion",
        expected=POPUP,
        rationale=(
            "The load-bearing step. AwardItemLot is what presents a vanilla pickup, "
            "so if the event-award lane also calls it for a received AP item, the "
            "game should present it the same way -- the mechanism, not a new "
            "presentation routine."
        ),
        extra_question="Did input stay free the whole time (y/n)",
        extra_key="nonblocking",
    ),
    PopupStep(
        step_id="award-while-menu-open",
        hypothesis="award_nonblocking",
        lane=LANE_EVENT_AWARD,
        item="Communion",
        quantity=1,
        setup=(
            "Same save as award-rune-token: issue #330 expects a second Communion "
            "to coexist with the first under a distinct handle, so do NOT reset the "
            "save. Open and hold the inventory menu open, then deliver the "
            "Communion token while the menu is open."
        ),
        observe=(
            "Did the popup appear WHILE the menu was open, only AFTER you closed it "
            "(deferred), or not at all"
        ),
        expected=DEFERRED,
        rationale=(
            "docs/TOASTS.md's non-blocking requirement, tested directly: a popup "
            "during a menu is fine, a popup that waits until the menu closes is "
            "`deferred` and still acceptable, and a modal that captures input while "
            "the menu is open is a permanent refusal for this lane."
        ),
        extra_question="Did input stay free the whole time (y/n)",
        extra_key="nonblocking",
    ),
    PopupStep(
        step_id="award-after-reload",
        hypothesis="award_persists",
        lane=LANE_EVENT_AWARD,
        item="(no delivery)",
        quantity=0,
        setup=(
            "No delivery this step. Save, then FULLY RESTART shadPS4 (not just "
            "reload the save-in-process), and load back in."
        ),
        observe=(
            "Did any pickup popup replay on load for the earlier awards (it should "
            "not; a popup on a load screen is a refusal per the spec)"
        ),
        expected=NONE_OBS,
        rationale=(
            "Mirrors TOASTS.md verdict 3 (reloading still reads the real state, not "
            "a stale cache) for the award lane: a popup that vanishes on reload would "
            "mean the presentation is cosmetic and the underlying AwardItemLot never "
            "stuck. The popup question guards the load-screen refusal condition."
        ),
        extra_question="Is the rune still present after the reload (y/n)",
        extra_key="persisted",
    ),
)


def steps_for(step_ids=None) -> tuple[PopupStep, ...]:
    if step_ids is None:
        return POPUP_STEPS
    wanted = set(step_ids)
    return tuple(step for step in POPUP_STEPS if step.step_id in wanted)


def validate_steps(steps=POPUP_STEPS) -> None:
    """Fail closed on a malformed step list, before anything attaches."""
    seen: set[str] = set()
    for step in steps:
        if step.step_id in seen:
            raise PopupProbeError(f"duplicate popup-probe step id {step.step_id!r}")
        seen.add(step.step_id)
        if step.quantity > 0:
            raw, normalized = step.descriptor
            try:
                describe_validated_descriptor(raw, normalized)
            except DescriptorError as exc:
                raise PopupProbeError(f"{step.step_id}: {exc}") from exc


# -- one step's record


@dataclass
class DeliveryResult:
    """What the ordinary grant machinery reported for one popup-probe grant."""

    status: str = "not_delivered"
    detail: str = ""
    native_result: int | None = None


@dataclass
class PopupProbeContext:
    """Everything a step needs that is not the step. Injectable, so the engine
    is host-testable end to end and only the live half is the operator's."""

    save_id: str
    deliver: object  # (step) -> DeliveryResult, or None for a no-delivery step
    prompt: object    # (question) -> str
    now: object       # () -> str
    emit: object = print
    journal: dict = field(default_factory=dict)


def run_step(step: PopupStep, context: PopupProbeContext) -> dict:
    """Deliver (if any), ask the popup question, ask any extra question."""
    result = context.deliver(step) if step.quantity > 0 else DeliveryResult()

    observation = parse_observation(
        context.prompt(f"[{step.step_id}] {step.observe}? (popup / modal / none / deferred / ?): ")
    )
    extra_value = None
    if step.extra_question is not None:
        extra_value = parse_yes_no(context.prompt(f"[{step.step_id}] {step.extra_question}? "))
    notes = context.prompt(f"[{step.step_id}] anything else worth recording (blank for none): ").strip()

    record = {
        "format": "bb-popup-probe-v1",
        "recorded_at": context.now(),
        "save_id": context.save_id,
        "step_id": step.step_id,
        "hypothesis": step.hypothesis,
        "lane": step.lane,
        "item": step.item,
        "quantity": step.quantity,
        "delivery_status": result.status,
        "delivery_detail": result.detail,
        "native_result": result.native_result,
        "observation": observation,
        "operator_notes": notes,
    }
    if step.extra_key is not None:
        record[step.extra_key] = extra_value
    return record


# -- classification


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


def classify_control(records: list[dict]) -> Verdict:
    """Positive control: a vanilla pickup must show a popup."""
    latest = _by_step(records)
    record = latest.get("control-vanilla-pickup")
    if record is None:
        return Verdict("control", UNCLEAR, "control-vanilla-pickup was not run.")
    if record.get("observation") == POPUP:
        return Verdict(
            "control", SUPPORTED,
            "the vanilla pickup showed its own popup, as expected. Downstream steps "
            "in this session are readable.",
            ("control-vanilla-pickup",),
        )
    return Verdict(
        "control", PROBE_DEFECT,
        f"the vanilla positive control observed {record.get('observation')!r}, not "
        "`popup`. Per CONTRIBUTING-LIVE-PROBES.md rule 1, this is a probe defect, "
        "not a data point -- nothing downstream in this session is evidence of "
        "anything until the control passes.",
        ("control-vanilla-pickup",),
    )


def classify_itemgrant(records: list[dict]) -> Verdict:
    """H: itemgrant_presents_popup -- does the ItemGrant lane show a popup."""
    latest = _by_step(records)
    record = latest.get("itemgrant-pebble")
    if record is None:
        return Verdict("itemgrant_presents_popup", UNCLEAR, "itemgrant-pebble was not run.")
    observation = record.get("observation")
    if observation == POPUP:
        return Verdict(
            "itemgrant_presents_popup", SUPPORTED,
            "the ItemGrant lane showed a popup for a delivered Pebble, contrary to "
            "the pre-registered prediction that it presents nothing.",
            ("itemgrant-pebble",),
        )
    if observation in (NONE_OBS, DEFERRED):
        return Verdict(
            "itemgrant_presents_popup", REFUTED,
            f"the ItemGrant lane observation was {observation!r}, matching the "
            "pre-registered prediction that this lane presents nothing (it bypasses "
            "the game's own acquisition path).",
            ("itemgrant-pebble",),
        )
    if observation == MODAL:
        return Verdict(
            "itemgrant_presents_popup", REFUTED,
            "the ItemGrant lane produced a MODAL dialog. Per "
            "docs/NATIVE-ITEM-POPUPS.md this permanently closes the lane for native "
            "popups; it does not support the popup-presents hypothesis.",
            ("itemgrant-pebble",),
        )
    return Verdict("itemgrant_presents_popup", UNCLEAR,
                    f"the observation was {observation!r}.", ("itemgrant-pebble",))


def classify_award_presents(records: list[dict]) -> Verdict:
    """H: award_presents_popup -- does the event-award lane show a popup."""
    latest = _by_step(records)
    record = latest.get("award-rune-token")
    if record is None:
        return Verdict("award_presents_popup", UNCLEAR, "award-rune-token was not run.")
    observation = record.get("observation")
    if observation == POPUP:
        return Verdict(
            "award_presents_popup", SUPPORTED,
            "the event-award lane's AwardItemLot call presented Communion with the "
            "game's own popup, matching the pre-registered prediction.",
            ("award-rune-token",),
        )
    if observation == MODAL:
        return Verdict(
            "award_presents_popup", REFUTED,
            "the event-award lane produced a MODAL dialog. This permanently closes "
            "the lane per docs/NATIVE-ITEM-POPUPS.md's refusal conditions.",
            ("award-rune-token",),
        )
    if observation in (NONE_OBS, DEFERRED):
        return Verdict(
            "award_presents_popup", REFUTED,
            f"the event-award lane observation was {observation!r}, not `popup`. "
            "The mechanism prediction (AwardItemLot presents what it awards) does "
            "not hold for this delivery shape.",
            ("award-rune-token",),
        )
    return Verdict("award_presents_popup", UNCLEAR,
                    f"the observation was {observation!r}.", ("award-rune-token",))


def classify_award_nonblocking(records: list[dict]) -> Verdict:
    """H: award_nonblocking -- the popup never captures input, even mid-menu."""
    latest = _by_step(records)
    record = latest.get("award-while-menu-open")
    if record is None:
        return Verdict("award_nonblocking", UNCLEAR, "award-while-menu-open was not run.")
    observation = record.get("observation")
    nonblocking = record.get("nonblocking")
    if observation == MODAL or nonblocking == "n":
        return Verdict(
            "award_nonblocking", REFUTED,
            "input was captured (or a modal appeared) while the inventory menu was "
            "open. Per docs/TOASTS.md a modal notification is never acceptable; this "
            "permanently closes the lane.",
            ("award-while-menu-open",),
        )
    if observation in (POPUP, DEFERRED) and nonblocking == "y":
        return Verdict(
            "award_nonblocking", SUPPORTED,
            f"the popup appeared {observation} and input stayed free the whole time.",
            ("award-while-menu-open",),
        )
    return Verdict("award_nonblocking", UNCLEAR,
                    f"observation={observation!r}, nonblocking={nonblocking!r}.",
                    ("award-while-menu-open",))


def classify_award_persists(records: list[dict]) -> Verdict:
    """H: award_persists -- the awarded rune survives a full restart+reload."""
    latest = _by_step(records)
    record = latest.get("award-after-reload")
    if record is None:
        return Verdict("award_persists", UNCLEAR, "award-after-reload was not run.")
    persisted = record.get("persisted")
    if persisted == "y":
        return Verdict(
            "award_persists", SUPPORTED,
            "Communion was still present after a full shadPS4 restart and reload.",
            ("award-after-reload",),
        )
    if persisted == "n":
        return Verdict(
            "award_persists", REFUTED,
            "Communion was NOT present after a full restart and reload -- the award "
            "did not persist and the earlier popup (if any) was cosmetic.",
            ("award-after-reload",),
        )
    return Verdict("award_persists", UNCLEAR, f"the answer was {persisted!r}.",
                    ("award-after-reload",))


CLASSIFIERS = (
    classify_control,
    classify_itemgrant,
    classify_award_presents,
    classify_award_nonblocking,
    classify_award_persists,
)

HYPOTHESIS_TITLES = {
    "control": "positive control: a vanilla pickup shows a popup",
    "itemgrant_presents_popup": "the ItemGrant lane presents a native popup",
    "award_presents_popup": "the event-award lane presents a native popup",
    "award_nonblocking": "the award-lane popup never captures input",
    "award_persists": "the awarded item survives a full restart+reload",
}


def summarize(records: list[dict]) -> list[Verdict]:
    return [classifier(records) for classifier in CLASSIFIERS]


def render_summary(records: list[dict], *, save_ids: tuple[str, ...] = (),
                    marks: list[dict] | None = None) -> str:
    """The markdown block the operator pastes into issue #330."""
    latest = _by_step(records)
    lines = [
        "## Native-item-popup probe results (issue #330)",
        "",
        f"`tools/bb_native_delivery probe-popup`, {len(latest)} step(s) recorded"
        + (f" across save(s) {', '.join(save_ids)}" if save_ids else "")
        + ".",
        "",
        "| step | hypothesis | lane | item | observation | notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for step_id in sorted(latest):
        record = latest[step_id]
        lines.append(
            "| {step} | {hyp} | {lane} | {item} | {obs} | {notes} |".format(
                step=step_id,
                hyp=record.get("hypothesis", "?"),
                lane=record.get("lane", "?"),
                item=record.get("item", "?"),
                obs=record.get("observation", UNKNOWN),
                notes=record.get("operator_notes", ""),
            )
        )
    lines += ["", "### Verdicts", ""]
    control_defect = False
    for verdict in summarize(records):
        title = HYPOTHESIS_TITLES.get(verdict.hypothesis, verdict.hypothesis)
        lines.append(f"- **{verdict.hypothesis} {verdict.verdict.upper()}** — {title}.")
        lines.append(f"  {verdict.reason}")
        if verdict.witnesses:
            lines.append(f"  Witnesses: {', '.join(verdict.witnesses)}")
        if verdict.verdict == PROBE_DEFECT:
            control_defect = True
    if marks:
        lines += ["", "### Console marks", ""]
        for mark in sorted(marks, key=lambda m: m.get("at", "")):
            lines.append(f"- `{mark.get('at', '?')}` mark {mark.get('label', '?')!r}")
    lines += [
        "",
        "Every `unclear` above is a step that was skipped or an observation the tool "
        "could not read -- not a weak result. A `probe_defect` control means nothing "
        "downstream in the affected session is evidence of anything; re-run the "
        "session." if not control_defect else
        "The positive control FAILED (probe_defect) -- every other verdict above is "
        "not evidence of anything and must be re-run in a session where the control "
        "passes.",
        "",
        "Recorded by a developer tool on a throwaway save; one emulator build "
        "(shadPS4, CUSA03173 01.09). See docs/NATIVE-ITEM-POPUPS.md.",
    ]
    return "\n".join(lines)


# -- resume


def pending_steps(steps, journal: dict, save_id: str) -> tuple[list[PopupStep], list[PopupStep]]:
    """Split ``steps`` into (to run, already done) against the grant journal."""
    todo, done = [], []
    for step in steps:
        entry = journal.get(step.tag(save_id))
        status = entry.get("probe_status") if isinstance(entry, dict) else None
        (done if status in TERMINAL_PROBE_STATUS else todo).append(step)
    return todo, done


def runbook(steps=POPUP_STEPS) -> str:
    """The operator runbook, generated from the steps so it cannot drift."""
    lines = [
        "NATIVE-ITEM-POPUP PROBE — operator runbook (issue #330)",
        "",
        "Run step 0 (the positive control) FIRST. If it does not observe `popup`, "
        "stop: the session is a probe defect, not a data point.",
        "",
        "Before each step, type `mark <step_id>` in the CLIENT console (not this "
        "CLI) at the moment named in BEFORE, so the mark lands in "
        "bb-probe-marks.jsonl beside the step's own record.",
        "",
    ]
    for step in steps:
        lines += [
            f"  [{step.step_id}]  {step.hypothesis}  {step.lane} lane"
            + (f"  {step.item} x{step.quantity}" if step.quantity else "  (no delivery)"),
            f"     CONSOLE MARK: mark {step.step_id}",
            f"     BEFORE: {step.setup}",
            f"     AFTER:  {step.observe}?"
            + (f"  Also: {step.extra_question}?" if step.extra_question else ""),
            f"     EXPECTED IF TRUE: {step.expected}",
            f"     WHY:    {step.rationale}",
            "",
        ]
    lines += [
        "Finally: `probe-popup --summary` and paste the rendered block into issue #330.",
    ]
    return "\n".join(lines)
