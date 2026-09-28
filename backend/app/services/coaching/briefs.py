"""Post-interaction brief. A missing score does not invent advice, and a voicemail is skipped."""

from __future__ import annotations


def absent_brief() -> dict:
    """No stored row yet. That is not a missing playbook and not a job in progress."""
    return {
        "status": "pending",
        "reason": "not_started",
        "input_revision": "",
        "sections": [],
        "audio_available": False,
        "strength": None,
        "improvement": None,
        "waiting": False,
    }


def aggregate_brief(
    *,
    screening: str | None,
    score: dict | None,
    patterns: list[dict],
    playbook_present: bool,
    job_error: bool,
    input_revision: str,
    audio_available: bool,
    debrief_v2: bool = False,
    flow: str | None = None,
    missed: list[dict] | None = None,
    evidence: list[dict] | None = None,
    progress: list[float | None] | None = None,
    meeting_agreed: bool | None = None,
    next_step_agreed: bool | None = None,
) -> dict:
    brief = _aggregate_brief_v1(
        screening=screening,
        score=score,
        patterns=patterns,
        playbook_present=playbook_present,
        job_error=job_error,
        input_revision=input_revision,
        audio_available=audio_available,
    )
    if not debrief_v2:
        return brief
    return _apply_debrief_v2(
        brief,
        flow=flow,
        missed=missed,
        evidence=evidence,
        progress=progress,
        meeting_agreed=meeting_agreed,
        next_step_agreed=next_step_agreed,
    )


def _apply_debrief_v2(
    brief: dict,
    *,
    flow: str | None,
    missed: list[dict] | None,
    evidence: list[dict] | None,
    progress: list[float | None] | None,
    meeting_agreed: bool | None,
    next_step_agreed: bool | None,
) -> dict:
    """T10/DEBRIEF_V2_ENABLED: what happened, in the rep's own flow, and how it compares."""
    missed = list(missed or [])
    extra = {
        "flow": flow,
        "missed": [{"id": item.get("id"), "kind": item.get("kind"), "label": item.get("label")} for item in missed if item.get("label")],
        "phrases": build_phrases(missed),
        "highlights": build_highlights(evidence or []),
        "progress": list(progress or []),
    }
    if flow == "sdr":
        extra["meeting_booked"] = meeting_agreed
    elif flow == "ae":
        extra["next_step_agreed"] = next_step_agreed
    return {**brief, **extra}


def build_phrases(missed: list[dict], *, limit: int = 3) -> list[str]:
    """The playbook's own words (`entries.guidance`) for each failed step or objection, no repeats."""
    phrases: list[str] = []
    for item in missed:
        text = str((item or {}).get("guidance") or "").strip()
        if text and text not in phrases:
            phrases.append(text)
        if len(phrases) >= limit:
            break
    return phrases


def _format_highlight(item: dict) -> str | None:
    start_ms = item.get("start_ms")
    if start_ms is None:
        return None
    quote = str(item.get("label") or item.get("quote") or "").strip()
    if not quote:
        return None
    minutes, seconds = divmod(max(0, int(start_ms)) // 1000, 60)
    return f"min {minutes:02d}:{seconds:02d} · {quote}"


def build_highlights(evidence: list[dict], *, limit: int = 5) -> list[str]:
    """Evidence with a timestamp, earliest first. Evidence without start_ms is not a highlight."""
    dated = [item for item in evidence if isinstance(item, dict) and item.get("start_ms") is not None]
    dated.sort(key=lambda item: int(item["start_ms"]))
    lines = [line for line in (_format_highlight(item) for item in dated) if line]
    return lines[:limit]


def label_missed_items(missed: list[dict], *, steps: list[dict], entries: list[dict]) -> list[dict]:
    """Attach the playbook's own label to a missed step or objection, and a separate phrase
    when the playbook has one to say. `label` names what was missed; `guidance` (when present)
    is the playbook's own words on it — never the same text twice. A category matches its
    entry case-insensitively. An id the playbook does not recognise anymore is dropped."""
    step_labels = {str(step.get("step_id")): step for step in steps if isinstance(step, dict)}
    entry_guidance: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip().lower()
        if category and category not in entry_guidance:
            entry_guidance[category] = str(entry.get("guidance") or "").strip()
    labeled: list[dict] = []
    for item in missed:
        kind = item.get("kind")
        item_id = str(item.get("id") or "")
        guidance = ""
        if kind == "step":
            step = step_labels.get(item_id)
            if step is None:
                continue
            label = str(step.get("label") or "").strip()
            guidance = str(step.get("criterion") or "").strip()
        else:
            label = str(item.get("category") or "").strip()
            category = label.lower()
            if category not in entry_guidance:
                continue
            guidance = entry_guidance[category]
        if not label:
            continue
        entry_out = {"id": item_id, "kind": kind, "label": label}
        if guidance and guidance != label:
            entry_out["guidance"] = guidance
        labeled.append(entry_out)
    return labeled


def _aggregate_brief_v1(
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
        if score.get("reason") == "insufficient_evidence" and sections:
            return _evidence_backed_coaching(
                {**base, "status": "ready", "reason": None, "strength": None, "improvement": None},
            )
        return _evidence_backed_coaching({**base, "status": "partial", "reason": score.get("reason") or "score_pending"})
    return _evidence_backed_coaching({**base, "status": "ready", "reason": None})


def _evidence_backed_coaching(brief: dict) -> dict:
    """An improvement is only shown when objection evidence exists for this revision."""
    sections = brief.get("sections") or []
    has_evidence = any(section.get("evidence_refs") for section in sections)
    if brief.get("improvement") and not has_evidence:
        return {**brief, "improvement": None}
    return brief


def _sections(patterns: list[dict], input_revision: str) -> list[dict]:
    sections: list[dict] = []
    seen_categories: set[str] = set()
    legacy_refs: list[str] = []
    for pattern in patterns:
        if pattern.get("input_revision") != input_revision or pattern.get("superseded"):
            continue
        kind = pattern.get("kind")
        if kind not in (None, "objection"):
            continue
        refs = [ref for ref in (pattern.get("evidence_refs") or []) if ref]
        if not refs:
            continue
        category = str(pattern.get("category") or "").strip()
        if not category:
            for ref in refs:
                if ref not in legacy_refs:
                    legacy_refs.append(ref)
            continue
        if category in seen_categories:
            continue
        seen_categories.add(category)
        sections.append({
            "kind": "objections",
            "category": category,
            "evidence_refs": refs[:3],
        })
        if len(sections) >= 3:
            break
    if legacy_refs and len(sections) < 3:
        sections.append({"kind": "objections", "evidence_refs": legacy_refs[:3]})
    return sections


def _coaching(score: dict | None, input_revision: str) -> dict:
    if not score or score.get("input_revision") != input_revision:
        return {"strength": None, "improvement": None}
    strengths = [item for item in (score.get("strengths") or []) if item]
    improvements = [item for item in (score.get("improvements") or []) if item]
    return {
        "strength": strengths[0] if strengths else None,
        "improvement": improvements[0] if improvements else None,
    }


def materialize_brief(
    *,
    screening: str | None,
    score: dict | None,
    patterns: list[dict],
    playbook_present: bool,
    job_error: bool,
    input_revision: str,
    audio_available: bool,
    debrief_v2: bool = False,
    flow: str | None = None,
    missed: list[dict] | None = None,
    evidence: list[dict] | None = None,
    progress: list[float | None] | None = None,
    meeting_agreed: bool | None = None,
    next_step_agreed: bool | None = None,
) -> dict:
    """Aggregate coaching sources into a persisted brief row (status + JSON body)."""
    aggregated = aggregate_brief(
        screening=screening,
        score=score,
        patterns=patterns,
        playbook_present=playbook_present,
        job_error=job_error,
        input_revision=input_revision,
        audio_available=audio_available,
        debrief_v2=debrief_v2,
        flow=flow,
        missed=missed,
        evidence=evidence,
        progress=progress,
        meeting_agreed=meeting_agreed,
        next_step_agreed=next_step_agreed,
    )
    status = aggregated["status"]
    body = {key: value for key, value in aggregated.items() if key != "status"}
    return {"status": status, "input_revision": input_revision, "body": body}


def _fetch_playbook_snapshot(supabase, playbook_version_id: str | None) -> tuple[list[dict], list[dict]]:
    """Best-effort read of one *published* version's steps/entries, for labeling missed items.
    A draft never backs a phrase: the rep sees only what the team actually published."""
    if not playbook_version_id:
        return [], []
    try:
        result = (
            supabase.table("playbook_versions")
            .select("id,status,steps,entries")
            .eq("id", playbook_version_id)
            .eq("status", "published")
            .limit(1)
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
    except Exception:
        return [], []
    if not rows:
        return [], []
    row = rows[0]
    return list(row.get("steps") or []), list(row.get("entries") or [])


def recent_progress(
    supabase,
    *,
    user_id: str | None,
    company_id: str | None,
    sales_motion_key: str | None,
    exclude_memo_id: str | None = None,
    limit: int = 5,
) -> list[float | None]:
    """Adherence of the rep's last `limit` interactions in the same flow, most recent first.
    Scoped to the rep's own company so a stray cross-company user_id never leaks in. A failed
    lookup is an empty trend, not a broken brief."""
    if not user_id or not company_id or not sales_motion_key:
        return []
    try:
        memo_rows = (
            supabase.table("memos")
            .select("id,created_at")
            .eq("user_id", user_id)
            .eq("company_id", company_id)
            .eq("sales_motion_key", sales_motion_key)
            .order("created_at", desc=True)
            .limit(limit + 1)
            .execute()
        )
        memos = list(getattr(memo_rows, "data", None) or [])
    except Exception:
        return []
    memo_ids = [str(row["id"]) for row in memos if row.get("id") and str(row["id"]) != str(exclude_memo_id)][:limit]
    if not memo_ids:
        return []
    try:
        score_rows = (
            supabase.table("memo_scores")
            .select("memo_id,revision_seq,score")
            .in_("memo_id", memo_ids)
            .execute()
        )
        rows = list(getattr(score_rows, "data", None) or [])
    except Exception:
        return []
    latest: dict[str, dict] = {}
    for row in rows:
        memo_id = str(row.get("memo_id"))
        current = latest.get(memo_id)
        if current is None or int(row.get("revision_seq") or 0) >= int(current.get("revision_seq") or 0):
            latest[memo_id] = row
    values: list[float | None] = []
    for memo_id in memo_ids:
        row = latest.get(memo_id)
        score = row.get("score") if row and isinstance(row.get("score"), dict) else None
        values.append(score.get("adherence") if score else None)
    return values


def debrief_v2_context(
    supabase,
    *,
    memo: dict,
    intelligence: dict | None,
    score: dict | None,
    memo_id: str,
) -> dict:
    """Best-effort inputs for T10's richer post-interaction brief. A failed lookup leaves that
    part empty; it never blocks the score/brief persist that already happened."""
    from app.services.playbooks.motion import flow_for_motion

    intelligence = intelligence if isinstance(intelligence, dict) else {}
    score = score if isinstance(score, dict) else {}
    flow = flow_for_motion(memo.get("sales_motion_key"))
    steps, entries = _fetch_playbook_snapshot(supabase, score.get("playbook_version_id"))
    missed = label_missed_items(list(score.get("missed_items") or []), steps=steps, entries=entries)
    evidence = list(intelligence.get("evidence") or [])
    meeting = intelligence.get("meeting") if isinstance(intelligence.get("meeting"), dict) else {}
    commitments = intelligence.get("commitments")
    progress = recent_progress(
        supabase,
        user_id=memo.get("user_id"),
        company_id=memo.get("company_id"),
        sales_motion_key=memo.get("sales_motion_key"),
        exclude_memo_id=memo_id,
    )
    return {
        "flow": flow,
        "missed": missed,
        "evidence": evidence,
        "progress": progress,
        "meeting_agreed": meeting.get("agreed"),
        "next_step_agreed": bool(commitments) if commitments is not None else None,
    }
