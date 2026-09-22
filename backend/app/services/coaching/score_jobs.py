"""Persist an assembled score for a memo. Score memo_jobs call this after assembly."""

from __future__ import annotations

from app.services.coaching.scoring import publish_memo_score


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
