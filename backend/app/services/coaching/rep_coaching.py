"""Rep coaching engine: per-step rates, one weekly focus, progress, conversion. No I/O."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from app.services.playbooks.outcome_steps import MEETING_BOOKED, status_from_rep_outcome
from app.services.playbooks.step_identity import StepMatcher

_MADRID = ZoneInfo("Europe/Madrid")

_STATE = {"met": "done", "missed": "missing", "unknown": "no_evidence", "not_applicable": "not_reached"}
STATES = frozenset(_STATE.values()) | {"improvable"}
DONE_STATES = frozenset({"done", "improvable"})
_NOT_A_CONVERSATION = frozenset({"voicemail", "no_response"})
# Call types (C04 v8 `call.call_type`) whose conversation is meant to go through every step.
FULL_PROCESS_CALLS = frozenset({"cold_first_contact", "discovery_meeting", "other"})
MIN_CONVERSATION_SECONDS = 30

FOCUS_MIN_APPLICABLE = 3
FOCUS_MIN_MISSING = 2
ACHIEVED_RATE = 0.8
CONVERSION_MIN_SAMPLE = {"sdr": 30, "ae": 8}
CONVERSION_MIN_GROUP = 5
PEER_MIN_PEOPLE = 3
PEER_MIN_CONVERSATIONS = 30
SUMMARY_MAX_CHARS = 160


def parse_instant(value) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        text = f"{text[:-1]}+00:00" if text.endswith("Z") else text
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def madrid_day(value) -> date | None:
    instant = parse_instant(value)
    return instant.astimezone(_MADRID).date() if instant else None


def _first_plain_line(summary: str) -> str:
    for raw in summary.splitlines():
        text = raw.strip().lstrip("#").strip().lstrip("-*•").strip()
        if text and not raw.strip().startswith("#"):
            return text
    return ""


def _duration(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _outcome_line(intel: dict) -> str:
    nxt = intel.get("next") if isinstance(intel.get("next"), dict) else {}
    outcome = nxt.get("outcome") if isinstance(nxt.get("outcome"), dict) else {}
    return " ".join(str(outcome.get("text") or "").split())


def _intelligence(memo: dict) -> dict:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    intel = memo.get("intelligence") or extraction.get("intelligence")
    return intel if isinstance(intel, dict) else {}


def is_conversation(memo: dict) -> bool:
    """THE conversation, for the rep and the Head of Sales alike: not a voicemail or a no-answer,
    at least 30 s when the length is known, and someone talked (the call reading can tell a line
    that connected to a switchboard or silence). Anything else is activity, never evaluated."""
    if memo.get("screening_outcome") in _NOT_A_CONVERSATION:
        return False
    duration = _duration(memo.get("audio_duration"))
    if duration is not None and duration < MIN_CONVERSATION_SECONDS:
        return False
    call = _intelligence(memo).get("call")
    return not (isinstance(call, dict) and call.get("reached_conversation") is False)


def interaction_row(memo: dict) -> dict | None:
    """One interaction as coaching sees it, or None when it carries no step observations."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    intel = _intelligence(memo)
    observations = intel.get("playbook_observations")
    if not isinstance(observations, list) or not observations:
        return None
    observed = parse_instant(memo.get("capture_started_at")) or parse_instant(memo.get("created_at"))
    if observed is None:
        return None
    duration = _duration(memo.get("audio_duration"))
    conversation = is_conversation(memo)
    call = intel.get("call") if isinstance(intel.get("call"), dict) else {}
    rep_outcome = memo.get("rep_outcome")
    steps: list[dict] = []
    seen_steps: set[str] = set()
    for item in observations:
        if not isinstance(item, dict) or not item.get("step_id"):
            continue
        step_id = str(item.get("step_id"))
        if step_id in seen_steps:  # a step is observed once per interaction: keep the first
            continue
        seen_steps.add(step_id)
        status = item.get("status")
        if item.get("judged_by") == "rep_outcome" and status == "unknown":
            status = status_from_rep_outcome(str(item.get("outcome") or ""), rep_outcome)
        state = _STATE.get(status, "no_evidence")
        if state == "done" and item.get("quality") == "improvable":
            state = "improvable"  # done, and the advice says how to do it better
        steps.append({
            "step_id": step_id,
            "label": str(item.get("label") or step_id),
            # What the step asked when this call was judged: a changed criterion stops counting.
            "criterion": item.get("criterion") or None,
            "state": state,
            "quote": item.get("quote") or None,
            "advice": item.get("advice") or None,
        })
    return {
        "memo_id": str(memo.get("id") or ""),
        "user_id": str(memo.get("user_id") or ""),
        "observed_at": observed.isoformat(),
        "motion": memo.get("sales_motion_key"),
        "is_conversation": conversation,
        # v8 call type: only a call that runs the whole process can complete it.
        "full_process": call.get("call_type") in FULL_PROCESS_CALLS if call else True,
        # Booked is what the rep declared after the call, never read into the transcript.
        "meeting_agreed": rep_outcome == MEETING_BOOKED,
        "duration_s": duration,
        # v8 says how the call ended, with who said what worked out; older calls keep the note's line.
        "summary_line": (_outcome_line(intel) or _first_plain_line(str(extraction.get("summary") or "")))[:SUMMARY_MAX_CHARS],
        "steps": steps,
    }


def _rate(done: int, applicable: int) -> float | None:
    return round(done / applicable, 4) if applicable else None


def step_rates(rows: list[dict], steps: list[dict]) -> list[dict]:
    """Per published step: done / (done + missing). no_evidence and not_reached do not count,
    and neither do non-conversations (voicemail, no answer, < 30 s): activity, not evaluated.
    A verdict counts for the published step with its criterion (step_identity)."""
    out = []
    matcher = StepMatcher(steps)
    states_of: dict[str, list[str]] = {}
    for row in rows:
        if not row.get("is_conversation", True):
            continue
        counted: set[str] = set()
        for s in row["steps"]:
            live_id = matcher.match(s["step_id"], s.get("criterion"))
            if live_id is not None and live_id not in counted:
                counted.add(live_id)
                states_of.setdefault(live_id, []).append(s["state"])
    for step in steps:
        step_id = str(step.get("step_id"))
        states = states_of.get(step_id, [])
        improvable = states.count("improvable")
        done, missing = states.count("done") + improvable, states.count("missing")
        out.append({
            "step_id": step_id,
            "label": str(step.get("label") or step_id),
            "done": done,
            "improvable": improvable,
            "missing": missing,
            "applicable": done + missing,
            "rate": _rate(done, done + missing),
        })
    return out


_PART_KEY = {"done": "met_steps", "improvable": "met_steps", "missing": "missed_steps",
             "no_evidence": "unknown_steps", "not_reached": "not_applicable_steps"}


def adherence_part(row: dict | None) -> dict | None:
    """THE "% del proceso" of one interaction, as counts for metrics.aggregate_adherence: done
    (improvable counts as done) over done + not done; no evidence and not reached do not count.
    None for a non-conversation, which is never evaluated. Every surface (the rep's coaching, the
    Head of Sales' team, trend and process health) sums these, so they all say one number."""
    if row is None or not row.get("is_conversation", True):
        return None
    part = {"met_steps": 0, "missed_steps": 0, "unknown_steps": 0, "not_applicable_steps": 0}
    for step in row["steps"]:
        part[_PART_KEY.get(step["state"], "unknown_steps")] += 1
    return part


def process_complete(row: dict) -> bool:
    """A conversation with no step missing and at least one done. A follow-up or a call cut at
    the door only had its opening to do: getting it right is not the full process."""
    if not row.get("is_conversation", True) or not row.get("full_process", True):
        return False
    states = [s["state"] for s in row["steps"]]
    return "missing" not in states and any(s in DONE_STATES for s in states)


def choose_focus(rows_prev_week: list[dict], steps: list[dict], peer_rates: dict | None = None) -> dict | None:
    """The one step to work on this week, from the previous full week; None when going well."""
    peers = peer_rates or {}
    candidates = []
    for order, rate in enumerate(step_rates(rows_prev_week, steps)):
        if rate["applicable"] < FOCUS_MIN_APPLICABLE or rate["missing"] < FOCUS_MIN_MISSING:
            continue
        peer = peers.get(rate["step_id"])
        distance = (peer - rate["rate"]) if peer is not None else 0.0
        candidates.append(((rate["rate"], -distance, -rate["applicable"], order), rate, peer))
    if not candidates:
        return None
    _, best, peer = min(candidates, key=lambda item: item[0])
    return {
        "step_id": best["step_id"],
        "label": best["label"],
        "rate": best["rate"],
        "applicable": best["applicable"],
        "missing": best["missing"],
        "peer_median": peer,
    }


def _step_counts(rows: list[dict], step: dict) -> tuple[int, int]:
    rate = step_rates(rows, [step])[0]
    return rate["done"], rate["applicable"]


def focus_progress(rows_this_week: list[dict], step: dict, week_start) -> dict:
    """Mon-Fri counts for the focus step (its published definition) plus the week total.
    achieved: rate >= 0.8 on >= 3."""
    monday = week_start.astimezone(_MADRID).date() if isinstance(week_start, datetime) else week_start
    by_day: dict[date, list[dict]] = {}
    for row in rows_this_week:
        day = madrid_day(row["observed_at"])
        if day is not None:
            by_day.setdefault(day, []).append(row)
    progress = []
    for offset in range(5):
        day = monday + timedelta(days=offset)
        done, applicable = _step_counts(by_day.get(day, []), step)
        progress.append({"date": day.isoformat(), "done": done, "applicable": applicable})
    done, applicable = _step_counts(rows_this_week, step)
    rate = _rate(done, applicable)
    return {
        "progress": progress,
        "week_total": {"done": done, "applicable": applicable, "rate": rate},
        "achieved": applicable >= FOCUS_MIN_APPLICABLE and rate is not None and rate >= ACHIEVED_RATE,
    }


def conversion_split(rows: list[dict], flow: str) -> dict | None:
    """Meeting-agreed rate with a complete process vs an incomplete one; None on thin samples."""
    conversations = [row for row in rows if row["is_conversation"]]
    if len(conversations) < CONVERSION_MIN_SAMPLE.get(flow, CONVERSION_MIN_SAMPLE["sdr"]):
        return None
    complete = [row for row in conversations if process_complete(row)]
    incomplete = [row for row in conversations if not process_complete(row)]
    if len(complete) < CONVERSION_MIN_GROUP or len(incomplete) < CONVERSION_MIN_GROUP:
        return None
    return {
        "complete_rate": _rate(sum(r["meeting_agreed"] for r in complete), len(complete)),
        "incomplete_rate": _rate(sum(r["meeting_agreed"] for r in incomplete), len(incomplete)),
        "complete_n": len(complete),
        "incomplete_n": len(incomplete),
    }


def peer_step_medians(rows_by_user: dict[str, list[dict]], steps: list[dict]) -> dict | None:
    """Median of individual step rates per step; None below 3 people or 30 conversations."""
    people = {uid: rows for uid, rows in rows_by_user.items() if any(r["is_conversation"] for r in rows)}
    conversations = sum(1 for rows in people.values() for r in rows if r["is_conversation"])
    if len(people) < PEER_MIN_PEOPLE or conversations < PEER_MIN_CONVERSATIONS:
        return None
    per_user = [{r["step_id"]: r["rate"] for r in step_rates(rows, steps)} for rows in people.values()]
    medians: dict[str, float | None] = {}
    for step in steps:
        step_id = str(step.get("step_id"))
        rates = [rates[step_id] for rates in per_user if rates.get(step_id) is not None]
        medians[step_id] = round(median(rates), 4) if rates else None
    return medians
