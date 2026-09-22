"""Persist coaching score and meeting proposal when extraction is saved (no intelligence worker)."""

from __future__ import annotations

import hashlib
import json
import logging
from app.services.coaching.score_assembly import build_score_from_extraction
from app.services.coaching.score_jobs import publish_assembled_score
from app.services.meetings.proposals import build_proposal, infer_agreement

logger = logging.getLogger(__name__)

_MEETING_CUES = ("quedamos", "reunión", "reunion", "vernos", "meeting")
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


def _extraction_blob(extraction: dict) -> str:
    parts: list[str] = []
    for key in ("summary", "meeting_phrase", "meetingPhrase"):
        value = extraction.get(key)
        if value:
            parts.append(str(value))
    steps = extraction.get("next_steps") or extraction.get("nextSteps") or []
    if isinstance(steps, list):
        for step in steps:
            parts.append(str(step))
    return "\n".join(parts)


def _has_meeting_cue(text: str) -> bool:
    lower = text.lower()
    return any(cue in lower for cue in _MEETING_CUES)


def _meeting_phrase_from_extraction(extraction: dict) -> str | None:
    for key in ("meeting_phrase", "meetingPhrase"):
        explicit = str(extraction.get(key) or "").strip()
        if explicit and _has_meeting_cue(explicit):
            return explicit
    blob = _extraction_blob(extraction)
    if not _has_meeting_cue(blob):
        return None
    for line in blob.splitlines():
        if _has_meeting_cue(line):
            return line.strip()
    return blob.strip() or None


def _load_patterns(supabase, memo_id: str) -> list[dict]:
    try:
        stored = supabase.table("interaction_patterns").select("*").eq("memo_id", memo_id).execute()
        return list(getattr(stored, "data", None) or [])
    except Exception:
        return []


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


def _maybe_insert_meeting_proposal(
    supabase,
    *,
    memo_id: str,
    memo: dict,
    extraction: dict,
    input_revision: str,
) -> None:
    phrase = _meeting_phrase_from_extraction(extraction)
    if not phrase:
        return
    if infer_agreement(phrase) == "not_agreed":
        return
    if _proposal_exists(supabase, memo_id, input_revision):
        return
    tz_name = str(memo.get("timezone") or memo.get("company_timezone") or _DEFAULT_TZ)
    proposal = build_proposal(
        proposal_id=_stable_proposal_id(memo_id, input_revision),
        phrase=phrase,
        tz_name=tz_name,
        evidence_refs=["extraction:summary"],
    )
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
    patterns = _load_patterns(supabase, memo_id)
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
        _maybe_insert_meeting_proposal(
            supabase,
            memo_id=memo_id,
            memo=memo,
            extraction=extraction,
            input_revision=input_revision,
        )
    except Exception:
        logger.exception(
            "post-extraction meeting proposal failed",
            extra={"memo_id": memo_id, "input_revision": input_revision},
        )
