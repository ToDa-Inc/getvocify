"""Deterministic score from extraction. No model call; CRM outcome does not set value."""

from __future__ import annotations

from app.services.coaching.metrics import compute_adherence
from app.services.coaching.scoring import assemble_score

_STATUS = frozenset({"met", "missed", "not_applicable", "unknown"})


def _intelligence_block(extraction: dict, payload: dict | None) -> dict:
    if isinstance(payload, dict) and payload.get("version") == 1:
        return payload
    intel = (extraction or {}).get("intelligence")
    return intel if isinstance(intel, dict) else {}


def _extraction_has_score_inputs(extraction: dict, intelligence: dict) -> bool:
    summary = str((extraction or {}).get("summary") or "").strip()
    if summary:
        return True
    objections = list(intelligence.get("objections") or (extraction or {}).get("objections") or [])
    if objections:
        return True
    observations = list(intelligence.get("playbook_observations") or [])
    return bool(observations)


def _evidence_ids(intelligence: dict) -> list[str]:
    refs: list[str] = []
    for item in intelligence.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("id") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _cited_refs(intelligence: dict, patterns: list[dict] | None, input_revision: str) -> list[str]:
    refs: list[str] = []
    for obs in intelligence.get("playbook_observations") or []:
        if not isinstance(obs, dict):
            continue
        for ref in obs.get("evidence_refs") or []:
            text = str(ref or "").strip()
            if text and text not in refs:
                refs.append(text)
    for obj in intelligence.get("objections") or []:
        if not isinstance(obj, dict):
            continue
        for ref in obj.get("evidence_refs") or []:
            text = str(ref or "").strip()
            if text and text not in refs:
                refs.append(text)
    for pattern in patterns or []:
        if pattern.get("input_revision") != input_revision or pattern.get("superseded"):
            continue
        for ref in pattern.get("evidence_refs") or []:
            text = str(ref or "").strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _criteria_statuses(intelligence: dict, *, evidence_ids: list[str]) -> list[str]:
    known = set(evidence_ids)
    statuses: list[str] = []
    for obs in intelligence.get("playbook_observations") or []:
        if not isinstance(obs, dict):
            continue
        status = str(obs.get("status") or "unknown").strip()
        if status not in _STATUS:
            status = "unknown"
        if status in {"met", "missed"}:
            refs = [str(ref or "").strip() for ref in (obs.get("evidence_refs") or []) if str(ref or "").strip()]
            if not refs or not any(ref in known for ref in refs):
                status = "unknown"
        statuses.append(status)
    return statuses


def _playbook_version_id(_intelligence: dict, memo: dict) -> str | None:
    version = memo.get("playbook_version_id")
    return str(version) if version else None


def _playbook_for_assembly(memo: dict, playbook_version_id: str | None) -> dict | None:
    if not playbook_version_id:
        return None
    ambiguous = bool(memo.get("playbook_ambiguous"))
    return {"id": playbook_version_id, "ambiguous": ambiguous}


def _proposed_value(criteria_statuses: list[str], *, screening: str | None) -> int | None:
    if screening in {"voicemail", "no_response"}:
        return None
    if not criteria_statuses:
        return None
    metrics = compute_adherence(criteria_statuses)
    adherence = metrics.get("adherence")
    if adherence is None:
        return None
    return int(round(float(adherence) * 10))


def build_score_from_extraction(
    *,
    extraction: dict,
    memo: dict,
    input_revision: str,
    payload: dict | None = None,
    patterns: list[dict] | None = None,
    crm_outcome: str | None = None,
    screening: str | None = None,
) -> dict | None:
    """Return an assembled score dict, or None when there is nothing to score."""
    extraction = extraction if isinstance(extraction, dict) else {}
    intelligence = _intelligence_block(extraction, payload)
    if not _extraction_has_score_inputs(extraction, intelligence):
        return None
    revision = str(input_revision or intelligence.get("input_revision") or "").strip()
    if not revision:
        return None
    if screening is None:
        screening = memo.get("screening_outcome")
    playbook_version_id = _playbook_version_id(intelligence, memo)
    playbook = _playbook_for_assembly(memo, playbook_version_id)
    evidence_refs = _evidence_ids(intelligence)
    criteria_statuses = _criteria_statuses(intelligence, evidence_ids=evidence_refs)
    cited_refs = _cited_refs(intelligence, patterns, revision)
    proposed_value = _proposed_value(criteria_statuses, screening=screening)
    score = assemble_score(
        playbook=playbook,
        criteria_statuses=criteria_statuses,
        evidence_refs=evidence_refs,
        cited_refs=cited_refs,
        proposed_value=proposed_value,
        crm_outcome=crm_outcome,
        input_revision=revision,
        playbook_version_id=playbook_version_id,
    )
    score["strengths"] = []
    score["improvements"] = []
    return score


def attach_score_to_job_payload(
    memo: dict,
    payload: dict,
    *,
    extraction: dict,
    patterns: list[dict] | None = None,
    crm_outcome: str | None = None,
) -> dict:
    """Ensure payload carries a deterministic score when extraction is scoreable."""
    if not isinstance(payload, dict):
        return payload
    if isinstance(payload.get("score"), dict):
        return payload
    input_revision = str(payload.get("input_revision") or "")
    score = build_score_from_extraction(
        extraction=extraction,
        memo=memo,
        input_revision=input_revision,
        payload=payload,
        patterns=patterns,
        crm_outcome=crm_outcome,
        screening=memo.get("screening_outcome"),
    )
    if score is None:
        return payload
    enriched = dict(payload)
    enriched["score"] = score
    if "playbook_present" not in enriched:
        enriched["playbook_present"] = bool(memo.get("playbook_version_id") or score.get("playbook_version_id"))
    return enriched
