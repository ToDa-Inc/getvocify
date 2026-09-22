"""Post-interaction brief. A missing score does not invent advice, and a voicemail is skipped."""

from __future__ import annotations


def aggregate_brief(
    *,
    screening: str | None,
    score: dict | None,
    patterns: list[dict],
    playbook_present: bool,
    job_error: bool,
    input_revision: str,
    audio_available: bool,
) -> dict:
    sections = _sections(patterns, input_revision)
    coaching = _coaching(score, input_revision)
    base = {
        "input_revision": input_revision,
        "sections": sections,
        "audio_available": audio_available,
        "strength": coaching["strength"],
        "improvement": coaching["improvement"],
        "waiting": False,
    }
    if screening in {"voicemail", "no_response"}:
        return {**base, "status": "skipped", "reason": "no_conversation", "sections": [], "strength": None, "improvement": None}
    if job_error:
        return {**base, "status": "failed", "reason": "job_error"}
    if not playbook_present:
        return {**base, "status": "unavailable", "reason": "missing_playbook", "strength": None, "improvement": None}
    if score is None or score.get("input_revision") != input_revision or score.get("status") in {None, "pending"}:
        if sections or (score and score.get("status") == "pending"):
            return {**base, "status": "partial", "reason": "score_pending", "waiting": score is not None and score.get("status") == "pending"}
        return {**base, "status": "pending", "reason": "waiting_for_sources", "waiting": True}
    if score.get("status") in {"partial", "unavailable"} or score.get("value") is None:
        return {**base, "status": "partial", "reason": score.get("reason") or "score_pending"}
    return {**base, "status": "ready", "reason": None}


def _sections(patterns: list[dict], input_revision: str) -> list[dict]:
    refs: list[str] = []
    for pattern in patterns:
        if pattern.get("input_revision") != input_revision or pattern.get("superseded"):
            continue
        for ref in pattern.get("evidence_refs") or []:
            if ref not in refs:
                refs.append(ref)
            if len(refs) == 3:
                break
        if len(refs) == 3:
            break
    if not refs:
        return []
    return [{"kind": "objections", "evidence_refs": refs}]


def _coaching(score: dict | None, input_revision: str) -> dict:
    if not score or score.get("input_revision") != input_revision:
        return {"strength": None, "improvement": None}
    strengths = [item for item in (score.get("strengths") or []) if item]
    improvements = [item for item in (score.get("improvements") or []) if item]
    return {
        "strength": strengths[0] if strengths else None,
        "improvement": improvements[0] if improvements else None,
    }
