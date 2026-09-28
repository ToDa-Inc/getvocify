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


def _labeled_observations(intelligence: dict, *, evidence_ids: list[str]) -> list[dict]:
    known = set(evidence_ids)
    labeled: list[dict] = []
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
        labeled.append({"step_id": obs.get("step_id"), "status": status})
    return labeled


def _criteria_statuses(intelligence: dict, *, evidence_ids: list[str]) -> list[str]:
    return [item["status"] for item in _labeled_observations(intelligence, evidence_ids=evidence_ids)]


def _missed_steps(intelligence: dict, *, evidence_ids: list[str]) -> list[dict]:
    return [
        {"kind": "step", "id": str(item["step_id"] or "")}
        for item in _labeled_observations(intelligence, evidence_ids=evidence_ids)
        if item["status"] == "missed"
    ]


def _objection_handling(intelligence: dict, *, evidence_ids: list[str]) -> tuple[list[str], list[dict]]:
    """T10/SCORING_OBJECTION_CREDIT_ENABLED: one synthetic criterion per real, evidenced objection.

    `met` when the rep's own reply is cited (resolved, with response_evidence_refs that
    resolve to known evidence). `missed` only when the objection stayed open AND the
    transcript shows the rep spoke again afterward with nothing that counts as an answer —
    a free-text `response` with no evidence earns nothing. When we cannot tell whether the
    rep replied at all (`rep_replied_after` is None), that is `unknown`, never `missed` on
    missing data. Without objections this returns nothing, so an easy call neither gains nor
    loses points."""
    known = set(evidence_ids)
    statuses: list[str] = []
    missed: list[dict] = []
    for obj in intelligence.get("objections") or []:
        if not isinstance(obj, dict):
            continue
        if obj.get("kind", "objection") != "objection":
            continue
        refs = [str(ref or "").strip() for ref in (obj.get("evidence_refs") or []) if str(ref or "").strip()]
        if not refs or not any(ref in known for ref in refs):
            continue
        resolution = obj.get("resolution")
        response_refs = [str(ref or "").strip() for ref in (obj.get("response_evidence_refs") or []) if str(ref or "").strip()]
        response_backed = bool(response_refs) and any(ref in known for ref in response_refs)
        if resolution == "resolved" and response_backed:
            statuses.append("met")
        elif resolution == "open" and not response_backed:
            if obj.get("rep_replied_after") is True:
                statuses.append("missed")
                missed.append({"kind": "objection", "id": str(obj.get("id") or ""), "category": str(obj.get("category") or "other")})
            else:
                statuses.append("unknown")
        else:
            statuses.append("unknown")
    return statuses, missed


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


def coaching_lines(intelligence: dict, *, evidence_ids: list[str]) -> tuple[list[str], list[str]]:
    """What went well and what to improve, straight from cited step observations (C04 v4):
    the step's own label with the rep's words for a met step, the step's own criterion for
    a missed one. Deterministic - no model writes these lines, so nothing generic slips in.
    No observations (flag off, no playbook) -> ([], []), exactly as before."""
    known = set(evidence_ids)
    strengths: list[str] = []
    improvements: list[str] = []
    for obs in intelligence.get("playbook_observations") or []:
        if not isinstance(obs, dict):
            continue
        refs = [ref for ref in (obs.get("evidence_refs") or []) if ref in known]
        if not refs:
            continue
        label = " ".join(str(obs.get("label") or "").split())
        if not label:
            continue
        status = obs.get("status")
        if status == "met":
            quote = " ".join(str(obs.get("quote") or "").split())
            strengths.append(f"{label}: «{quote}»" if quote else label)
        elif status == "missed":
            criterion = " ".join(str(obs.get("criterion") or "").split())
            improvements.append(f"{label}: {criterion}" if criterion and criterion != label else label)
    return strengths, improvements


def build_score_from_extraction(
    *,
    extraction: dict,
    memo: dict,
    input_revision: str,
    payload: dict | None = None,
    patterns: list[dict] | None = None,
    crm_outcome: str | None = None,
    screening: str | None = None,
    objection_credit_enabled: bool = False,
    debrief_v2_enabled: bool = False,
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
    missed_items = _missed_steps(intelligence, evidence_ids=evidence_refs)
    if objection_credit_enabled:
        objection_statuses, objection_missed = _objection_handling(intelligence, evidence_ids=evidence_refs)
        criteria_statuses = criteria_statuses + objection_statuses
        missed_items = missed_items + objection_missed
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
    strengths, improvements = coaching_lines(intelligence, evidence_ids=evidence_refs)
    score["strengths"] = strengths
    score["improvements"] = improvements
    # Flag-off must stay byte-identical to pre-T10 output: missed_items is new surface, so it
    # only appears when a T10 flag actually needs it (objection credit or the v2 debrief).
    if objection_credit_enabled or debrief_v2_enabled:
        score["missed_items"] = missed_items
    return score


def attach_score_to_job_payload(
    memo: dict,
    payload: dict,
    *,
    extraction: dict,
    patterns: list[dict] | None = None,
    crm_outcome: str | None = None,
    objection_credit_enabled: bool = False,
    debrief_v2_enabled: bool = False,
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
        objection_credit_enabled=objection_credit_enabled,
        debrief_v2_enabled=debrief_v2_enabled,
    )
    if score is None:
        return payload
    enriched = dict(payload)
    enriched["score"] = score
    if "playbook_present" not in enriched:
        enriched["playbook_present"] = bool(memo.get("playbook_version_id") or score.get("playbook_version_id"))
    return enriched
