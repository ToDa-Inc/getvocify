"""Team reads. A member is rejected before any number is returned."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.deps import get_membership, get_supabase
from app.services.activity_scope import effective_visibility
from app.services.company import Membership
from app.services.feature_flags import is_enabled
from app.services.team_insights.adherence_trend import DEFAULT_WEEKS, FLAG as TREND_FLAG, adherence_trend
from app.services.coaching.best import FLAG as PLAYBOOK_TAB_FLAG
from app.services.team_insights.competitors import COMPETITORS_FLAG
from app.services.team_insights.aggregate import (
    _TEAM_ROLES,
    TeamAccessError,
    assert_team_reader,
    load_team_adherence_inputs,
    team_adherence,
)
from app.services.team_insights.period import period_windows
from app.services.team_insights.rep_detail import name_handoff_contacts, rep_handoffs, rep_in_company, rep_name, rep_sales_role

router = APIRouter(prefix="/api/v1/team", tags=["team"])

# T13: /dashboard becomes the Head of Sales' team home, with a per-rep detail page.
MANAGER_HOME_FLAG = "MANAGER_HOME_ENABLED"
HANDOFF_FLAG = "HANDOFF_ENABLED"

_LOADER = None


def set_team_adherence_loader(loader) -> None:
    """loader(supabase, company_id, user_id, motion) -> kwargs for team_adherence."""
    global _LOADER
    _LOADER = loader


def _trend_now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/adherence")
async def get_team_adherence(
    user_id: Optional[str] = Query(None),
    motion: Optional[str] = Query(None),
    # Head of Sales phase 2. Without period the response is exactly the pre-phase-2 week.
    period: Optional[Literal["week", "month", "last_30", "quarter"]] = Query(None),
    sales_role: Optional[Literal["sdr", "ae"]] = Query(None),
    # Coaching focus per rep: only the Head of Sales Equipo page asks for it.
    with_focus: bool = Query(False),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    visibility = effective_visibility(supabase, membership)
    # 403 before any heavy read.
    try:
        assert_team_reader(membership.role, visibility)
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    # A member reading the team (visibility=team) gets exactly the pre-phase-2 body:
    # period, sales_role and with_focus are for managers.
    is_manager = membership.role in _TEAM_ROLES
    if not is_manager:
        period, sales_role, with_focus = None, None, False
    windows = period_windows(period, now=_trend_now()) if period else None
    try:
        if _LOADER is not None:
            inputs = _LOADER(supabase, membership.company_id, user_id, motion)
            if windows is not None:
                current, previous = windows
                inputs = {
                    **inputs,
                    "activity_period_start": current.start,
                    "activity_period_end": current.end,
                    "previous_period_start": previous.start,
                    "previous_period_end": previous.end,
                }
        else:
            inputs = load_team_adherence_inputs(
                supabase,
                membership.company_id,
                user_id=user_id,
                motion=motion,
                period=windows,
                sales_role=sales_role,
                with_focus=with_focus,
            )
        # T11: how_to/best_example only when the Playbook tab is on for this company —
        # off keeps the objection_categories items in the pre-T11 shape.
        include_guidance = is_enabled(supabase, membership.company_id, PLAYBOOK_TAB_FLAG)
        body = team_adherence(
            role=membership.role,
            visibility=visibility,
            include_objection_guidance=include_guidance,
            **inputs,
        )
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    if not is_enabled(supabase, membership.company_id, COMPETITORS_FLAG):
        body.pop("competitor_mentions", None)
    return JSONResponse(body)


@router.get("/adherence/trend")
async def get_team_adherence_trend(
    weeks: int = Query(DEFAULT_WEEKS),
    user_id: Optional[str] = Query(None),
    motion: Optional[str] = Query(None),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    # Off means the route does not exist for this company: same body as an unknown path.
    if not is_enabled(supabase, membership.company_id, TREND_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    try:
        body = adherence_trend(
            supabase,
            membership.company_id,
            role=membership.role,
            weeks=weeks,
            now=_trend_now(),
            user_id=user_id,
            motion=motion,
            visibility=effective_visibility(supabase, membership),
        )
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    return JSONResponse(body)


@router.get("/rep/{user_id}")
async def get_team_rep_detail(
    user_id: str,
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """T13: what the per-rep detail page needs beyond /team/adherence?user_id= and
    /team/adherence/trend?user_id= (both already generic) - the rep's own sales_role and
    its handoffs, SDR past / AE received."""
    # Owner/admin do not need the flag; a member with visibility=team still does.
    if membership.role not in _TEAM_ROLES and not is_enabled(supabase, membership.company_id, MANAGER_HOME_FLAG):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    try:
        assert_team_reader(membership.role, effective_visibility(supabase, membership))
    except TeamAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo") from error
    if not rep_in_company(supabase, company_id=membership.company_id, user_id=user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    sales_role = rep_sales_role(supabase, company_id=membership.company_id, user_id=user_id)
    handoffs = None
    if is_enabled(supabase, membership.company_id, HANDOFF_FLAG):
        handoffs = rep_handoffs(supabase, company_id=membership.company_id, user_id=user_id)
        handoffs = name_handoff_contacts(supabase, company_id=membership.company_id, handoffs=handoffs)
    return JSONResponse({
        "user_id": user_id,
        "name": rep_name(supabase, company_id=membership.company_id, user_id=user_id),
        "sales_role": sales_role,
        "handoffs": handoffs,
    })


_COACHING_MARGIN = timedelta(days=1)


@router.get("/coaching")
async def get_team_coaching(
    period: Literal["week", "month", "last_30", "quarter"] = Query("month"),
    sales_role: Optional[Literal["sdr", "ae"]] = Query(None),
    type_key: Optional[str] = Query(None, alias="type", max_length=64),
    membership: Membership = Depends(get_membership),
    supabase=Depends(get_supabase),
):
    """Equipo for the Head of Sales, one interaction type at a time (team_coaching): do they follow
    the playbook, does it work, and why we lose. Owner/admin only, before any read."""
    if membership.role not in _TEAM_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puedes ver el equipo")
    from app.services.coaching import rep_coaching as engine
    from app.services.coaching import rep_coaching_reads as reads
    from app.services.coaching.crm_meetings import crm_lost_calls
    from app.services.playbooks.catalog import INTERNAL_KEY
    from app.services.team_insights import team_coaching as answers
    from app.services.team_insights.aggregate import load_team_reps, reps_for_sales_role

    current, previous = period_windows(period, now=_trend_now())
    reps = reps_for_sales_role(load_team_reps(supabase, membership.company_id, exclude_managers=True), sales_role)
    body: dict = {
        "period": period,
        "types": [],
        "type": None,
        "goal": "meeting_booked",
        "follow": {"adherence": None, "prev_adherence": None, "conversations": 0, "steps": [], "reps": []},
        "works": {"process": None, "steps": []},
        "losses": {"total": 0, "by_source": {"not_interested": 0, "disqualified": 0, "crm_lost": 0}, "causes": []},
    }
    if not reps:
        return body
    names = {str(rep["userId"]): rep.get("name") or "" for rep in reps}
    memos = [
        memo for memo in reads.load_memos(
            supabase, membership.company_id, list(names), start=previous.start - _COACHING_MARGIN
        )
        if memo.get("sales_motion_key") and memo.get("sales_motion_key") != INTERNAL_KEY
    ]

    def in_window(instant, window) -> bool:
        return instant is not None and window.start <= instant < window.end

    rows = [row for row in (engine.interaction_row(memo) for memo in memos) if row is not None]
    now_rows = [row for row in rows if in_window(engine.parse_instant(row["observed_at"]), current)]
    playbooks: dict[str, dict] = {}

    def playbook_for(motion: str) -> dict:
        if motion not in playbooks:
            playbooks[motion] = reads.load_published_playbook(supabase, membership.company_id, motion)
        return playbooks[motion]

    counts: dict[str, int] = {}
    for row in now_rows:
        if row["is_conversation"]:
            counts[row["motion"]] = counts.get(row["motion"], 0) + 1
    types = [motion for motion in sorted(counts, key=lambda m: (-counts[m], m)) if playbook_for(motion)["published"]]
    labels = {}
    if types:
        try:
            from app.services.playbooks.repository import get_playbook_repository

            labels = {
                key: str(row.get("label"))
                for key, row in get_playbook_repository().list_types(membership.company_id, include_draft=False).items()
                if row.get("label")
            }
        except Exception:
            labels = {}
    chosen = type_key if type_key in types else (types[0] if types else None)
    body["types"] = [{"key": motion, "label": labels.get(motion), "conversations": counts[motion]} for motion in types]
    body["type"] = chosen
    if chosen is None:
        return body
    playbook = playbook_for(chosen)
    steps = playbook["steps"]
    own = [row for row in now_rows if row["motion"] == chosen]
    before = [
        row for row in rows
        if row["motion"] == chosen and in_window(engine.parse_instant(row["observed_at"]), previous)
    ]
    by_user: dict[str, list[dict]] = {}
    for row in own:
        by_user.setdefault(row["user_id"], []).append(row)
    team = answers.adherence_of(own)
    body["follow"] = {
        **team,
        "prev_adherence": answers.adherence_of(before)["adherence"],
        "steps": [
            {key: rate[key] for key in ("step_id", "label", "done", "applicable", "rate")}
            for rate in engine.step_rates(own, steps)
        ],
        "reps": [rep for rep in answers.rep_matrix(by_user, reps, steps) if rep["conversations"]],
    }
    body["works"] = {"process": answers.process_effect(own), "steps": answers.step_effects(own, steps)}
    # Why we lose: every call of the type in the period (voicemails too: seven no-answers is a cause).
    signals = [
        signal for signal in (answers.call_signals(memo) for memo in memos)
        if signal is not None and signal["motion"] == chosen and in_window(signal["observed_at"], current)
    ]
    history = [signal for signal in (answers.call_signals(memo) for memo in memos) if signal is not None]
    lost_ids = set(crm_lost_calls(supabase, membership.company_id, memos))
    custom_labels = {
        f"custom:{str(entry.get('entry_id'))[len('objection:custom:'):]}": " ".join(str(entry.get("label") or "").split())
        for entry in playbook["entries"]
        if entry.get("category") == "custom" and str(entry.get("entry_id") or "").startswith("objection:custom:")
    }
    body["losses"] = answers.losses(signals, lost_ids, custom_labels, names, history=history)
    return body
