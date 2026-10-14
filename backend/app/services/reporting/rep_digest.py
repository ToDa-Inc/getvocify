"""What a rep did in a day or a week, and how it went: the numbers and the coaching facts the report
shows and its written feedback is built from. Read from the same rows as the Coaching tab
(rep_coaching.interaction_row, is_conversation, adherence_part, slipped_steps), so a report never says
a different number than Coaching. No I/O.

Rules the numbers keep:
  * a rate is only given over at least MIN_RATE_SAMPLE cases: "1 de 1" is not a 100 %;
  * a meeting is booked when the rep declared it (rep_outcome, or the deal moved to the meeting stage in
    the CRM), never read into the transcript; with no declaration at all the count is unknown (None);
  * a voicemail, a no-answer or a line nobody talked on is activity, never a conversation, and is
    never evaluated.
"""

from __future__ import annotations

from datetime import datetime

from app.services.captures import interaction_kind_of
from app.services.coaching import rep_coaching as engine
from app.services.coaching.metrics import aggregate_adherence

MIN_RATE_SAMPLE = 3
# The fixed objection kinds by their Spanish name (a company's own objection has its label).
OBJECTION_ES = {
    "price": "Precio", "timing": "Momento", "authority": "No decide", "competitor": "Competencia",
    "status_quo": "Ya lo tienen resuelto", "trust": "Confianza", "other": "Otra",
}
MAX_SLIPS = 3
MAX_STRENGTHS = 3
MAX_OBJECTIONS = 3
_MEETING_KINDS = frozenset({"meeting", "visit"})
_NO_ANSWER = frozenset({"voicemail", "no_response"})


def rate(part: int, whole: int) -> float | None:
    """part / whole, only when there are enough cases to say it."""
    return round(part / whole, 4) if whole >= MIN_RATE_SAMPLE else None


def in_period(memo: dict, start: datetime, end: datetime) -> bool:
    observed = engine.parse_instant(memo.get("capture_started_at")) or engine.parse_instant(memo.get("created_at"))
    return observed is not None and start <= observed < end


def activity(memos: list[dict], start: datetime, end: datetime) -> dict:
    """Calls made and how many became a conversation, meetings held, meetings the rep booked and the
    minutes talked, for the memos captured in [start, end)."""
    calls = conversations = no_answer = meetings_held = booked = declared = 0
    seconds = 0.0
    for memo in memos:
        if not in_period(memo, start, end):
            continue
        conversation = engine.is_conversation(memo)
        if interaction_kind_of(memo) in _MEETING_KINDS:
            meetings_held += 1 if conversation else 0
        else:
            calls += 1
            no_answer += 1 if memo.get("screening_outcome") in _NO_ANSWER else 0
        if conversation:
            conversations += 1
            duration = engine._duration(memo.get("audio_duration"))
            seconds += duration or 0.0
        booked += 1 if memo.get("rep_outcome") == engine.MEETING_BOOKED else 0
        declared += 1 if memo.get("rep_outcome") else 0
    call_conversations = conversations - meetings_held
    return {
        "calls": calls,
        "conversations": conversations,
        "no_answer": no_answer,
        "meetings_held": meetings_held,
        # None, not 0, when the rep declared no outcome at all: an undeclared meeting is unknown.
        "meetings_booked": booked if declared else None,
        "talk_minutes": round(seconds / 60),
        "connect_rate": rate(call_conversations, calls),
        "booking_rate": rate(booked, conversations) if declared else None,
    }


def _rows(memos: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [row for memo in memos if in_period(memo, start, end) and (row := engine.interaction_row(memo)) is not None]


def _strengths(rows: list[dict]) -> list[dict]:
    """The steps the rep did well most often in these conversations, each with its best quote."""
    tally: dict[str, dict] = {}
    for row in rows:
        if not row.get("is_conversation", True):
            continue
        for step in row["steps"]:
            if step["state"] != "done" or step.get("outcome"):
                continue
            entry = tally.setdefault(step["label"], {"label": step["label"], "times": 0, "quote": None})
            entry["times"] += 1
            entry["quote"] = entry["quote"] or step.get("quote")
    return sorted(tally.values(), key=lambda item: -item["times"])[:MAX_STRENGTHS]


def coaching(memos: list[dict], start: datetime, end: datetime, playbook_for, labels: dict[str, str]) -> dict:
    """How the conversations went against each call type's published playbook: the "% del proceso"
    (Coaching's adherence), the steps done well, the steps that slipped (with what went wrong and what
    to try) and the objections. `playbook_for(motion)` is {steps, entries} of the live playbook."""
    rows = _rows(memos, start, end)
    conversations = [row for row in rows if row.get("is_conversation", True)]
    parts = [part for row in conversations if (part := engine.adherence_part(row)) is not None]
    adherence = aggregate_adherence(parts) if parts else None
    by_type: dict[str, int] = {}
    slips: list[dict] = []
    objections: list[dict] = []
    for motion in sorted({row["motion"] for row in conversations if row.get("motion")}):
        typed = [row for row in conversations if row["motion"] == motion]
        by_type[labels.get(motion) or motion] = len(typed)
        playbook = playbook_for(motion) or {}
        for slip in engine.slipped_steps(typed, playbook.get("steps") or [], limit=1):
            occurrence = (slip.get("occurrences") or [{}])[0]
            slips.append({
                "type": labels.get(motion) or motion,
                "label": slip["label"],
                "missing": slip["missing"],
                "improvable": slip["improvable"],
                "applicable": slip["applicable"],
                "reason": occurrence.get("reason"),
                "advice": occurrence.get("advice"),
                "quote": occurrence.get("quote"),
            })
        for item in engine.objection_breakdown(typed, playbook.get("entries") or [], limit=1):
            occurrence = (item.get("occurrences") or [{}])[0]
            objections.append({
                "label": item.get("label") or OBJECTION_ES.get(item["category"], item["category"]),
                "total": item["total"],
                "open": item["open"],
                "resolved": item["resolved"],
                "quote": occurrence.get("quote"),
                "response": occurrence.get("response"),
                "playbook_answer": item.get("how"),
            })
    slips.sort(key=lambda item: (-item["missing"], -item["improvable"]))
    objections.sort(key=lambda item: (-item["open"], -item["total"]))
    return {
        "evaluated": len(conversations),
        "adherence": adherence["adherence"] if adherence and len(parts) >= MIN_RATE_SAMPLE else None,
        "adherence_steps": (
            {"met": adherence["met_steps"], "applicable": adherence["applicable_steps"]}
            if adherence else None
        ),
        "by_type": by_type,
        "strengths": _strengths(conversations),
        "slips": slips[:MAX_SLIPS],
        "objections": objections[:MAX_OBJECTIONS],
    }


def digest(
    memos: list[dict],
    *,
    start: datetime,
    end: datetime,
    previous_start: datetime,
    playbook_for,
    labels: dict[str, str],
    sales_role: str | None,
) -> dict:
    """The period's numbers, the previous period's to compare, and the coaching facts."""
    return {
        "sales_role": sales_role or "general",
        "activity": activity(memos, start, end),
        "previous": activity(memos, previous_start, start),
        "coaching": coaching(memos, start, end, playbook_for, labels),
    }


def team_rows(digests: list[tuple[dict, dict]]) -> list[dict]:
    """One row per rep for the Head of Sales: [(rep {userId, name, salesRole?}, digest)]."""
    rows = []
    for rep, found in digests:
        act, prev, coach = found["activity"], found["previous"], found["coaching"]
        top = (coach.get("slips") or [None])[0]
        rows.append({
            "name": rep.get("name") or "",
            "sales_role": rep.get("salesRole") or found.get("sales_role") or "general",
            "calls": act["calls"],
            "conversations": act["conversations"],
            "meetings_held": act["meetings_held"],
            "meetings_booked": act["meetings_booked"],
            "previous_conversations": prev["conversations"],
            "previous_meetings_booked": prev["meetings_booked"],
            "adherence": coach.get("adherence"),
            "evaluated": coach.get("evaluated") or 0,
            "top_slip": top["label"] if top else None,
        })
    return sorted(rows, key=lambda row: (-row["conversations"], row["name"].casefold()))
