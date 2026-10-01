"""Pre-meeting brief for the AE (T6). Deterministic, no model call - everything here is a
fact already on record: the CRM's own company fields, the memos for this contact (the
AE's own plus, via T4/D8, the handoff SDR's - the caller passes whichever memos the viewer
is allowed to read), and the closing playbook's steps."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.briefs.v2 import _as_dt, _day_label, missing_steps, plain_sentence
from app.services.followup_logic import pain_quote

MAX_INTERACTIONS = 5


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def company_summary(profile: dict | None) -> dict | None:
    """name, sector (industry) and size, whichever the CRM has. None when the CRM gave
    nothing at all - a brief with no company facts says so, it does not invent one."""
    if not profile:
        return None
    name = _clean(profile.get("company_name"))
    sector = _clean(profile.get("industry") or profile.get("sector"))
    size = _clean(profile.get("company_size") or profile.get("employees"))
    out = {"name": name or None, "sector": sector or None, "size": size or None}
    if not any(out.values()):
        return None
    return out


def _one_phrase(memo: dict) -> str | None:
    """How that conversation ended (C04 v8), else the pain the prospect confirmed in their own
    words, else the note's first sentence."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    nxt = intelligence.get("next") if isinstance(intelligence.get("next"), dict) else {}
    outcome = nxt.get("outcome") if isinstance(nxt.get("outcome"), dict) else {}
    if _clean(outcome.get("text")):
        return _clean(outcome.get("text"))
    quote = _clean(pain_quote(intelligence)) if intelligence else ""
    if quote:
        return f"«{quote}»"
    return plain_sentence(extraction.get("summary"))


def interaction_lines(memos: list[dict], *, author_names: dict[str, str] | None = None) -> list[dict]:
    """Newest first, capped at MAX_INTERACTIONS. Includes every memo the caller passed -
    the handoff SDR's memos as much as the AE's own (T4) - the caller already filtered who
    may be read; this module never decides that."""
    author_names = author_names or {}
    dated = [
        (memo, _as_dt(memo.get("capture_started_at")) or _as_dt(memo.get("created_at")))
        for memo in memos
    ]
    dated = [(memo, at) for memo, at in dated if at is not None]
    dated.sort(key=lambda pair: pair[1], reverse=True)
    lines = []
    for memo, at in dated[:MAX_INTERACTIONS]:
        text = _one_phrase(memo)
        if not text:
            continue
        user_id = str(memo.get("user_id") or "")
        lines.append({
            "date": at.isoformat(),
            "author": author_names.get(user_id) or user_id or None,
            "text": text,
            "source_ref": memo.get("id"),
        })
    return lines


def _open_objections(memos: list[dict]) -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        for item in intelligence.get("objections") or []:
            if not isinstance(item, dict) or item.get("kind") == "obstacle":
                continue  # "me pillas en una reunión" is not something the AE has to answer
            resolution = item.get("resolution") or item.get("state") or "unknown"
            if resolution not in {"open", "unknown"}:
                continue
            text = _clean(item.get("quote") or item.get("text"))
            if not text or text in seen:
                continue
            seen.add(text)
            items.append({"text": text, "source_ref": item.get("id")})
    return items


def _pending_commitments(memos: list[dict], *, now: datetime) -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        for item in intelligence.get("commitments") or []:
            if not isinstance(item, dict):
                continue
            if item.get("status") in {"done", "fulfilled", "completed"}:
                continue
            due = _as_dt(item.get("due_at"))
            if due and due > now:
                continue
            text = _clean(item.get("text") or item.get("summary"))
            if not text or text in seen:
                continue
            seen.add(text)
            items.append({"text": text, "due_at": due.isoformat() if due else None, "source_ref": item.get("id")})
    return items


def open_items(memos: list[dict], *, playbook_steps: list[dict] | None, now: datetime) -> dict:
    """Objections still open, commitments not yet honored, and closing-playbook steps this
    contact has not covered - the three things an AE should not walk into a meeting missing."""
    observations: list[dict] = []
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        observations.extend(intelligence.get("playbook_observations") or [])
    return {
        "objections": _open_objections(memos),
        "commitments": _pending_commitments(memos, now=now),
        "missing_playbook_steps": missing_steps(steps=playbook_steps or [], observations=observations),
    }


def prepare_meeting_brief(
    *,
    company_profile: dict | None = None,
    memos: list[dict] | None = None,
    author_names: dict[str, str] | None = None,
    playbook_steps: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    memos = memos or []
    return {
        "company": company_summary(company_profile),
        "interactions": interaction_lines(memos, author_names=author_names),
        "open_items": open_items(memos, playbook_steps=playbook_steps, now=now),
    }
