"""Team metrics. Members get nothing. Adherence is the sum of counts, not the average of rates."""

from __future__ import annotations

from app.services.coaching.metrics import aggregate_adherence

_TEAM_ROLES = frozenset({"owner", "admin"})
_SCREENING_ATTEMPTS = frozenset({"voicemail", "no_response", "connected"})


class TeamAccessError(Exception):
    pass


def assert_team_reader(role: str) -> None:
    if role not in _TEAM_ROLES:
        raise TeamAccessError("equipo denegado")


def authorized_scope(*, role: str, requested_user_id: str | None, instruction: str) -> dict:
    """Free text never widens the scope. The role is the server's."""
    del instruction
    assert_team_reader(role)
    if requested_user_id:
        return {"scope": "user", "user_id": requested_user_id}
    return {"scope": "team", "user_id": None}


def activity_counts(rows: list[dict]) -> dict:
    """Voicemail and no-answer are attempts only. Connected is an attempt and a conversation."""
    attempts = 0
    connected = 0
    meetings = 0
    for row in rows:
        screening = row.get("screening")
        if screening in _SCREENING_ATTEMPTS:
            attempts += 1
            if screening == "connected":
                connected += 1
        if row.get("meeting_agreed") is True:
            meetings += 1
    return {"attempts": attempts, "connected": connected, "meetings": meetings}


def activity_row_from_memo(memo: dict) -> dict | None:
    screening = memo.get("screening_outcome")
    if screening not in _SCREENING_ATTEMPTS:
        return None
    intel = memo.get("intelligence") or (memo.get("extraction") or {}).get("intelligence") or {}
    meeting = intel.get("meeting") if isinstance(intel, dict) else {}
    agreed = meeting.get("agreed") if isinstance(meeting, dict) else None
    return {"screening": screening, "meeting_agreed": agreed is True}


def adherence_part_from_score(score: dict) -> dict | None:
    if score.get("status") not in {"ready", "partial"}:
        return None
    return {
        "met_steps": int(score.get("met_steps") or 0),
        "missed_steps": int(score.get("missed_steps") or 0),
        "unknown_steps": int(score.get("unknown_steps") or 0),
        "not_applicable_steps": int(score.get("not_applicable_steps") or 0),
    }


def load_team_adherence_inputs(supabase, company_id: str) -> dict:
    """Memos and scores for the company. Empty lists when the read fails."""
    activity_rows: list[dict] = []
    parts: list[dict] = []
    playbook_present = False
    try:
        memos = (
            supabase.table("memos")
            .select("id,screening_outcome,extraction,intelligence")
            .eq("company_id", company_id)
            .execute()
        )
        memo_ids: list[str] = []
        for memo in memos.data or []:
            memo_ids.append(str(memo.get("id")))
            row = activity_row_from_memo(memo)
            if row is not None:
                activity_rows.append(row)
        if memo_ids:
            scores = supabase.table("memo_scores").select("memo_id,score").in_("memo_id", memo_ids).execute()
            for item in scores.data or []:
                score = item.get("score") or {}
                part = adherence_part_from_score(score if isinstance(score, dict) else {})
                if part is not None:
                    parts.append(part)
        published = (
            supabase.table("playbooks")
            .select("id, playbook_versions!inner(status)")
            .eq("company_id", company_id)
            .eq("playbook_versions.status", "published")
            .limit(1)
            .execute()
        )
        playbook_present = bool(published.data)
    except Exception:
        pass
    return {
        "parts": parts,
        "playbook_present": playbook_present,
        "sample_size": len(parts),
        "activity_rows": activity_rows,
    }


def team_adherence(
    *,
    role: str,
    parts: list[dict],
    playbook_present: bool,
    sample_size: int,
    activity_rows: list[dict] | None = None,
) -> dict:
    assert_team_reader(role)
    activity = activity_counts(activity_rows) if activity_rows is not None else {}
    if not playbook_present or sample_size < 1:
        body = {
            "met_steps": 0,
            "applicable_steps": 0,
            "unknown_steps": 0,
            "adherence": None,
            "coverage": None,
            "conclusion": None,
        }
        body.update(activity)
        return body
    metrics = aggregate_adherence(parts)
    conclusion = None
    if sample_size < 5:
        conclusion = None
    body = {
        "met_steps": metrics["met_steps"],
        "applicable_steps": metrics["applicable_steps"],
        "unknown_steps": metrics["unknown_steps"],
        "adherence": metrics["adherence"],
        "coverage": metrics["coverage"],
        "conclusion": conclusion,
    }
    body.update(activity)
    return body
