"""The brain tools read what the screens read (Today, Coaching, Head of Sales) and add nothing of their own."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.api import coaching as coaching_api, team_insights as team_api
from app.services.crm_copilot import brain_tools, intel_tools
from app.services.crm_copilot.actor import AskActor
from tests.crm_copilot.fakes import FakeCompanyService, FakeSupabase
from tests.crm_copilot.test_intel_tools import ANALYSED, _iso, _memo

PLAYBOOK = dict(
    playbooks=[{"id": "p1", "company_id": "co", "sales_motion_key": "discovery", "active_version_id": "v1"}],
    playbook_versions=[{
        "id": "v1", "playbook_id": "p1", "status": "published", "steps": [{"step_id": "s1", "label": "Confirmar problema"}],
        "entries": [{"entry_id": "e1", "category": "price", "approved_answer": "Pregunta por el coste actual antes de dar precio."}],
    }],
)


def _ctx(db, role="member", user="u1", members=("u1", "u2"), **actor):
    a = AskActor(user_id=user, company_id="co", role=role, timezone="UTC", locale="es", **actor)
    return SimpleNamespace(supabase=db, actor=a, company=FakeCompanyService(list(members)), hs=None, user_id=user, artifacts={})


async def run(name, args, ctx):
    return await intel_tools.execute_intel_tool(name, args, ctx)


def _promised(due_days=1, **extra):
    block = dict(ANALYSED)
    block["intelligence"] = {**ANALYSED["intelligence"], "commitments": [{"kind": "send", "origin": "rep_promise", "text": "enviar el caso", "due_at": _iso(due_days), "evidence_refs": ["ev-2"]}], **extra}
    return block


# ----- next_actions ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_promise_that_came_due_says_what_to_do_by_when_and_cites_the_quote():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **_promised(due_days=1))])
    out = await run("next_actions", {}, _ctx(db))
    item = out["items"][0]
    assert item["contact"] == "Marina López (Acme)" and item["type"] == "commitment_due"
    assert item["suggested"]["do"] == "keep_promise" and item["suggested"]["what"] == "enviar el caso"
    assert item["suggested"]["overdue"] is True and item["due"]
    assert item["why"] and item["evidence"] == "ev-2"
    assert "ev-2" in {e["id"] for e in out["evidence"]}


@pytest.mark.asyncio
async def test_an_open_objection_carries_the_companys_approved_answer_as_a_citable_source():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **_promised(due_days=1))], **PLAYBOOK)
    out = await run("next_actions", {}, _ctx(db))
    also = out["items"][0]["also"]
    assert also[0]["type"] == "objection_open"
    assert also[0]["suggested"]["playbook"]["answer"].startswith("Pregunta por el coste")
    assert {"pb-e1", "ev-1"} <= {e["id"] for e in out["evidence"]}
    assert out["playbook_published"] is True


@pytest.mark.asyncio
async def test_without_a_published_playbook_no_answer_is_invented():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **_promised(due_days=1))])
    out = await run("next_actions", {}, _ctx(db))
    assert out["items"][0]["also"][0]["suggested"]["playbook"] is None
    assert out["playbook_published"] is None


@pytest.mark.asyncio
async def test_a_card_dismissed_on_today_stays_hidden_and_a_stored_one_is_not_repeated():
    memo = _memo("m1", "u1", "c1", 3, **_promised(due_days=1))
    key = f"commitment:m1:send:{(datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()}"
    stored = {"company_id": "co", "user_id": "u1", "contact_id": "c1", "memo_id": "m1", "type": "commitment_due", "dedupe_key": key,
              "payload": {"kind": "send", "origin": "rep_promise", "text": "enviar el caso", "due_at": _iso(1)}, "status": "pending"}
    shown = await run("next_actions", {}, _ctx(FakeSupabase(memos=[memo], action_signals=[stored])))
    assert shown["counts"]["commitment_due"] == 1
    hidden = await run("next_actions", {}, _ctx(FakeSupabase(memos=[memo], action_signals=[{**stored, "status": "dismissed"}])))
    assert "commitment_due" not in hidden["counts"]


@pytest.mark.asyncio
async def test_open_obstacles_are_listed_apart_from_next_actions():
    out = await run("next_actions", {}, _ctx(FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **ANALYSED)])))
    assert [o["category"] for o in out["obstacles"]] == ["bad_moment"]


@pytest.mark.asyncio
async def test_the_team_view_is_by_rep_alphabetical_and_never_speaks_as_the_manager():
    rows = [_memo("m1", "u2", "c1", 3, **_promised(due_days=1)), _memo("m2", "u1", "c2", 3, **_promised(due_days=1))]
    out = await run("next_actions", {}, _ctx(FakeSupabase(memos=rows), role="admin", user="u9", members=("u1", "u2")))
    assert [i["rep"] for i in out["items"]] == ["Rep u1", "Rep u2"]
    assert all("why" not in i for i in out["items"])


@pytest.mark.asyncio
async def test_a_member_cannot_read_a_teammates_next_actions():
    out = await run("next_actions", {"user_id": "u2"}, _ctx(FakeSupabase(memos=[])))
    assert out["coverage"] == "forbidden"


# ----- my_coaching -----------------------------------------------------------------------------

SUMMARY = {
    "flow": "sdr", "week_start": "2026-09-28", "playbook_published": True,
    "numbers": {"conversations": 12, "meetings_agreed": 3, "process_complete": 5, "interactions": 20},
    "prev_numbers": {"conversations": 10, "meetings_agreed": 2, "process_complete": 4, "interactions": 18},
    "steps": [{"step_id": "s1", "label": "Confirmar problema", "rate": 0.4, "prev_rate": 0.5, "peer_median": 0.7}],
    "focus": {
        "step_id": "s1", "label": "Confirmar problema", "criterion": "Nombra el problema con sus palabras", "example": None,
        "why": {"rate": 0.25, "applicable": 8, "missing": 6, "peer_median": 0.7},
        "week_total": {"done": 2, "applicable": 5, "rate": 0.4}, "achieved": False, "progress": [],
    },
    "conversion": {"complete_rate": 0.5, "incomplete_rate": 0.2, "complete_n": 6, "incomplete_n": 9},
}


@pytest.mark.asyncio
async def test_my_coaching_hands_over_the_coaching_engines_focus_with_percentages(monkeypatch):
    async def fake(flow, membership, supabase):
        assert membership.user_id == "u1" and membership.role == "member"
        return SUMMARY

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", fake)
    out = await run("my_coaching", {}, _ctx(FakeSupabase(memos=[])))
    assert out["focus"]["step"] == "Confirmar problema" and out["focus"]["last_week_pct"] == 25.0
    assert (out["focus"]["conversations"], out["focus"]["missed_in"]) == (8, 6)
    assert out["steps"][0] == {"step": "Confirmar problema", "rate_pct": 40.0, "last_week_pct": 50.0, "team_median_pct": 70.0}
    assert out["conversion"]["meeting_rate_full_process_pct"] == 50.0 and out["coverage"] == "complete"


@pytest.mark.asyncio
async def test_my_coaching_keeps_unknown_unknown(monkeypatch):
    thin = {**SUMMARY, "steps": [{"step_id": "s1", "label": "Confirmar problema", "rate": None, "prev_rate": None, "peer_median": None}], "focus": None, "conversion": None}

    async def fake(flow, membership, supabase):
        return thin

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", fake)
    out = await run("my_coaching", {}, _ctx(FakeSupabase(memos=[])))
    assert out["steps"][0]["rate_pct"] is None and out["focus"] is None and "conversion" not in out


@pytest.mark.asyncio
async def test_my_coaching_says_when_there_is_no_published_playbook(monkeypatch):
    async def fake(flow, membership, supabase):
        return {**SUMMARY, "playbook_published": False, "steps": [], "focus": None, "conversion": None}

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", fake)
    out = await run("my_coaching", {}, _ctx(FakeSupabase(memos=[])))
    assert out["note"] == "no_published_playbook" and out["coverage"] == "partial" and "steps" not in out


@pytest.mark.asyncio
async def test_my_coaching_failures_are_named_not_swallowed(monkeypatch):
    async def missing(flow, membership, supabase):
        raise HTTPException(status_code=404, detail="Sin playbook")

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", missing)
    out = await run("my_coaching", {}, _ctx(FakeSupabase(memos=[])))
    assert out["ok"] is False and out["coverage"] == "unavailable"

    async def broken(flow, membership, supabase):
        raise RuntimeError("db down")

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", broken)
    assert (await run("my_coaching", {}, _ctx(FakeSupabase(memos=[]))))["error"] == "coaching_unavailable"


# ----- team_health -----------------------------------------------------------------------------

TEAM = {
    "adherence": 0.62, "met_steps": 31, "applicable_steps": 50, "sample_limited": False, "attempts": 80, "connected": 20, "meetings": 5,
    "period": {"start": "2026-08-30T00:00:00+00:00", "end": "2026-09-29T00:00:00+00:00"},
    "previous": {"adherence": 0.5, "attempts": 60, "connected": 15, "meetings": 3},
    "process_health": [{"motion": "discovery", "goal": "meeting", "verdict": "coach_reps", "scored": 40, "follow_share": 0.4, "follows_goal_rate": 0.5, "deviates_goal_rate": 0.2, "needed": 0}],
    "reps": [
        {"userId": "u2", "name": "Zoe", "salesRole": "sdr", "activity": {"attempts": 40, "connected": 10, "meetings": 3}, "coaching_focus": {"label": "Confirmar problema", "rate": 0.25}, "flows": {"sdr": 0.5, "ae": None}},
        {"userId": "u1", "name": "Abel", "salesRole": "sdr", "activity": {"attempts": 40, "connected": 10, "meetings": 2}, "coaching_focus": None, "flows": {"sdr": 0.7, "ae": None}},
    ],
    "objection_categories": [{"name": "price", "count": 5, "open": 2, "resolved": 3, "unknown": 0}],
}


@pytest.mark.asyncio
async def test_team_health_separates_people_from_process_and_never_ranks(monkeypatch):
    async def fake(**kwargs):
        assert kwargs["with_focus"] is True and kwargs["membership"].role == "admin"
        return JSONResponse(TEAM)

    monkeypatch.setattr(team_api, "get_team_adherence", fake)
    out = await run("team_health", {"include": ["activity", "objections"]}, _ctx(FakeSupabase(memos=[]), role="admin"))
    assert out["adherence_pct"] == 62.0 and out["adherence_change_pts"] == 12.0
    assert out["activity"] == {"attempts": 80, "connected": 20, "meetings": 5} and out["activity_last_period"]["attempts"] == 60
    assert out["period"] == {"from": "2026-08-30", "to": "2026-09-28"}
    assert out["process"][0]["verdict"] == "coach_reps" and "coaching problem" in out["process"][0]["meaning"]
    assert [r["name"] for r in out["reps"]] == ["Abel", "Zoe"]
    assert out["reps"][1]["focus"] == {"step": "Confirmar problema", "rate_pct": 25.0}
    assert out["objections"][0]["open"] == 2


@pytest.mark.asyncio
async def test_team_health_is_for_team_readers_only(monkeypatch):
    out = await run("team_health", {}, _ctx(FakeSupabase(memos=[]), role="member"))
    assert out["coverage"] == "forbidden"

    async def denied(**kwargs):
        raise HTTPException(status_code=403, detail="No")

    monkeypatch.setattr(team_api, "get_team_adherence", denied)
    assert (await run("team_health", {}, _ctx(FakeSupabase(memos=[]), role="admin")))["coverage"] == "forbidden"


@pytest.mark.asyncio
async def test_team_health_without_scored_conversations_says_so(monkeypatch):
    async def fake(**kwargs):
        return JSONResponse({"adherence": None, "applicable_steps": 0, "met_steps": 0, "reps": [], "process_health": [], "objection_categories": []})

    monkeypatch.setattr(team_api, "get_team_adherence", fake)
    out = await run("team_health", {}, _ctx(FakeSupabase(memos=[]), role="admin"))
    assert out["adherence_pct"] is None and out["adherence_change_pts"] is None and out["coverage"] == "partial"
    assert out["note"] == "no_scored_conversations_or_no_published_playbook"


# ----- cards: what Ask draws under its answer ---------------------------------------------------


@pytest.mark.asyncio
async def test_my_coaching_leaves_the_coach_screens_own_numbers_for_the_answer_card(monkeypatch):
    async def fake(flow, membership, supabase):
        return SUMMARY

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", fake)
    ctx = _ctx(FakeSupabase(memos=[]))
    await run("my_coaching", {}, ctx)
    (card,) = ctx.cards
    assert card["kind"] == "coaching" and card["focus"] == SUMMARY["focus"] and card["steps"] == SUMMARY["steps"]


@pytest.mark.asyncio
async def test_no_coaching_card_without_a_published_playbook(monkeypatch):
    async def fake(flow, membership, supabase):
        return {**SUMMARY, "playbook_published": False, "steps": [], "focus": None, "conversion": None}

    monkeypatch.setattr(coaching_api, "get_my_coaching_summary", fake)
    ctx = _ctx(FakeSupabase(memos=[]))
    await run("my_coaching", {}, ctx)
    assert not getattr(ctx, "cards", None)


@pytest.mark.asyncio
async def test_team_health_card_keeps_raw_rates_reps_alphabetical_and_one_card_per_kind(monkeypatch):
    async def fake(**kwargs):
        return JSONResponse(TEAM)

    monkeypatch.setattr(team_api, "get_team_adherence", fake)
    ctx = _ctx(FakeSupabase(memos=[]), role="admin")
    await run("team_health", {}, ctx)
    await run("team_health", {"period": "week"}, ctx)
    (card,) = ctx.cards
    assert card["kind"] == "team" and card["period"] == "week" and (card["adherence"], card["previous"]) == (0.62, 0.5)
    assert card["process"][0]["verdict"] == "coach_reps" and card["process"][0]["follows_goal_rate"] == 0.5
    assert [r["name"] for r in card["reps"]] == ["Abel", "Zoe"]
    assert card["reps"][1] == {"user_id": "u2", "name": "Zoe", "focus": {"label": "Confirmar problema", "rate": 0.25}}


# ----- deal_story carries the approved answer ---------------------------------------------------


@pytest.mark.asyncio
async def test_deal_story_attaches_the_approved_answer_for_an_objection_still_open():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **ANALYSED)], **PLAYBOOK)
    out = await run("deal_story", {"contact_id": "c1"}, _ctx(db))
    assert out["approved_answers"] == [{"category": "price", "answer": "Pregunta por el coste actual antes de dar precio.", "evidence": "pb-e1"}]
    assert "pb-e1" in {e["id"] for e in out["evidence"]}


@pytest.mark.asyncio
async def test_deal_story_without_a_playbook_answer_adds_nothing():
    out = await run("deal_story", {"contact_id": "c1"}, _ctx(FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **ANALYSED)])))
    assert "approved_answers" not in out


@pytest.mark.asyncio
async def test_team_health_leaves_activity_and_objections_out_unless_asked(monkeypatch):
    async def fake(**kwargs):
        return JSONResponse(TEAM)

    monkeypatch.setattr(team_api, "get_team_adherence", fake)
    out = await run("team_health", {}, _ctx(FakeSupabase(memos=[]), role="admin"))
    assert "activity" not in out and "objections" not in out and out["reps"] and out["process"]
