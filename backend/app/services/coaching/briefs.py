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
    coach: dict | None = None,
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
        coach=coach,
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
    coach: dict | None = None,
) -> dict:
    """T10/DEBRIEF_V2_ENABLED: what happened, in the rep's own flow, and how it compares."""
    missed = list(missed or [])
    extra = {
        "flow": flow,
        "missed": [{"id": item.get("id"), "kind": item.get("kind"), "label": item.get("label")} for item in missed if item.get("label")],
        "phrases": build_phrases(missed),
        "highlights": build_highlights(evidence or []),
        "progress": list(progress or []),
        # One thing kept, one thing to change: only for a conversation measured against a playbook.
        "coach": coach if brief.get("status") in {"ready", "partial"} and _coach_has_content(coach) else None,
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
    when the playbook has one to say (a step's `example`, an objection's answer). `label`
    names what was missed; `guidance` (when present) is the playbook's own words to say —
    never the same text twice. A category matches its
    entry case-insensitively. An id the playbook does not recognise anymore is dropped."""
    step_labels = {str(step.get("step_id")): step for step in steps if isinstance(step, dict)}
    entry_guidance: dict[str, str] = {}
    custom_entries: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("entry_id") or "").startswith("objection:custom:"):
            custom_entries.setdefault(str(entry["entry_id"]), entry)
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
            # What to say is the step's literal phrase. The criterion is how it is judged,
            # not something to say out loud.
            guidance = str(step.get("example") or "").strip()
        elif kind == "qualification":
            # C04 v7: a criterion that never came out of the call. It carries its own label.
            label = str(item.get("label") or "").strip()
        elif item.get("objection_id") and f"objection:custom:{item['objection_id']}" in custom_entries:
            custom = custom_entries[f"objection:custom:{item['objection_id']}"]
            label = str(custom.get("label") or item.get("category") or "").strip()
            guidance = str(custom.get("guidance") or "").strip()
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


def _coach_has_content(coach: dict | None) -> bool:
    return bool(coach and (coach.get("kept") or coach.get("fix")))


def build_coach(
    *,
    observations: list[dict],
    evidence_ids: list[str],
    steps: list[dict],
    entries: list[dict],
    missed: list[dict],
    focus_step_id: str | None = None,
) -> dict:
    """One step kept and one thing to change, in the playbook's own words.

    kept: the week's focus step when the rep did it (progress worth naming), else the first
    step done, with the rep's own quote. fix: the focus step when missed, else the first missed
    step in playbook order, else an objection the playbook answers that stayed open. `say` is
    the playbook's phrase for it (a step's example, an objection's answer), never the criterion.
    Only cited observations count, so nothing here rests on a quote that is not in the call."""
    known = set(evidence_ids)
    step_by_id = {str(step.get("step_id")): step for step in steps if isinstance(step, dict)}
    cited = [
        obs for obs in observations
        if isinstance(obs, dict)
        and obs.get("status") in {"met", "missed"}
        and any(ref in known for ref in (obs.get("evidence_refs") or []))
    ]
    focus = str(focus_step_id or "") or None

    def label_of(obs: dict) -> str:
        step = step_by_id.get(str(obs.get("step_id"))) or {}
        return " ".join(str(step.get("label") or obs.get("label") or "").split())

    met = [obs for obs in cited if obs.get("status") == "met" and label_of(obs)]
    kept_obs = next((obs for obs in met if str(obs.get("step_id")) == focus), met[0] if met else None)
    kept = None
    if kept_obs is not None:
        quote = " ".join(str(kept_obs.get("quote") or "").split()) or None
        kept = {"step_id": str(kept_obs.get("step_id")), "label": label_of(kept_obs), "quote": quote}

    fix = None
    missed_steps = [obs for obs in cited if obs.get("status") == "missed" and label_of(obs)]
    missed_steps.sort(key=lambda obs: str(obs.get("step_id")) != focus)  # stable: playbook order otherwise
    if missed_steps:
        obs = missed_steps[0]
        step = step_by_id.get(str(obs.get("step_id"))) or {}
        criterion = " ".join(str(step.get("criterion") or obs.get("criterion") or "").split())
        label = label_of(obs)
        fix = {
            "kind": "step",
            "id": str(obs.get("step_id")),
            "label": label,
            "criterion": criterion if criterion and criterion != label else None,
            "say": " ".join(str(step.get("example") or "").split()) or None,
            "focus": str(obs.get("step_id")) == focus,
        }
    else:
        answers = {
            str(entry.get("category") or "").strip().lower(): " ".join(str(entry.get("guidance") or "").split())
            for entry in entries
            if isinstance(entry, dict)
        }
        for item in missed:
            if item.get("kind") != "objection":
                continue
            category = str(item.get("category") or item.get("label") or "").strip().lower()
            if answers.get(category):
                fix = {
                    "kind": "objection",
                    "id": str(item.get("id") or ""),
                    "label": category,
                    "category": category,
                    "criterion": None,
                    "say": answers[category],
                    "focus": False,
                }
                break
    return {"kept": kept, "fix": fix}


def next_step_agreed(meeting: dict | None, commitments: list[dict] | None) -> bool | None:
    """AE outcome: a meeting both sides accepted, or a dated call or meeting to talk again.
    "I'll send you the deck" is a commitment, not a next step. None when nothing was read."""
    meeting = meeting if isinstance(meeting, dict) else {}
    if meeting.get("agreed") is True:
        return True
    if commitments is None:
        return None if meeting.get("agreed") is None else False
    for item in commitments:
        if isinstance(item, dict) and item.get("kind") in {"call", "meeting"} and item.get("due_at"):
            return True
    return False


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
    cited_improvement = bool(score and score.get("input_revision") == input_revision and score.get("improvements_cited"))
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
                cited=cited_improvement,
            )
        return _evidence_backed_coaching(
            {**base, "status": "partial", "reason": score.get("reason") or "score_pending"}, cited=cited_improvement,
        )
    return _evidence_backed_coaching({**base, "status": "ready", "reason": None}, cited=cited_improvement)


def _evidence_backed_coaching(brief: dict, *, cited: bool = False) -> dict:
    """An improvement is only shown with evidence for this revision: objection sections, or
    (`cited`) the score's own lines, which come from step observations quoted in the transcript."""
    sections = brief.get("sections") or []
    has_evidence = cited or any(section.get("evidence_refs") for section in sections)
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
    coach: dict | None = None,
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
        coach=coach,
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
    raw_missed = list(score.get("missed_items") or [])
    missed = label_missed_items(raw_missed, steps=steps, entries=entries)
    evidence = list(intelligence.get("evidence") or [])
    meeting = intelligence.get("meeting") if isinstance(intelligence.get("meeting"), dict) else {}
    commitments = intelligence.get("commitments")
    coach = build_coach(
        observations=list(intelligence.get("playbook_observations") or []),
        evidence_ids=[str(item.get("id")) for item in evidence if isinstance(item, dict) and item.get("id")],
        steps=steps,
        entries=entries,
        missed=raw_missed,
        focus_step_id=weekly_focus_step(supabase, memo),
    )
    # This call's own adherence closes the trend, only when it earned a mark (enough steps judged).
    coach["adherence"] = score.get("adherence") if score.get("value") is not None else None
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
        "next_step_agreed": next_step_agreed(meeting, commitments if isinstance(commitments, list) else None),
        "coach": coach,
    }


def weekly_focus_step(supabase, memo: dict) -> str | None:
    """The step the rep is working on this week (Coach), when it belongs to this call's type.
    Best-effort: any failed read means no focus, never a broken brief."""
    user_id = memo.get("user_id")
    company_id = memo.get("company_id")
    motion = memo.get("sales_motion_key")
    if not user_id or not company_id or not motion:
        return None
    try:
        from datetime import datetime, timezone

        from app.services.coaching import rep_coaching_reads as reads
        from app.services.coaching.rep_focus import flow_window_start, previous_week_start, rep_focus, rows_of
        from app.services.company import sales_role_for_user
        from app.services.team_insights.aggregate import madrid_week_bounds

        week_start, _ = madrid_week_bounds(now=datetime.now(timezone.utc))
        rows = rows_of(reads.load_memos(supabase, str(company_id), [str(user_id)], start=flow_window_start(week_start)))
        found = rep_focus(
            rows,
            sales_role_for_user(supabase, str(user_id), company_id=str(company_id)),
            lambda key: reads.load_published_playbook(supabase, str(company_id), key),
            prev_start=previous_week_start(week_start),
            week_start=week_start,
        )
    except Exception:
        return None
    if not found or found.get("motion") != motion or not found.get("focus"):
        return None
    return str(found["focus"].get("step_id") or "") or None
