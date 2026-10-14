"""Reads for the reports' numbers and written feedback (REPORT_FEEDBACK_ENABLED): the same memos and
published playbooks as the Coaching tab. Tolerant: any failure means no digest or no feedback, never
a broken report."""

from __future__ import annotations

import logging
from datetime import datetime

from app.services.coaching import rep_coaching_reads as reads
from app.services.company import sales_role_for_user
from app.services.feature_flags import is_enabled
from app.services.playbooks.catalog import catalog_label
from app.services.reporting import feedback_writer, rep_digest

logger = logging.getLogger(__name__)


def type_labels(supabase, company_id: str) -> dict[str, str]:
    """{key: the name the company gave the call type}, the catalog name when it gave none."""
    try:
        rows = supabase.table("playbooks").select("sales_motion_key,label").eq("company_id", company_id).execute().data or []
    except Exception:
        rows = []
    out = {str(row["sales_motion_key"]): str(row.get("label") or "").strip() for row in rows if row.get("sales_motion_key")}
    return {key: label or catalog_label(key) or key for key, label in out.items()}


def _playbook_reader(supabase, company_id: str):
    cache: dict[str, dict] = {}

    def playbook_for(motion: str) -> dict:
        if motion not in cache:
            cache[motion] = reads.load_published_playbook(supabase, company_id, motion)
        return cache[motion]

    return playbook_for


def self_digest(
    supabase, *, company_id: str, user_id: str, start: datetime, end: datetime, previous_start: datetime,
) -> dict | None:
    """The rep's digest for [start, end), compared with [previous_start, start). None when the flag is
    off or the read failed."""
    if not is_enabled(supabase, company_id, feedback_writer.FLAG):
        return None
    try:
        memos = reads.load_memos(supabase, company_id, [user_id], start=previous_start)
        return rep_digest.digest(
            memos,
            start=start,
            end=end,
            previous_start=previous_start,
            playbook_for=_playbook_reader(supabase, company_id),
            labels=type_labels(supabase, company_id),
            sales_role=sales_role_for_user(supabase, user_id, company_id=company_id),
        )
    except Exception:
        logger.warning("report digest failed", extra={"company_id": company_id}, exc_info=True)
        return None


def team_digest(
    supabase, *, company_id: str, reps: list[dict], start: datetime, end: datetime, previous_start: datetime,
) -> dict | None:
    """One row per rep ({userId, name, salesRole?}) and the team's totals and coaching, for the Head of
    Sales' week. None when the flag is off or the read failed."""
    if not is_enabled(supabase, company_id, feedback_writer.FLAG):
        return None
    try:
        user_ids = [str(rep["userId"]) for rep in reps if rep.get("userId")]
        memos = reads.load_memos(supabase, company_id, user_ids, start=previous_start)
        playbook_for = _playbook_reader(supabase, company_id)
        labels = type_labels(supabase, company_id)
        per_rep = []
        for rep in reps:
            mine = [memo for memo in memos if str(memo.get("user_id")) == str(rep.get("userId"))]
            found = rep_digest.digest(
                mine, start=start, end=end, previous_start=previous_start,
                playbook_for=playbook_for, labels=labels, sales_role=rep.get("salesRole"),
            )
            if found["activity"]["calls"] or found["activity"]["meetings_held"] or found["previous"]["calls"]:
                per_rep.append((rep, found))
        team = rep_digest.digest(
            memos, start=start, end=end, previous_start=previous_start,
            playbook_for=playbook_for, labels=labels, sales_role=None,
        )
        return {**team, "reps": rep_digest.team_rows(per_rep)}
    except Exception:
        logger.warning("team report digest failed", extra={"company_id": company_id}, exc_info=True)
        return None


def feedback_for(
    supabase, *, company_id: str, digest: dict | None, audience: str, period: str, previous: dict | None,
) -> dict | None:
    if not digest:
        return None
    payload = {
        "audience": audience,
        "period": period,
        "sales_role": digest.get("sales_role") or "general",
        "facts": digest,
    }
    return feedback_writer.write_feedback(supabase, company_id=company_id, payload=payload, previous=previous)


def enrich(snapshot: dict, digest: dict | None, feedback: dict | None) -> dict:
    """The report with its digest, its written feedback, and Coaching's "% del proceso" as its
    adherence (until now always "No disponible" in a rep's report)."""
    if not digest:
        return snapshot
    snapshot["digest"] = digest
    adherence = (digest.get("coaching") or {}).get("adherence")
    if adherence is not None:
        snapshot.setdefault("metrics", {})["adherence"] = adherence
    if feedback:
        snapshot["feedback"] = feedback
    return snapshot


def previous_day_start(period_start: datetime) -> datetime:
    """The day to compare with: the previous working day (Friday for a Monday)."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    local = period_start.astimezone(ZoneInfo("Europe/Madrid"))
    return period_start - timedelta(days=3 if local.weekday() == 0 else 1)
