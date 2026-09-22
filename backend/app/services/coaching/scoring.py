"""Score assembly. A CRM outcome does not change the mark, and a missing citation is not published."""

from __future__ import annotations

import json

from app.services.coaching.metrics import compute_adherence

PROMPT_VERSION = "scoring_v1"


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
