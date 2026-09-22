"""A meeting proposal. Agreeing to meet does not close the deal."""

from __future__ import annotations

import json

from app.services.meetings.time_resolution import resolve_phrase

_TENTATIVE = ("podríamos vernos", "podriamos vernos", "a lo mejor nos vemos")


def infer_agreement(phrase: str) -> str:
    text = " ".join((phrase or "").lower().split())
    if any(cue in text for cue in _TENTATIVE):
        return "unknown"
    if "no podemos" in text or "no quedamos" in text:
        return "not_agreed"
    if "quedamos" in text or "confirmado" in text:
        return "agreed"
    return "unknown"


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
        starts_at = last["starts_at"]
        precision = "exact"
        needs_review = False
        evidence = list(evidence_refs) + [last["evidence_ref"]]
    else:
        resolved = resolve_phrase(phrase, tz_name=tz_name, on=on)
        starts_at = resolved["starts_at"]
        precision = resolved["precision"]
        needs_review = resolved["needs_review"]
        evidence = list(evidence_refs)
    return {
        "proposal_id": proposal_id,
        "agreement": infer_agreement(phrase) if not confirmed else "agreed",
        "starts_at": starts_at,
        "timezone": tz_name,
        "precision": precision,
        "decision": "pending",
        "crm_status": "not_requested",
        "evidence_refs": evidence,
        "needs_review": needs_review,
        "closes_deal": False,
    }


def insert_proposal_statement(memo_id: str, input_revision: str, proposal: dict) -> str:
    starts = "NULL" if proposal["starts_at"] is None else "'" + proposal["starts_at"].replace("'", "''") + "'"
    evidence = json.dumps(proposal["evidence_refs"]).replace("'", "''")
    return (
        "INSERT INTO meeting_proposals "
        "(proposal_id, memo_id, input_revision, agreement, starts_at, timezone, precision, decision, crm_status, evidence_refs) "
        f"VALUES ('{proposal['proposal_id']}', '{memo_id}', '{input_revision}', '{proposal['agreement']}', "
        f"{starts}, '{proposal['timezone']}', '{proposal['precision']}', 'pending', 'not_requested', '{evidence}'::jsonb);"
    )
