"""Deterministic score from extraction. No model call; CRM outcome does not set value."""

from __future__ import annotations

from app.services.coaching.metrics import compute_adherence
from app.services.coaching.scoring import assemble_score
from app.services.playbooks.catalog import INTERNAL_KEY

_STATUS = frozenset({"met", "missed", "not_applicable", "unknown"})
# C04 v7: what a qualification criterion can be, and how each maps onto a score status.
_QUALIFICATION_STATUS = {"found": "met", "missing": "missed", "not_applicable": "not_applicable", "unknown": "unknown"}
_NOT_FOUND = {"es": "No salió", "en": "Not found out"}
_BLOCKS = ("steps", "qualification", "objections")
# Below this share of steps judged (met or missed among those that applied), a mark would
# rest on one or two steps: 1 met + 4 unknown is not a 10. The call still gets its cited
# lines, only without a number.
MIN_STEP_COVERAGE = 0.5


def _intelligence_block(extraction: dict, payload: dict | None) -> dict:
    if isinstance(payload, dict) and payload.get("version") == 1:
        return payload
    intel = (extraction or {}).get("intelligence")
    return intel if isinstance(intel, dict) else {}


def _extraction_has_score_inputs(extraction: dict, intelligence: dict, *, qualification_enabled: bool = False) -> bool:
    summary = str((extraction or {}).get("summary") or "").strip()
    if summary:
        return True
    objections = list(intelligence.get("objections") or (extraction or {}).get("objections") or [])
    if objections:
        return True
    observations = list(intelligence.get("playbook_observations") or [])
    if qualification_enabled:
        observations += list(intelligence.get("qualification_observations") or [])
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


def _cited_refs(
    intelligence: dict, patterns: list[dict] | None, input_revision: str, *, qualification_enabled: bool = False,
) -> list[str]:
    refs: list[str] = []
    if qualification_enabled:
        for obs in intelligence.get("qualification_observations") or []:
            if not isinstance(obs, dict):
                continue
            for ref in obs.get("evidence_refs") or []:
                text = str(ref or "").strip()
                if text and text not in refs:
                    refs.append(text)
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


def _labeled_qualification(intelligence: dict, *, evidence_ids: list[str]) -> list[dict]:
    """C04 v7: one entry per criterion with its score status (found -> met, missing -> missed).
    Like a step, found/missing only count with cited evidence the transcript backs; without it
    the criterion is unknown, never a miss on missing data."""
    known = set(evidence_ids)
    labeled: list[dict] = []
    for obs in intelligence.get("qualification_observations") or []:
        if not isinstance(obs, dict):
            continue
        status = _QUALIFICATION_STATUS.get(str(obs.get("status") or "unknown").strip(), "unknown")
        if status in {"met", "missed"}:
            refs = [str(ref or "").strip() for ref in (obs.get("evidence_refs") or []) if str(ref or "").strip()]
            if not refs or not any(ref in known for ref in refs):
                status = "unknown"
        labeled.append({
            "criterion_id": str(obs.get("criterion_id") or ""),
            "label": " ".join(str(obs.get("label") or "").split()),
            "status": status,
        })
    return labeled


def score_blocks(step_statuses: list[str], qualification_statuses: list[str], objection_statuses: list[str]) -> dict:
    """{steps|qualification|objections: {met, applicable}}. applicable = met + missed; unknown and
    not_applicable count for nothing, so a block the call never exercised has applicable 0."""
    blocks = {}
    for name, statuses in zip(_BLOCKS, (step_statuses, qualification_statuses, objection_statuses)):
        met = statuses.count("met")
        blocks[name] = {"met": met, "applicable": met + statuses.count("missed")}
    return blocks


def blocks_value(
    blocks: dict, *, screening: str | None = None, step_statuses: list[str] | None = None,
) -> int | None:
    """round(10 x the mean of the block ratios), over the blocks that had something to judge.
    None when no block did: there is nothing to grade. Same step-coverage floor as the
    adherence mark: too few steps judged and there is no number."""
    if screening in {"voicemail", "no_response"}:
        return None
    if _thin_step_coverage(step_statuses):
        return None
    ratios = [block["met"] / block["applicable"] for block in blocks.values() if block["applicable"] > 0]
    if not ratios:
        return None
    return int(round(10 * sum(ratios) / len(ratios)))


def _objection_handling(
    intelligence: dict,
    *,
    evidence_ids: list[str],
    with_custom_id: bool = False,
    answered_categories: frozenset[str] | None = None,
) -> tuple[list[str], list[dict]]:
    """T10/SCORING_OBJECTION_CREDIT_ENABLED: one synthetic criterion per real, evidenced objection.

    `met` when the rep's own reply is cited (resolved, with response_evidence_refs that
    resolve to known evidence). `missed` only when the objection stayed open AND the
    transcript shows the rep spoke again afterward with nothing that counts as an answer —
    a free-text `response` with no evidence earns nothing. When we cannot tell whether the
    rep replied at all (`rep_replied_after` is None), that is `unknown`, never `missed` on
    missing data. Without objections this returns nothing, so an easy call neither gains nor
    loses points.

    `answered_categories`: the categories the pinned playbook has an answer for. An objection
    the playbook says nothing about is not the rep's miss against the playbook, so it does not
    count. None = not known (no playbook read), every category counts as before."""
    known = set(evidence_ids)
    statuses: list[str] = []
    missed: list[dict] = []
    for obj in intelligence.get("objections") or []:
        if not isinstance(obj, dict):
            continue
        if obj.get("kind", "objection") != "objection":
            continue
        if answered_categories is not None and str(obj.get("category") or "other") not in answered_categories:
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
                item = {"kind": "objection", "id": str(obj.get("id") or ""), "category": str(obj.get("category") or "other")}
                if with_custom_id and obj.get("objection_id"):
                    item["objection_id"] = str(obj["objection_id"])
                missed.append(item)
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


def _thin_step_coverage(step_statuses: list[str] | None) -> bool:
    """True when fewer than MIN_STEP_COVERAGE of the steps were judged: a mark would rest on too little."""
    if not step_statuses:
        return False
    coverage = compute_adherence(step_statuses).get("coverage")
    return coverage is not None and coverage < MIN_STEP_COVERAGE


def _proposed_value(
    criteria_statuses: list[str], *, screening: str | None, step_statuses: list[str] | None = None,
) -> int | None:
    if screening in {"voicemail", "no_response"}:
        return None
    if not criteria_statuses:
        return None
    if _thin_step_coverage(step_statuses):
        return None
    metrics = compute_adherence(criteria_statuses)
    adherence = metrics.get("adherence")
    if adherence is None:
        return None
    return int(round(float(adherence) * 10))


def _language(memo: dict) -> str:
    """Spanish unless the conversation itself is clearly English."""
    from app.services.crm_copilot.language import reply_language

    return reply_language(str(memo.get("transcript") or "")) or "es"


def qualification_improvements(intelligence: dict, *, evidence_ids: list[str], language: str = "es") -> list[str]:
    """«No salió: {label}» for each cited missing criterion. Deterministic, like the step lines."""
    prefix = _NOT_FOUND.get(language, _NOT_FOUND["es"])
    return [
        f"{prefix}: {item['label']}"
        for item in _labeled_qualification(intelligence, evidence_ids=evidence_ids)
        if item["status"] == "missed" and item["label"]
    ]


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
    qualification_enabled: bool = False,
    answered_categories: frozenset[str] | None = None,
) -> dict | None:
    """Return an assembled score dict, or None when there is nothing to score.

    qualification_enabled (PLAYBOOK_QUALIFICATION_ENABLED): qualification observations become
    criteria (found -> met, missing -> missed), the score carries `blocks` and its value is the
    mean of the blocks' ratios. Off, nothing below differs from before.

    An `internal` memo (no customer in the conversation) is never scored."""
    if (memo or {}).get("sales_motion_key") == INTERNAL_KEY:
        return None
    extraction = extraction if isinstance(extraction, dict) else {}
    intelligence = _intelligence_block(extraction, payload)
    if not _extraction_has_score_inputs(extraction, intelligence, qualification_enabled=qualification_enabled):
        return None
    revision = str(input_revision or intelligence.get("input_revision") or "").strip()
    if not revision:
        return None
    if screening is None:
        screening = memo.get("screening_outcome")
    playbook_version_id = _playbook_version_id(intelligence, memo)
    playbook = _playbook_for_assembly(memo, playbook_version_id)
    evidence_refs = _evidence_ids(intelligence)
    step_statuses = _criteria_statuses(intelligence, evidence_ids=evidence_refs)
    criteria_statuses = list(step_statuses)
    missed_items = _missed_steps(intelligence, evidence_ids=evidence_refs)
    blocks = None
    if qualification_enabled:
        labeled_qualification = _labeled_qualification(intelligence, evidence_ids=evidence_refs)
        qualification_statuses = [item["status"] for item in labeled_qualification]
        criteria_statuses = criteria_statuses + qualification_statuses
        missed_items = missed_items + [
            {"kind": "qualification", "id": item["criterion_id"], "label": item["label"]}
            for item in labeled_qualification
            if item["status"] == "missed"
        ]
        # With the three blocks the objections the rep faced always count (they are a block of
        # the mark), whatever SCORING_OBJECTION_CREDIT_ENABLED says for the old adherence.
        objection_statuses, objection_missed = _objection_handling(
            intelligence, evidence_ids=evidence_refs, with_custom_id=True, answered_categories=answered_categories,
        )
        criteria_statuses = criteria_statuses + objection_statuses
        missed_items = missed_items + objection_missed
        blocks = score_blocks(step_statuses, qualification_statuses, objection_statuses)
    elif objection_credit_enabled:
        objection_statuses, objection_missed = _objection_handling(
            intelligence, evidence_ids=evidence_refs, answered_categories=answered_categories,
        )
        criteria_statuses = criteria_statuses + objection_statuses
        missed_items = missed_items + objection_missed
    cited_refs = _cited_refs(intelligence, patterns, revision, qualification_enabled=qualification_enabled)
    if blocks is not None:
        proposed_value = blocks_value(blocks, screening=screening, step_statuses=step_statuses)
    else:
        proposed_value = _proposed_value(criteria_statuses, screening=screening, step_statuses=step_statuses)
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
    if qualification_enabled:
        improvements = improvements + qualification_improvements(
            intelligence, evidence_ids=evidence_refs, language=_language(memo),
        )
    score["strengths"] = strengths
    score["improvements"] = improvements
    if blocks is not None:
        score["blocks"] = blocks
    # coaching_lines only writes lines for observations whose quote is in the transcript, so
    # these improvements carry their own evidence (the brief shows them without objections).
    if improvements:
        score["improvements_cited"] = True
    # Flag-off must stay byte-identical to pre-T10 output: missed_items is new surface, so it
    # only appears when a T10 flag actually needs it (objection credit, the v2 debrief or the
    # qualification blocks).
    if objection_credit_enabled or debrief_v2_enabled or qualification_enabled:
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
    qualification_enabled: bool = False,
    answered_categories: frozenset[str] | None = None,
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
        qualification_enabled=qualification_enabled,
        answered_categories=answered_categories,
    )
    if score is None:
        return payload
    enriched = dict(payload)
    enriched["score"] = score
    if "playbook_present" not in enriched:
        enriched["playbook_present"] = bool(memo.get("playbook_version_id") or score.get("playbook_version_id"))
    return enriched
