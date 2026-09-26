"""Persist coaching score and meeting proposal when extraction is saved.

The meeting proposal reads C04 `intelligence.meeting` when it is current; until then a transcript
fallback leaves a proposal that always needs review, replaced once C04 is stored."""

from __future__ import annotations

import hashlib
import json
import logging
import re

from app.services.coaching.score_assembly import build_score_from_extraction
from app.services.coaching.score_jobs import publish_assembled_score
from app.services.meetings.proposals import build_proposal, infer_agreement, proposal_from_meeting

logger = logging.getLogger(__name__)

_MEETING_CUES = (
    "quedamos", "reunión", "reunion", "vernos", "nos vemos", "meeting", "demo", "invitación", "invitacion",
)
_SEGMENT = re.compile(r"[^\n.!?]+[.!?]?")
_DEFAULT_TZ = "Europe/Madrid"
_EXTRACTION_REVISION_SEQ = 1


def resolve_input_revision(memo: dict, extraction: dict) -> str:
    revision = str(memo.get("input_revision") or "").strip()
    if revision:
        return revision
    memo_id = str(memo.get("id") or "")
    blob = json.dumps(extraction if isinstance(extraction, dict) else {}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(f"{memo_id}:{blob}".encode("utf-8")).hexdigest()


def _stable_proposal_id(memo_id: str, input_revision: str) -> str:
    digest = hashlib.sha256(f"{memo_id}:{input_revision}:meeting".encode()).hexdigest()[:32]
    return f"meet-{digest}"


def _has_meeting_cue(text: str) -> bool:
    lower = text.lower()
    return any(cue in lower for cue in _MEETING_CUES)


def _meeting_phrase_from_transcript(memo: dict) -> str | None:
    """The latest mention wins. The summary is a paraphrase and never dates a meeting."""
    transcript = str(memo.get("transcript") or "")
    mentions = [part.strip() for part in _SEGMENT.findall(transcript) if _has_meeting_cue(part)]
    return mentions[-1] if mentions else None


def _meeting_revision(memo: dict, extraction: dict) -> str:
    from app.services.intelligence.worker import revision_for_memo

    return revision_for_memo({**memo, "extraction": extraction})


def _current_meeting(memo: dict, extraction: dict) -> dict | None:
    """C04 meeting for this exact revision, from the saved extraction or the stored memo."""
    from app.services.intelligence.extract import is_current

    stored = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    for source in (extraction, stored):
        block = source.get("intelligence") if isinstance(source, dict) else None
        if not isinstance(block, dict) or not isinstance(block.get("meeting"), dict):
            continue
        if is_current({**memo, "extraction": {**extraction, "intelligence": block}}):
            return block["meeting"]
    return None


def _memo_tz(memo: dict) -> str:
    return str(memo.get("timezone") or memo.get("company_timezone") or _DEFAULT_TZ)


def _store_patterns_from_extraction(
    supabase,
    memo: dict,
    extraction: dict,
    input_revision: str,
) -> list[dict]:
    from app.services.intelligence.worker import _store_patterns

    return _store_patterns(
        supabase,
        memo,
        extraction,
        {"input_revision": input_revision},
    )


def _proposal_exists(supabase, memo_id: str, input_revision: str) -> bool:
    try:
        stored = (
            supabase.table("meeting_proposals")
            .select("proposal_id")
            .eq("memo_id", memo_id)
            .eq("input_revision", input_revision)
            .limit(1)
            .execute()
        )
        return bool(getattr(stored, "data", None))
    except Exception:
        return True


def _maybe_publish_score(
    supabase,
    *,
    memo: dict,
    extraction: dict,
    input_revision: str,
    patterns: list[dict] | None,
) -> None:
    score = build_score_from_extraction(
        extraction=extraction,
        memo=memo,
        input_revision=input_revision,
        patterns=patterns,
        crm_outcome=memo.get("crm_outcome"),
        screening=memo.get("screening_outcome"),
    )
    if score is None:
        return
    publish_assembled_score(
        supabase,
        memo=memo,
        revision_seq=_EXTRACTION_REVISION_SEQ,
        score=score,
        patterns=patterns,
        playbook_present=bool(memo.get("playbook_version_id") or score.get("playbook_version_id")),
    )


def _insert_proposal(supabase, *, memo_id: str, input_revision: str, proposal: dict) -> None:
    if proposal.get("closes_deal") is not False:
        return
    row = {
        "proposal_id": proposal["proposal_id"],
        "memo_id": memo_id,
        "input_revision": input_revision,
        "agreement": proposal["agreement"],
        "starts_at": proposal["starts_at"],
        "timezone": proposal["timezone"],
        "precision": proposal["precision"],
        "decision": proposal["decision"],
        "crm_status": proposal["crm_status"],
        "evidence_refs": proposal["evidence_refs"],
    }
    supabase.table("meeting_proposals").insert(row).execute()


def _apply_meeting_fact(supabase, *, memo_id: str, memo: dict, meeting: dict, input_revision: str) -> None:
    """C04 supersedes machine proposals nobody has decided on. A human decision is never replaced."""
    rows = (
        supabase.table("meeting_proposals").select("*").eq("memo_id", memo_id).execute()
    ).data or []
    decided = any(
        row.get("input_revision") == input_revision
        and ((row.get("decision") or "pending") != "pending" or (row.get("crm_status") or "not_requested") != "not_requested")
        for row in rows
    )
    if decided:
        return
    (
        supabase.table("meeting_proposals")
        .delete()
        .eq("memo_id", memo_id)
        .eq("decision", "pending")
        .eq("crm_status", "not_requested")
        .execute()
    )
    proposal = proposal_from_meeting(
        proposal_id=_stable_proposal_id(memo_id, input_revision),
        meeting=meeting,
        tz_name=_memo_tz(memo),
    )
    if proposal:
        _insert_proposal(supabase, memo_id=memo_id, input_revision=input_revision, proposal=proposal)


def _maybe_insert_meeting_proposal(
    supabase,
    *,
    memo_id: str,
    memo: dict,
    extraction: dict,
) -> None:
    input_revision = _meeting_revision(memo, extraction)
    meeting = _current_meeting(memo, extraction)
    if meeting is not None:
        _apply_meeting_fact(supabase, memo_id=memo_id, memo=memo, meeting=meeting, input_revision=input_revision)
        return
    phrase = _meeting_phrase_from_transcript(memo)
    if not phrase:
        return
    if infer_agreement(phrase) == "not_agreed":
        return
    if _proposal_exists(supabase, memo_id, input_revision):
        return
    proposal = build_proposal(
        proposal_id=_stable_proposal_id(memo_id, input_revision),
        phrase=phrase,
        tz_name=_memo_tz(memo),
        evidence_refs=["transcript"],
    )
    _insert_proposal(supabase, memo_id=memo_id, input_revision=input_revision, proposal=proposal)


def refresh_meeting_proposal(supabase, memo: dict) -> None:
    """After C04 is stored: its meeting fact replaces the transcript fallback. Best-effort."""
    memo_id = str((memo or {}).get("id") or "")
    extraction = (memo or {}).get("extraction")
    if not memo_id or not isinstance(extraction, dict):
        return
    try:
        meeting = _current_meeting(memo, extraction)
        if meeting is None:
            return
        _apply_meeting_fact(
            supabase,
            memo_id=memo_id,
            memo=memo,
            meeting=meeting,
            input_revision=_meeting_revision(memo, extraction),
        )
    except Exception:
        logger.exception("meeting proposal refresh failed", extra={"memo_id": memo_id})


def _load_memo(supabase, memo_id: str) -> dict | None:
    try:
        result = supabase.table("memos").select("*").eq("id", memo_id).limit(1).execute()
        rows = list(getattr(result, "data", None) or [])
        return rows[0] if rows else None
    except Exception:
        return None


def run_post_extraction_hooks(
    supabase,
    *,
    memo_id: str,
    extraction: dict,
    memo: dict | None = None,
) -> None:
    """Best-effort score and meeting proposal after extraction save."""
    extraction = extraction if isinstance(extraction, dict) else {}
    if hasattr(extraction, "model_dump"):
        extraction = extraction.model_dump()
    memo = memo if isinstance(memo, dict) else None
    if memo is None:
        memo = _load_memo(supabase, memo_id)
    if not memo:
        memo = {"id": memo_id}
    memo = {**memo, "id": str(memo.get("id") or memo_id)}
    input_revision = resolve_input_revision(memo, extraction)
    patterns: list[dict] = []
    try:
        patterns = _store_patterns_from_extraction(
            supabase,
            memo,
            extraction,
            input_revision,
        ) or []
    except Exception:
        logger.exception(
            "post-extraction pattern projection failed",
            extra={"memo_id": memo_id, "input_revision": input_revision},
        )
        patterns = []
    try:
        _maybe_publish_score(
            supabase,
            memo=memo,
            extraction=extraction,
            input_revision=input_revision,
            patterns=patterns,
        )
    except Exception:
        logger.exception(
            "post-extraction score failed",
            extra={"memo_id": memo_id, "input_revision": input_revision},
        )
    try:
        from app.services.intelligence.extract import schedule_intelligence

        schedule_intelligence(supabase, memo_id, company_id=memo.get("company_id"))
    except Exception:
        logger.exception("post-extraction intelligence schedule failed", extra={"memo_id": memo_id})
    try:
        _maybe_insert_meeting_proposal(
            supabase,
            memo_id=memo_id,
            memo=memo,
            extraction=extraction,
        )
    except Exception:
        logger.exception(
            "post-extraction meeting proposal failed",
            extra={"memo_id": memo_id, "input_revision": input_revision},
        )
