"""A meeting proposal. Agreeing to meet does not close the deal."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.meetings.time_resolution import local_time_is_ambiguous, resolve_phrase

_TENTATIVE = ("podríamos vernos", "podriamos vernos", "a lo mejor nos vemos")
_AGREED = (
    "quedamos",
    "confirmado",
    "te mando la invitaci",
    "te envío la invitaci",
    "te envio la invitaci",
    "te pongo una reuni",
    "te agendo",
    "agendado",
)
_PRECISION = {"date": "date_only", "time": "ambiguous"}


def latest_proposal(rows: list[dict]) -> dict | None:
    """The newest stored proposal. No row is not a meeting."""
    if not rows:
        return None
    row = max(rows, key=lambda item: str(item.get("created_at") or item.get("input_revision") or ""))
    agreed = row.get("agreement") == "agreed"
    starts_at = row.get("starts_at")
    return {
        "proposal_id": row.get("proposal_id"),
        "agreement": row.get("agreement"),
        "starts_at": starts_at,
        "timezone": row.get("timezone"),
        "decision": row.get("decision") or "pending",
        "crm_status": row.get("crm_status") or "not_requested",
        "needs_review": not agreed or not starts_at,
    }


def infer_agreement(phrase: str) -> str:
    text = " ".join((phrase or "").lower().split())
    if any(cue in text for cue in _TENTATIVE):
        return "unknown"
    if "no podemos" in text or "no quedamos" in text:
        return "not_agreed"
    if any(cue in text for cue in _AGREED):
        return "agreed"
    return "unknown"


def _proposal(
    proposal_id: str,
    *,
    agreement: str,
    starts_at: str | None,
    tz_name: str,
    precision: str,
    evidence_refs: list[str],
    needs_review: bool,
) -> dict:
    return {
        "proposal_id": proposal_id,
        "agreement": agreement,
        "starts_at": starts_at,
        "timezone": tz_name,
        "precision": precision,
        "decision": "pending",
        "crm_status": "not_requested",
        "evidence_refs": evidence_refs,
        "needs_review": needs_review,
        "closes_deal": False,
    }


def build_proposal(
    *,
    proposal_id: str,
    phrase: str,
    tz_name: str,
    evidence_refs: list[str],
    corrections: list[dict] | None = None,
    on=None,
    uploaded_at: str | None = None,
) -> dict:
    del uploaded_at  # never becomes the meeting time
    confirmed = [item for item in (corrections or []) if item.get("confirmed_by_both")]
    if confirmed:
        last = confirmed[-1]
        return _proposal(
            proposal_id,
            agreement="agreed",
            starts_at=last["starts_at"],
            tz_name=tz_name,
            precision="exact",
            evidence_refs=list(evidence_refs) + [last["evidence_ref"]],
            needs_review=False,
        )
    resolved = resolve_phrase(phrase, tz_name=tz_name, on=on)
    return _proposal(
        proposal_id,
        agreement=infer_agreement(phrase),
        starts_at=resolved["starts_at"],
        tz_name=tz_name,
        precision=resolved["precision"],
        evidence_refs=list(evidence_refs),
        needs_review=resolved["needs_review"],
    )


def _exact_instant(value: str, tz_name: str) -> str | None:
    """Only an offset that is the memo zone's own, on an hour that happens once."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        zone = ZoneInfo(tz_name)
    except (ValueError, ZoneInfoNotFoundError):
        return None
    if parsed.tzinfo is None:
        return None
    local = parsed.astimezone(zone)
    if local.replace(tzinfo=None) != parsed.replace(tzinfo=None):
        return None
    if local_time_is_ambiguous(local.year, local.month, local.day, local.hour, local.minute, tz_name):
        return None
    return parsed.isoformat()


def proposal_from_meeting(*, proposal_id: str, meeting: dict, tz_name: str) -> dict | None:
    """C04 meeting to C15. Booked is agreed plus the exact time both accepted; less waits for review."""
    if not isinstance(meeting, dict) or meeting.get("agreed") is not True:
        return None
    refs = [str(ref) for ref in meeting.get("evidence_refs") or [] if ref]
    if not refs:
        return None
    raw = meeting.get("starts_at")
    exact = _exact_instant(raw, tz_name) if meeting.get("precision") == "time" and isinstance(raw, str) else None
    if exact:
        return build_proposal(
            proposal_id=proposal_id,
            phrase="",
            tz_name=tz_name,
            evidence_refs=refs[:-1],
            corrections=[{"starts_at": exact, "evidence_ref": refs[-1], "confirmed_by_both": True}],
        )
    return _proposal(
        proposal_id,
        agreement="agreed",
        starts_at=None,
        tz_name=tz_name,
        precision=_PRECISION.get(str(meeting.get("precision")), "unknown"),
        evidence_refs=refs,
        needs_review=True,
    )


def insert_proposal_statement(memo_id: str, input_revision: str, proposal: dict) -> str:
    starts = "NULL" if proposal["starts_at"] is None else "'" + proposal["starts_at"].replace("'", "''") + "'"
    evidence = json.dumps(proposal["evidence_refs"]).replace("'", "''")
    return (
        "INSERT INTO meeting_proposals "
        "(proposal_id, memo_id, input_revision, agreement, starts_at, timezone, precision, decision, crm_status, evidence_refs) "
        f"VALUES ('{proposal['proposal_id']}', '{memo_id}', '{input_revision}', '{proposal['agreement']}', "
        f"{starts}, '{proposal['timezone']}', '{proposal['precision']}', 'pending', 'not_requested', '{evidence}'::jsonb);"
    )
