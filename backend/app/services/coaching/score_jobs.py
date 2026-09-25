"""Persist an assembled score for a memo. Score memo_jobs call this after assembly."""

from __future__ import annotations

import logging

from app.services.coaching.scoring import publish_memo_score

logger = logging.getLogger(__name__)


def publish_assembled_score(
    supabase,
    *,
    memo: dict,
    revision_seq: int,
    score: dict,
    patterns: list[dict] | None = None,
    playbook_present: bool = True,
    job_error: bool = False,
) -> bool:
    """Production path after a score dict is ready. Failed scores are not stored."""
    if score.get("status") == "failed":
        return False
    memo_id = str(memo.get("id") or "")
    input_revision = str(score.get("input_revision") or "")
    if not memo_id or not input_revision:
        return False
    return publish_memo_score(
        supabase,
        memo_id=memo_id,
        input_revision=input_revision,
        revision_seq=int(revision_seq),
        score=score,
        screening=memo.get("screening_outcome"),
        patterns=patterns,
        playbook_present=playbook_present,
        job_error=job_error,
        audio_available=bool(memo.get("audio_path") or memo.get("recording_url")),
    )


def _job_revision_seq(
    supabase,
    memo_id: str,
    input_revision: str,
    *,
    kind: str = "intelligence",
) -> int | None:
    stored = (
        supabase.table("memo_jobs")
        .select("revision_seq")
        .eq("memo_id", memo_id)
        .eq("kind", kind)
        .eq("input_revision", input_revision)
        .limit(1)
        .execute()
    )
    rows = list(getattr(stored, "data", None) or [])
    if not rows:
        return None
    return int(rows[0].get("revision_seq") or 0)


def store_coaching_from_job_payload(supabase, memo: dict, payload: dict) -> None:
    """When a finished job payload carries an assembled score, persist score and brief."""
    if not isinstance(payload, dict):
        return
    score = payload.get("score")
    if not isinstance(score, dict):
        return
    memo_id = str(memo.get("id") or "")
    input_revision = str(score.get("input_revision") or "")
    if not memo_id or not input_revision:
        return
    kind = str(payload.get("job_kind") or "intelligence")
    revision_seq = _job_revision_seq(supabase, memo_id, input_revision, kind=kind)
    if revision_seq is None:
        return
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), list) else None
    try:
        publish_assembled_score(
            supabase,
            memo=memo,
            revision_seq=revision_seq,
            score=score,
            patterns=patterns,
            playbook_present=bool(payload.get("playbook_present", True)),
            job_error=bool(payload.get("job_error")),
        )
    except Exception:
        logger.exception(
            "coaching score persist failed",
            extra={"memo_id": memo_id, "input_revision": input_revision},
        )
