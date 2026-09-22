"""Score assembly. A CRM outcome does not change the mark, and a missing citation is not published."""

from __future__ import annotations

import json
import logging

from app.services.coaching.brief_preferences import publish_if_newer
from app.services.coaching.briefs import materialize_brief
from app.services.coaching.metrics import compute_adherence

PROMPT_VERSION = "scoring_v1"
logger = logging.getLogger(__name__)


def assemble_score(
    *,
    playbook: dict | None,
    criteria_statuses: list[str],
    evidence_refs: list[str],
    cited_refs: list[str],
    proposed_value: int | None,
    crm_outcome: str | None,
    input_revision: str,
    playbook_version_id: str | None,
) -> dict:
    if playbook is None:
        return _empty("unavailable", "missing_playbook", input_revision, None)
    if playbook.get("ambiguous"):
        metrics = compute_adherence(criteria_statuses)
        return {
            "status": "partial",
            "value": None,
            "reason": "ambiguous_playbook",
            "crm_outcome": crm_outcome,
            "playbook_version_id": playbook_version_id,
            "input_revision": input_revision,
            "prompt_version": PROMPT_VERSION,
            **metrics,
        }
    missing = [ref for ref in cited_refs if ref not in evidence_refs]
    if missing:
        return _empty("failed", "uncited_evidence", input_revision, playbook_version_id)
    metrics = compute_adherence(criteria_statuses)
    value = proposed_value
    reason = None
    status = "ready"
    if metrics["adherence"] is None or proposed_value is None:
        value = None
        reason = "insufficient_evidence"
        status = "partial"
    return {
        "status": status,
        "value": value,
        "reason": reason,
        "crm_outcome": crm_outcome,
        "playbook_version_id": playbook_version_id,
        "input_revision": input_revision,
        "prompt_version": PROMPT_VERSION,
        **metrics,
    }


def _empty(status: str, reason: str, input_revision: str, playbook_version_id: str | None) -> dict:
    return {
        "status": status,
        "value": None,
        "reason": reason,
        "crm_outcome": None,
        "playbook_version_id": playbook_version_id,
        "input_revision": input_revision,
        "prompt_version": PROMPT_VERSION,
        "met_steps": 0,
        "missed_steps": 0,
        "applicable_steps": 0,
        "unknown_steps": 0,
        "not_applicable_steps": 0,
        "adherence": None,
        "coverage": None,
    }


def publish_score_statement(*, memo_id: str, input_revision: str, revision_seq: int, score: dict) -> str:
    payload = json.dumps(score, ensure_ascii=False).replace("'", "''")
    return (
        "INSERT INTO memo_scores (memo_id, input_revision, revision_seq, playbook_version_id, prompt_version, score) "
        f"VALUES ('{memo_id}', '{input_revision}', {int(revision_seq)}, "
        f"{_text(score.get('playbook_version_id'))}, '{PROMPT_VERSION}', '{payload}'::jsonb) "
        "ON CONFLICT (memo_id, input_revision) DO UPDATE SET "
        "score = EXCLUDED.score, revision_seq = EXCLUDED.revision_seq "
        "WHERE memo_scores.revision_seq < EXCLUDED.revision_seq;"
    )


def _text(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def publish_memo_score(
    supabase,
    *,
    memo_id: str,
    input_revision: str,
    revision_seq: int,
    score: dict,
    screening: str | None = None,
    patterns: list[dict] | None = None,
    playbook_present: bool = True,
    job_error: bool = False,
    audio_available: bool = False,
) -> bool:
    """Production score publish: persist memo_scores, then materialize post_interaction_briefs."""
    if not _upsert_score_if_newer(supabase, memo_id, input_revision, revision_seq, score):
        return False
    store_memo_score(
        supabase,
        memo_id=memo_id,
        input_revision=input_revision,
        revision_seq=revision_seq,
        score=score,
        screening=screening,
        patterns=patterns,
        playbook_present=playbook_present,
        job_error=job_error,
        audio_available=audio_available,
        score_already_persisted=True,
    )
    return True


def store_memo_score(
    supabase,
    *,
    memo_id: str,
    input_revision: str,
    revision_seq: int,
    score: dict,
    screening: str | None = None,
    patterns: list[dict] | None = None,
    playbook_present: bool = True,
    job_error: bool = False,
    audio_available: bool = False,
    score_already_persisted: bool = False,
) -> bool:
    """Upsert memo_scores unless already written, then upsert post_interaction_briefs from aggregate_brief."""
    if score_already_persisted:
        if not _score_revision_at_least(supabase, memo_id, input_revision, revision_seq):
            return False
    elif not _upsert_score_if_newer(supabase, memo_id, input_revision, revision_seq, score):
        return False
    try:
        brief = materialize_brief(
            screening=screening,
            score=score,
            patterns=list(patterns or []),
            playbook_present=playbook_present,
            job_error=job_error,
            input_revision=input_revision,
            audio_available=audio_available,
        )
        _upsert_brief_if_newer(
            supabase,
            memo_id=memo_id,
            input_revision=input_revision,
            revision_seq=revision_seq,
            status=brief["status"],
            body=brief["body"],
        )
    except Exception:
        logger.exception(
            "post_interaction_brief persist failed",
            extra={"memo_id": memo_id, "input_revision": input_revision},
        )
    return True


def _score_revision_at_least(
    supabase,
    memo_id: str,
    input_revision: str,
    revision_seq: int,
) -> bool:
    stored = (
        supabase.table("memo_scores")
        .select("revision_seq")
        .eq("memo_id", memo_id)
        .eq("input_revision", input_revision)
        .execute()
    )
    rows = list(getattr(stored, "data", None) or [])
    if not rows:
        return False
    return int(rows[0].get("revision_seq") or 0) >= int(revision_seq)


def _upsert_score_if_newer(supabase, memo_id: str, input_revision: str, revision_seq: int, score: dict) -> bool:
    stored = (
        supabase.table("memo_scores")
        .select("revision_seq")
        .eq("memo_id", memo_id)
        .eq("input_revision", input_revision)
        .execute()
    )
    rows = list(getattr(stored, "data", None) or [])
    if rows and (rows[0].get("revision_seq") or 0) >= revision_seq:
        return False
    (
        supabase.table("memo_scores")
        .upsert(
            {
                "memo_id": memo_id,
                "input_revision": input_revision,
                "revision_seq": revision_seq,
                "playbook_version_id": score.get("playbook_version_id"),
                "prompt_version": PROMPT_VERSION,
                "score": score,
            }
        )
        .execute()
    )
    return True


def _upsert_brief_if_newer(
    supabase,
    *,
    memo_id: str,
    input_revision: str,
    revision_seq: int,
    status: str,
    body: dict,
) -> None:
    stored = (
        supabase.table("post_interaction_briefs")
        .select("revision_seq")
        .eq("memo_id", memo_id)
        .eq("input_revision", input_revision)
        .execute()
    )
    rows = list(getattr(stored, "data", None) or [])
    current = rows[0] if rows else None
    incoming = {
        "memo_id": memo_id,
        "input_revision": input_revision,
        "revision_seq": revision_seq,
        "status": status,
        "body": body,
    }
    if publish_if_newer(current, incoming) is None:
        return
    supabase.table("post_interaction_briefs").upsert(incoming).execute()
