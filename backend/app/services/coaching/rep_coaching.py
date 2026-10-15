"""Rep coaching engine: per-step rates, one weekly focus, progress, conversion. No I/O."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Optional
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
        outcome_step = item.get("judged_by") == "rep_outcome"
        if outcome_step and status == "unknown":
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
            # What went wrong, to the rep as "tú" (C04 v8), and what to say next time.
            "reason": item.get("reason") or None,
            "advice": item.get("advice") or None,
            # Settled by what the rep declared (the meeting), not behaviour to coach.
            "outcome": outcome_step,
        })
    objections = []
    for item in intel.get("objections") or []:
        # Every time the prospect resisted: an objection (the offer or the fit) or an obstacle ("I'm driving").
        if isinstance(item, dict):
            response = item.get("response") if isinstance(item.get("response"), dict) else {}
            objections.append({
                "kind": "obstacle" if item.get("kind") == "obstacle" else "objection",
                "category": str(item.get("category") or "other"),
                "objection_id": item.get("objection_id") or None,
                "resolution": item.get("resolution"),
                "quote": item.get("quote") or None,
                "response": response.get("text") or None,
            })
    return {
        "memo_id": str(memo.get("id") or ""),
        "user_id": str(memo.get("user_id") or ""),
        "observed_at": observed.isoformat(),
        "motion": memo.get("sales_motion_key"),
        "kind": memo.get("interaction_kind"),
        "is_conversation": conversation,
        # v8 call type: only a call that runs the whole process can complete it.
        "full_process": call.get("call_type") in FULL_PROCESS_CALLS if call else True,
        # Booked is what the rep declared after the call, never read into the transcript.
        "meeting_agreed": rep_outcome == MEETING_BOOKED,
        "duration_s": duration,
        # v8 says how the call ended, with who said what worked out; older calls keep the note's line.
        "summary_line": (_outcome_line(intel) or _first_plain_line(str(extraction.get("summary") or "")))[:SUMMARY_MAX_CHARS],
        "steps": steps,
        "objections": objections,
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


SLIP_STATES = ("missing", "improvable")


def call_slips(row: dict) -> list[dict]:
    """What to improve in one conversation: the steps not done or done halfway, as the call was
    judged (what went wrong, the moment, what to try). Outcome steps are not behaviour."""
    if not row.get("is_conversation", True):
        return []
    return [
        {key: step.get(key) for key in ("step_id", "label", "criterion", "state", "reason", "quote", "advice")}
        for step in row["steps"]
        if step["state"] in SLIP_STATES and not step.get("outcome")
    ]


_CUSTOM_ENTRY_PREFIX = "objection:custom:"


def _objection_answers(entries: list[dict]) -> dict[str, dict]:
    """{key: {label, how}} from the playbook: a fixed category by its name, a company's own
    objection as "custom:<slug>" (the id the call reading names it by)."""
    out: dict[str, dict] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip().lower()
        guidance = " ".join(str(entry.get("guidance") or "").split()) or None
        entry_id = str(entry.get("entry_id") or "")
        if category == "custom" and entry_id.startswith(_CUSTOM_ENTRY_PREFIX):
            key = f"custom:{entry_id[len(_CUSTOM_ENTRY_PREFIX):]}"
            out.setdefault(key, {"label": " ".join(str(entry.get("label") or "").split()) or None, "how": guidance})
        elif category and category != "custom":
            out.setdefault(category, {"label": None, "how": guidance})
    return out


def objection_entry(entries: list[dict], key: str) -> Optional[dict]:
    """The playbook entry an objection key names (a category, or "custom:<slug>"), or None."""
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip().lower()
        entry_id = str(entry.get("entry_id") or "")
        if category == "custom" and entry_id.startswith(_CUSTOM_ENTRY_PREFIX):
            if key == f"custom:{entry_id[len(_CUSTOM_ENTRY_PREFIX):]}":
                return entry
        elif category and category != "custom" and category == key:
            return entry
    return None


def call_objections(row: dict, entries: list[dict]) -> list[dict]:
    """The objections the prospect raised in one conversation (not obstacles), each with the key the
    playbook answers it by, how it ended, what they said and what the rep replied."""
    if not row.get("is_conversation", True):
        return []
    answers = _objection_answers(entries)
    out = []
    for item in row.get("objections") or []:
        if item.get("kind") != "objection":
            continue
        custom = f"custom:{item['objection_id']}" if item.get("objection_id") else None
        key = custom if custom in answers else item["category"]
        out.append({
            "key": key,
            "category": key.split(":", 1)[0] if key.startswith("custom:") else key,
            "label": (answers.get(key) or {}).get("label"),
            "how": (answers.get(key) or {}).get("how"),
            "resolution": item.get("resolution") or "unknown",
            "quote": item.get("quote"),
            "response": item.get("response"),
        })
    return out


OCCURRENCE_LIMIT = 10


def slipped_steps(rows: list[dict], steps: list[dict], limit: int = OCCURRENCE_LIMIT) -> list[dict]:
    """Every coachable step the rep slipped on in these conversations (not done or halfway), worst
    first, each with the calls it slipped in, newest first: what went wrong, the moment, what to try."""
    coachable = [step for step in steps if not step.get("outcome")]
    by_id = {str(step.get("step_id")): step for step in coachable}
    out = []
    for rate in step_rates(rows, coachable):
        if not rate["missing"] and not rate["improvable"]:
            continue
        step = by_id[rate["step_id"]]
        matcher = StepMatcher([step])
        occurrences = []
        for row in sorted(rows, key=lambda r: r["observed_at"], reverse=True):
            if not row.get("is_conversation", True):
                continue
            for observed in row["steps"]:
                if observed["state"] in SLIP_STATES and matcher.match(observed["step_id"], observed.get("criterion")) == rate["step_id"]:
                    occurrences.append({
                        "memo_id": row["memo_id"],
                        "observed_at": row["observed_at"],
                        **{key: observed.get(key) for key in ("state", "reason", "quote", "advice")},
                    })
                    break
        out.append({
            "step_id": rate["step_id"],
            "label": rate["label"],
            "criterion": str(step.get("criterion") or ""),
            "missing": rate["missing"],
            "improvable": rate["improvable"],
            "applicable": rate["applicable"],
            "example": str(step.get("example") or "") or None,
            "occurrences": occurrences[:limit],
        })
    return sorted(out, key=lambda item: (-item["missing"], -item["improvable"]))


def objection_breakdown(rows: list[dict], entries: list[dict], limit: int = OCCURRENCE_LIMIT) -> list[dict]:
    """Every objection the prospects raised in these conversations (objections, not obstacles), the
    ones left open most first: how many, how each went (what they said, what the rep replied) and the
    playbook's answer."""
    answers = _objection_answers(entries)
    tally: dict[str, dict] = {}
    for row in sorted(rows, key=lambda r: r["observed_at"], reverse=True):
        if not row.get("is_conversation", True):
            continue
        for item in row.get("objections") or []:
            if item.get("kind") != "objection":
                continue
            custom = f"custom:{item['objection_id']}" if item.get("objection_id") else None
            key = custom if custom in answers else item["category"]
            entry = tally.setdefault(key, {"total": 0, "open": 0, "resolved": 0, "occurrences": []})
            entry["total"] += 1
            if item.get("resolution") in ("open", "resolved"):
                entry[item["resolution"]] += 1
            if len(entry["occurrences"]) < limit:
                entry["occurrences"].append({
                    "memo_id": row["memo_id"],
                    "observed_at": row["observed_at"],
                    "resolution": item.get("resolution") or "unknown",
                    "quote": item.get("quote"),
                    "response": item.get("response"),
                })
    return [
        {
            "key": key,
            "category": key.split(":", 1)[0] if key.startswith("custom:") else key,
            "label": (answers.get(key) or {}).get("label"),
            "how": (answers.get(key) or {}).get("how"),
            **entry,
        }
        for key, entry in sorted(tally.items(), key=lambda pair: (-pair[1]["open"], -pair[1]["total"], pair[0]))
    ]


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
