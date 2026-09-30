"""Build C04 once per revision. A repeat reuses the stored intelligence."""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.models.intelligence import EvidenceRef, IntelligenceV1, MeetingFact, quote_is_in_source
from app.services.intelligence.worker import revision_for_memo
from app.services.llm.jev_schemas import INTELLIGENCE_QUESTIONS, evidence_state

Classify = Callable[[dict], dict]


_LISTS = ("objections", "commitments", "competitor_mentions", "playbook_observations", "qualification_observations")
_SCALARS = ("interest", "pain_confirmed", "sales_motion_key")
_STATUS_RANK = {"ready": 2, "partial": 1, "unavailable": 0}


def merge_intelligence(existing: Optional[dict], incoming: dict) -> dict:
    """One block, two producers. The extractor owns interest, objections, commitments and competitors;
    the classifier owns pain and the meeting. Whichever runs last keeps what the other found.
    A block for another input revision is stale and is not merged in."""
    if not isinstance(existing, dict) or not existing or existing.get("input_revision") != incoming.get("input_revision"):
        return incoming
    if existing.get("prompt_version") and incoming.get("prompt_version") and existing["prompt_version"] != incoming["prompt_version"]:
        return incoming  # a re-analysis with a newer prompt replaces the old reading
    merged = dict(existing)
    for key in _SCALARS:
        if incoming.get(key) is not None:
            merged[key] = incoming[key]
    for key in _LISTS:
        if incoming.get(key):
            merged[key] = incoming[key]
    meeting = dict(existing.get("meeting") or {})
    new_meeting = incoming.get("meeting") or {}
    if new_meeting.get("agreed") is not None or not meeting:
        meeting = {**meeting, **new_meeting}
    refs = list(dict.fromkeys([*(existing.get("meeting") or {}).get("evidence_refs", []), *new_meeting.get("evidence_refs", [])]))
    merged["meeting"] = {**meeting, "evidence_refs": refs}
    by_id = {e["id"]: e for e in [*(existing.get("evidence") or []), *(incoming.get("evidence") or [])] if isinstance(e, dict) and e.get("id")}
    merged["evidence"] = list(by_id.values())
    ranked = max((existing.get("status"), incoming.get("status")), key=lambda st: _STATUS_RANK.get(st, -1))
    merged["status"] = ranked
    merged["version"] = incoming.get("version", existing.get("version"))
    merged["input_revision"] = incoming["input_revision"]
    if existing.get("prompt_version") or incoming.get("prompt_version"):
        merged["prompt_version"] = existing.get("prompt_version") or incoming.get("prompt_version")
    return merged


def extraction_with_intelligence(extraction, intelligence: dict) -> dict:
    """Keep the extraction and attach C04, merged with any block already stored. The attached block is
    not part of the input revision."""
    if hasattr(extraction, "model_dump"):
        extraction = extraction.model_dump()
    merged = dict(extraction or {})
    merged["intelligence"] = merge_intelligence(merged.get("intelligence"), intelligence)
    return merged


async def classify_memo(memo: dict, client) -> dict:
    """Ask Jev about this memo. Silence stays unknown, and a late quote is still in the state."""
    excerpts = [
        str(raw["quote"])
        for raw in (memo.get("candidate_evidence") or [])
        if isinstance(raw, dict) and raw.get("quote")
    ]
    state = evidence_state(memo.get("transcript") or "", excerpts)
    return await client.classify_questions(state, INTELLIGENCE_QUESTIONS)


def _tri_state(value: Any, *, yes: str, no: str) -> Optional[bool]:
    if value == yes:
        return True
    if value == no:
        return False
    return None


def interpret_memo(
    memo: dict,
    classify: Classify,
    sources: dict[str, str],
) -> tuple[IntelligenceV1, bool]:
    """Return intelligence and whether a new classification was required."""
    revision = revision_for_memo(memo)
    existing = memo.get("intelligence")
    if isinstance(existing, dict) and existing.get("input_revision") == revision and existing.get("version") == 1:
        return IntelligenceV1.model_validate(existing), False

    result = classify(memo)
    answers = result.get("answers") or {}
    evidence: list[EvidenceRef] = []
    for raw in memo.get("candidate_evidence") or []:
        item = raw if isinstance(raw, EvidenceRef) else EvidenceRef.model_validate(raw)
        if quote_is_in_source(item, sources):
            evidence.append(item)
    agreed = _tri_state(answers.get("meeting_agreed"), yes="agreed", no="not_agreed")
    pain = _tri_state(answers.get("pain_confirmed"), yes="confirmed", no="not_confirmed")
    if result.get("status") == "unavailable":
        status = "unavailable"
    elif agreed is None or pain is None:
        status = "partial"
    else:
        status = "ready"
    intelligence = IntelligenceV1(
        version=1,
        input_revision=revision,
        status=status,
        pain_confirmed=pain,
        meeting=MeetingFact(agreed=agreed, precision="unknown", evidence_refs=[item.id for item in evidence]),
        evidence=evidence,
    )
    return intelligence, True


def drain_once(memo: dict, claim, publish, classify: Classify, sources: dict[str, str]) -> Optional[dict]:
    """Claim one job, reuse or build intelligence, then publish. No claim means nothing ran."""
    claimed = claim()
    if not claimed:
        return None
    intelligence, created = interpret_memo(memo, classify, sources)
    outcome = publish(claimed["run_id"], intelligence.model_dump())
    return {"created": created, "outcome": outcome, "input_revision": intelligence.input_revision}
