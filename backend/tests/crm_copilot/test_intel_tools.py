"""Ask tools: envelopes with coverage and evidence, scoped by the server's role, one tool per question."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.crm_copilot import intel_tools, tools as copilot_tools
from app.services.crm_copilot.actor import AskActor
from app.services.hubspot.call_log import HUBSPOT_DISPOSITION_GUID as G
from app.services.hubspot.exceptions import HubSpotAuthError, HubSpotError, HubSpotRateLimitError, HubSpotValidationError
from app.services.hubspot.types import CRMSchema, HubSpotProperty, PropertyOption
from tests.crm_copilot.fakes import FakeCompanyService, FakeHubSpotClient, FakeSupabase

NOW = datetime.now(timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _memo(mid, user, contact, days_ago, screening=None, **extraction):
    return {
        "id": mid, "user_id": user, "company_id": "co", "status": "approved",
        "hubspot_contact_id": contact, "created_at": _iso(days_ago), "capture_started_at": _iso(days_ago),
        "interaction_kind": "call", "screening_outcome": screening, "extraction": extraction,
    }


ANALYSED = dict(
    summary="Marina quiere automatizar el seguimiento.",
    contactName="Marina López", companyName="Acme",
    painPoints=["Seguimiento manual"],
    competitors=["Gong"],
    intelligence={
        "interest": "high",
        "objections": [
            {"kind": "objection", "category": "price", "resolution": "open", "quote": "Nos parece caro", "response": "Te enseño el retorno", "evidence_refs": ["ev-1"], "response_evidence": "ev-3"},
            {"kind": "obstacle", "category": "bad_moment", "resolution": "open", "quote": "Ahora estoy conduciendo", "evidence_refs": ["ev-4"]},
        ],
        "commitments": [{"kind": "send", "origin": "rep_promise", "text": "enviar el caso", "due_at": _iso(-1), "evidence_refs": ["ev-2"]}],
        "meeting": {"agreed": True},
        "evidence": [
            {"id": "ev-1", "source_type": "transcript", "source_id": "m1", "quote": "Nos parece caro", "speaker_role": "prospect"},
            {"id": "ev-2", "source_type": "transcript", "source_id": "m1", "quote": "te lo envío mañana", "speaker_role": "rep"},
            {"id": "ev-3", "source_type": "transcript", "source_id": "m1", "quote": "Te enseño el retorno", "speaker_role": "rep"},
            {"id": "ev-4", "source_type": "transcript", "source_id": "m1", "quote": "Ahora estoy conduciendo", "speaker_role": "prospect"},
        ],
    },
)


def _ctx(db, role="member", user="u1", members=("u1", "u2"), hs=None):
    actor = AskActor(user_id=user, company_id="co", role=role, timezone="UTC")
    return SimpleNamespace(supabase=db, actor=actor, company=FakeCompanyService(list(members)), hs=hs, user_id=user, artifacts={})


async def run(name, args, ctx):
    return await intel_tools.execute_intel_tool(name, args, ctx)


# ----- deal_story ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_story_separates_objections_from_obstacles_and_carries_the_reps_reply():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **ANALYSED)])
    out = await run("deal_story", {"contact_id": "c1"}, _ctx(db))
    assert out["coverage"] == "complete" and out["n"] == 1 and out["n_analysed"] == 1
    touch = out["touches"][0]
    assert [o["category"] for o in touch["objections"]] == ["price"]
    assert [o["category"] for o in touch["obstacles"]] == ["bad_moment"]
    assert touch["objections"][0]["rep_response"] == "Te enseño el retorno"
    assert {e["id"] for e in out["evidence"]} == {"ev-1", "ev-2", "ev-3", "ev-4"}
    assert out["contact"] == "Marina López (Acme)"
    assert "rep" not in touch


@pytest.mark.asyncio
async def test_a_memo_without_intelligence_makes_coverage_partial():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **ANALYSED), _memo("m2", "u1", "c1", 5, summary="Llamada corta.")])
    out = await run("deal_story", {"contact_id": "c1"}, _ctx(db))
    assert out["n"] == 2 and out["n_analysed"] == 1 and out["coverage"] == "partial"


@pytest.mark.asyncio
async def test_no_memos_is_a_complete_empty_read_not_an_error():
    out = await run("deal_story", {"contact_id": "nobody"}, _ctx(FakeSupabase(memos=[])))
    assert out["coverage"] == "complete" and out["n"] == 0 and out["touches"] == []


@pytest.mark.asyncio
async def test_a_legacy_memo_objection_is_read_as_an_objection_not_dropped():
    legacy = _memo("m1", "u1", "c1", 2, summary="x", objections=["Es caro"])
    out = await run("deal_story", {"contact_id": "c1"}, _ctx(FakeSupabase(memos=[legacy])))
    assert out["touches"][0]["objections"][0]["quote"] == "Es caro"
    assert out["touches"][0]["obstacles"] == []


# ----- scope --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_member_never_reads_a_teammates_memos():
    db = FakeSupabase(memos=[_memo("m9", "u2", "c1", 3, **ANALYSED)])
    assert (await run("deal_story", {"contact_id": "c1"}, _ctx(db)))["n"] == 0
    denied = await run("find_interactions", {"user_id": "u2"}, _ctx(db))
    assert denied["ok"] is False and denied["coverage"] == "forbidden"


@pytest.mark.asyncio
async def test_an_admin_sees_the_team_and_the_rep_name():
    db = FakeSupabase(memos=[_memo("m9", "u2", "c1", 3, **ANALYSED)])
    out = await run("deal_story", {"contact_id": "c1"}, _ctx(db, role="admin"))
    assert out["n"] == 1 and out["touches"][0]["rep"] == "Rep u2"


def test_tool_lists_are_role_filtered_so_a_member_never_sees_team_tools():
    member = {t["function"]["name"] for t in intel_tools.intel_tools_for(AskActor("u", "co", "member"))}
    admin = {t["function"]["name"] for t in intel_tools.intel_tools_for(AskActor("u", "co", "admin"))}
    assert "team_health" not in member and "team_health" in admin
    assert {"deal_story", "objection_breakdown", "next_actions", "my_coaching", "crm_call_stats", "crm_lost_reasons", "playbook_lookup"} <= member


@pytest.mark.asyncio
async def test_a_member_calling_a_team_tool_directly_is_forbidden():
    out = await run("team_health", {}, _ctx(FakeSupabase(memos=[]), role="member"))
    assert out == {"ok": False, "error": "forbidden", "coverage": "forbidden"}


# ----- find / breakdown / loops / competitors / meetings -----------------------------------


@pytest.mark.asyncio
async def test_find_interactions_filters_by_kind_and_category():
    price = _memo("m1", "u1", "c1", 2, **ANALYSED)
    plain = _memo("m2", "u1", "c2", 2, summary="Sin nada.")
    db = FakeSupabase(memos=[price, plain])
    assert [i["memo_id"] for i in (await run("find_interactions", {"objection_category": "price"}, _ctx(db)))["items"]] == ["m1"]
    assert [i["memo_id"] for i in (await run("find_interactions", {"kind": "obstacle"}, _ctx(db)))["items"]] == ["m1"]
    assert (await run("find_interactions", {"objection_category": "trust"}, _ctx(db)))["items"] == []


@pytest.mark.asyncio
async def test_objection_breakdown_keeps_objections_and_obstacles_apart():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 1, **ANALYSED), _memo("m2", "u1", "c2", 1, summary="vieja")])
    out = await run("objection_breakdown", {"period_days": 30}, _ctx(db))
    assert out["objections"]["total"] == 1 and out["objections"]["by_category"][0]["category"] == "price"
    assert out["objections"]["open"] == 1
    assert out["obstacles"]["total"] == 1 and out["obstacles"]["by_category"][0]["category"] == "bad_moment"
    assert out["n"] == 2 and out["n_analysed"] == 1 and out["coverage"] == "partial"


@pytest.mark.asyncio
async def test_next_actions_lists_a_promise_that_came_due_with_the_contact_name():
    due = dict(ANALYSED)
    due["intelligence"] = {**ANALYSED["intelligence"], "commitments": [{"kind": "send", "origin": "rep_promise", "text": "enviar el caso", "due_at": _iso(1), "evidence_refs": []}]}
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **due)])
    out = await run("next_actions", {}, _ctx(db))
    assert out["counts"].get("commitment_due") == 1
    assert out["items"][0]["contact"] == "Marina López (Acme)" and out["items"][0]["type"] == "commitment_due"


@pytest.mark.asyncio
async def test_competitor_mentions_count_by_name_case_insensitively():
    a = _memo("m1", "u1", "c1", 2, competitors=["Gong"], summary="a", intelligence={"interest": "low"})
    b = _memo("m2", "u1", "c2", 2, competitors=["gong", "Salesloft"], summary="b", intelligence={"interest": "low"})
    out = await run("competitor_mentions", {}, _ctx(FakeSupabase(memos=[a, b])))
    assert [(r["competitor"], r["mentions"]) for r in out["items"]] == [("Gong", 2), ("Salesloft", 1)]


@pytest.mark.asyncio
async def test_meetings_agreed_rate_is_over_judged_conversations_and_voicemail_is_not_a_conversation():
    yes = _memo("m1", "u1", "c1", 2, summary="a", intelligence={"meeting": {"agreed": True}})
    no = _memo("m2", "u1", "c2", 2, summary="b", intelligence={"meeting": {"agreed": False}})
    unknown = _memo("m3", "u1", "c3", 2, summary="c", intelligence={"meeting": {"agreed": None}})
    vm = _memo("m4", "u1", "c4", 2, screening="voicemail", summary="d", intelligence={"meeting": {"agreed": False}})
    out = await run("meetings_agreed", {}, _ctx(FakeSupabase(memos=[yes, no, unknown, vm])))
    assert (out["conversations"], out["agreed"], out["not_agreed"], out["unknown"]) == (3, 1, 1, 1)
    assert out["meeting_rate_pct"] == 50.0
    assert "by_rep" not in out


@pytest.mark.asyncio
async def test_meetings_by_rep_is_only_for_team_readers_and_alphabetical():
    rows = [_memo("m1", "u2", "c1", 2, summary="a", intelligence={"meeting": {"agreed": True}}), _memo("m2", "u1", "c2", 2, summary="b", intelligence={"meeting": {"agreed": False}})]
    out = await run("meetings_agreed", {}, _ctx(FakeSupabase(memos=rows), role="admin"))
    assert [r["rep"] for r in out["by_rep"]] == ["Rep u1", "Rep u2"]


@pytest.mark.asyncio
async def test_playbook_lookup_returns_the_approved_answer_as_citable_evidence():
    db = FakeSupabase(
        playbooks=[{"id": "p1", "company_id": "co", "sales_motion_key": "discovery", "active_version_id": "v1"}],
        playbook_versions=[{"id": "v1", "playbook_id": "p1", "status": "published", "steps": [{"label": "Confirmar problema"}], "entries": [{"entry_id": "e1", "category": "price", "approved_answer": "Pregunta por el coste actual antes de dar precio."}, {"entry_id": "e2", "category": "timing", "guidance": "Ofrece una fecha concreta."}]}],
    )
    out = await run("playbook_lookup", {"category": "price"}, _ctx(db))
    assert out["playbooks"][0]["entries"] == [{"category": "price", "answer": "Pregunta por el coste actual antes de dar precio.", "evidence": "pb-e1"}]
    assert out["evidence"][0]["id"] == "pb-e1" and out["evidence"][0]["speaker"] == "playbook"


@pytest.mark.asyncio
async def test_playbook_lookup_says_when_there_is_none():
    out = await run("playbook_lookup", {}, _ctx(FakeSupabase(playbooks=[])))
    assert out["playbooks"] == [] and out["note"] == "no_playbook"


# ----- HubSpot tools ------------------------------------------------------------------------


def _ms(day):
    return str(int(datetime(2026, 8, day, 12, tzinfo=timezone.utc).timestamp() * 1000))


def _call(day, outcome=None, owner="1"):
    p = {"hs_timestamp": _ms(day), "hubspot_owner_id": owner, "hs_call_direction": "OUTBOUND"}
    if outcome:
        p["hs_call_disposition"] = G[outcome]
    return p


def _hs(calls=(), deals=(), owners=(), fail_with=None, schema=None):
    schema = schema or CRMSchema(
        object_type="deals",
        properties=[HubSpotProperty(name="closed_lost_reason", label="Closed lost reason", type="enumeration", options=[PropertyOption(label="Precio", value="price")])],
    )

    async def get_deal_schema(use_cache=True):
        return schema

    return SimpleNamespace(
        client=FakeHubSpotClient(calls=calls, deals=deals, owners=owners, fail_with=fail_with),
        connection={"id": "conn-1", "metadata": {"hubspot_owners": {"u1": "1", "u2": "2"}}},
        provider=SimpleNamespace(_schema_service=lambda: SimpleNamespace(get_deal_schema=get_deal_schema)),
    )


CALLS = [_call(3, "connected")] * 2 + [_call(4, "no_answer")] * 2 + [_call(5, "connected", owner="2")] * 3 + [_call(6, "no_answer", owner="2")] * 3


@pytest.mark.asyncio
async def test_a_member_gets_only_their_own_calls_from_hubspot():
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(CALLS)))
    assert out["total"] == 4 and out["connected"] == 2 and out["connection_rate_pct"] == 50.0
    assert out["unit"] == "calls" and out["source"] == "hubspot" and out["coverage"] == "complete"


@pytest.mark.asyncio
async def test_a_member_cannot_ask_for_a_teammate_or_a_per_rep_table():
    ctx = _ctx(FakeSupabase(), hs=_hs(CALLS))
    for args in ({"month": "2026-08", "user_id": "u2"}, {"month": "2026-08", "by_rep": True}):
        assert (await run("crm_call_stats", args, ctx))["coverage"] == "forbidden"


@pytest.mark.asyncio
async def test_an_admin_gets_the_whole_team_and_can_break_it_down_by_rep():
    owners = [{"id": "1", "firstName": "Ana", "lastName": ""}, {"id": "2", "firstName": "Luis", "lastName": ""}]
    out = await run("crm_call_stats", {"month": "2026-08", "by_rep": True}, _ctx(FakeSupabase(), role="admin", hs=_hs(CALLS, owners=owners)))
    assert out["total"] == 10 and out["connected"] == 5
    assert [(r["rep"], r["total"], r["connected"]) for r in out["by_rep"]] == [("Ana", 4, 2), ("Luis", 6, 3)]


@pytest.mark.asyncio
async def test_an_unknown_owner_is_unavailable_not_someone_elses_numbers(monkeypatch):
    async def no_owner(*a, **k):
        return None

    monkeypatch.setattr("app.services.hubspot.sync._get_hubspot_owner_id_for_user", no_owner)
    hs = _hs(CALLS)
    hs.connection["metadata"] = {}
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=hs))
    assert out == {"ok": False, "error": "owner_unresolved", "coverage": "unavailable"}


@pytest.mark.asyncio
async def test_calls_without_a_logged_outcome_make_the_rate_partial():
    calls = [_call(3, "connected")] + [_call(4)] * 9
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(calls)))
    assert out["coverage"] == "partial" and out["n"] == 10 and out["n_analysed"] == 1


@pytest.mark.asyncio
async def test_missing_hubspot_permission_is_forbidden_not_zero_calls():
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(fail_with=HubSpotError("403 forbidden: missing scope"))))
    assert out["coverage"] == "forbidden" and out["reason"] == "hubspot_scope"


@pytest.mark.asyncio
async def test_a_hubspot_outage_is_not_reported_as_not_connected_and_never_as_zero_calls():
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(fail_with=HubSpotError("500 upstream"))))
    assert out == {"ok": False, "error": "hubspot_unreachable", "coverage": "unavailable", "retryable": True}


@pytest.mark.asyncio
async def test_no_crm_connected_is_unavailable(monkeypatch):
    def boom(ctx):
        raise ValueError("No CRM connected")

    monkeypatch.setattr(copilot_tools, "_crm", boom)
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase()))
    assert out["coverage"] == "unavailable"


@pytest.mark.asyncio
async def test_a_bad_period_tells_the_model_what_to_fix():
    out = await run("crm_call_stats", {"month": "agosto"}, _ctx(FakeSupabase(), hs=_hs(CALLS)))
    assert out["ok"] is False and "2026-08" in out["error"]


def _deal(day, lost=False, won=False, reason=None, owner="1"):
    p = {"closedate": _ms(day), "hs_is_closed_lost": "true" if lost else "false", "hs_is_closed_won": "true" if won else "false", "hubspot_owner_id": owner}
    if reason:
        p["closed_lost_reason"] = reason
    return p


@pytest.mark.asyncio
async def test_lost_reasons_report_counts_top_reasons_and_win_rate():
    deals = [_deal(3, lost=True, reason="price")] * 3 + [_deal(4, lost=True)] + [_deal(5, won=True)] * 4
    out = await run("crm_lost_reasons", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(deals=deals)))
    assert out["lost"] == 4 and out["won"] == 4 and out["win_rate_pct"] == 50.0
    assert out["reasons"] == [{"reason": "Precio", "count": 3, "share_pct": 75.0}] and out["no_reason"] == 1
    assert out["coverage"] == "partial" and out["n"] == 4 and out["n_analysed"] == 3 and out["unit"] == "deals"


@pytest.mark.asyncio
async def test_a_member_sees_only_their_own_lost_deals():
    deals = [_deal(3, lost=True, reason="price", owner="1")] * 2 + [_deal(3, lost=True, reason="price", owner="2")] * 5
    out = await run("crm_lost_reasons", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(deals=deals)))
    assert out["lost"] == 2
    admin = await run("crm_lost_reasons", {"month": "2026-08"}, _ctx(FakeSupabase(), role="admin", hs=_hs(deals=deals)))
    assert admin["lost"] == 7


# ----- fixes found by the eval --------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_period_defaults_to_the_last_30_days_for_calls_and_says_so():
    out = await run("crm_call_stats", {}, _ctx(FakeSupabase(), hs=_hs(CALLS)))
    assert out["period_defaulted"] is True
    start, end = _instant_range(out)
    assert 30 <= (end - start).days <= 31  # 30 days back touches up to 31 calendar days


@pytest.mark.asyncio
async def test_no_period_defaults_to_the_last_90_days_for_lost_reasons():
    out = await run("crm_lost_reasons", {}, _ctx(FakeSupabase(), hs=_hs(deals=[])))
    assert out["period_defaulted"] is True
    start, end = _instant_range(out)
    assert 90 <= (end - start).days <= 91


@pytest.mark.asyncio
async def test_an_explicit_period_is_not_marked_defaulted():
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(CALLS)))
    assert out["period_defaulted"] is False


def _instant_range(out):
    """The local calendar days the answer covers, inclusive; a span of N days is (to - from) + 1."""
    return datetime.fromisoformat(out["period"]["from"]), datetime.fromisoformat(out["period"]["to"]) + timedelta(days=1)


@pytest.mark.asyncio
async def test_find_interactions_carries_the_prospects_words_as_citable_evidence():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 2, **ANALYSED)])
    out = await run("find_interactions", {"objection_category": "price"}, _ctx(db))
    item = out["items"][0]
    assert item["quotes"] == [{"kind": "objection", "category": "price", "quote": "Nos parece caro", "evidence": "ev-1"}]
    assert {e["id"] for e in out["evidence"]} == {"ev-1"}
    assert out["evidence"][0]["speaker"] == "prospect"


@pytest.mark.asyncio
async def test_find_interactions_quotes_only_the_matching_episodes():
    db = FakeSupabase(memos=[_memo("m1", "u1", "c1", 2, **ANALYSED)])
    out = await run("find_interactions", {"kind": "obstacle"}, _ctx(db))
    assert [q["category"] for q in out["items"][0]["quotes"]] == ["bad_moment"]


@pytest.mark.asyncio
async def test_meetings_by_rep_separates_not_judged_from_zero():
    rows = [_memo("m1", "u1", "c1", 2, summary="a", intelligence={"meeting": {"agreed": None}}), _memo("m2", "u2", "c2", 2, summary="b", intelligence={"meeting": {"agreed": True}})]
    out = await run("meetings_agreed", {}, _ctx(FakeSupabase(memos=rows), role="admin"))
    by = {r["rep"]: r for r in out["by_rep"]}
    assert by["Rep u1"]["judged"] == 0 and by["Rep u1"]["meeting_rate_pct"] is None and by["Rep u1"]["unknown"] == 1
    assert by["Rep u2"]["judged"] == 1 and by["Rep u2"]["agreed"] == 1
    assert out["judged"] == 1


@pytest.mark.asyncio
async def test_next_actions_keeps_open_obstacles_apart_from_open_objections():
    memo = _memo("m1", "u1", "c1", 3, **ANALYSED)
    out = await run("next_actions", {}, _ctx(FakeSupabase(memos=[memo])))
    assert [o["category"] for o in out["obstacles"]] == ["bad_moment"]
    assert out["obstacles"][0]["contact"] == "Marina López (Acme)"
    types = {i["type"] for i in out["items"]}
    assert "objection_open" in types  # the price objection
    assert all(i["suggested"].get("category") != "bad_moment" for i in out["items"])


@pytest.mark.asyncio
async def test_a_resolved_obstacle_is_not_a_next_action():
    resolved = dict(ANALYSED)
    resolved["intelligence"] = {**ANALYSED["intelligence"], "objections": [{"kind": "obstacle", "category": "bad_moment", "resolution": "resolved", "quote": "conduciendo", "evidence_refs": []}]}
    out = await run("next_actions", {}, _ctx(FakeSupabase(memos=[_memo("m1", "u1", "c1", 3, **resolved)])))
    assert out["obstacles"] == []


@pytest.mark.asyncio
async def test_objection_breakdown_by_rep_is_one_call_alphabetical_with_sample_sizes():
    rows = [_memo("m1", "u2", "c1", 2, **ANALYSED), _memo("m2", "u1", "c2", 2, summary="x", intelligence={"objections": [{"kind": "objection", "category": "price", "resolution": "resolved", "quote": "caro"}]})]
    out = await run("objection_breakdown", {"by_rep": True}, _ctx(FakeSupabase(memos=rows), role="admin"))
    assert [r["rep"] for r in out["by_rep"]] == ["Rep u1", "Rep u2"]
    u1 = out["by_rep"][0]
    assert u1["conversations"] == 1 and u1["objections"]["by_category"][0] == {"category": "price", "count": 1, "open": 0, "resolved": 1, "unknown": 0}
    assert out["by_rep"][1]["obstacles"]["total"] == 1
    assert out["objections"]["total"] == 2  # the team totals are still there


@pytest.mark.asyncio
async def test_a_member_cannot_ask_for_objections_by_rep():
    out = await run("objection_breakdown", {"by_rep": True}, _ctx(FakeSupabase(memos=[]), role="member"))
    assert out["coverage"] == "forbidden"


@pytest.mark.asyncio
async def test_call_stats_can_compare_with_the_previous_month_with_the_change_computed():
    july = [_call_in(7, 5, "connected")] * 2 + [_call_in(7, 6, "no_answer")] * 2
    out = await run("crm_call_stats", {"month": "2026-08", "compare_previous": True}, _ctx(FakeSupabase(), hs=_hs([*CALLS, *july])))
    assert out["total"] == 4 and out["connection_rate_pct"] == 50.0
    previous = out["previous"]
    assert previous["total"] == 4 and previous["connection_rate_pct"] == 50.0
    assert previous["change_total_pct"] == 0.0 and previous["change_rate_pts"] == 0.0
    assert previous["period"] == {"from": "2026-07-01", "to": "2026-07-31"}


def _call_in(month, day, outcome, owner="1"):
    return {"hs_timestamp": str(int(datetime(2026, month, day, 12, tzinfo=timezone.utc).timestamp() * 1000)), "hubspot_owner_id": owner, "hs_call_direction": "OUTBOUND", "hs_call_disposition": G[outcome]}


@pytest.mark.asyncio
async def test_a_month_is_reported_as_its_calendar_days_in_the_accounts_timezone():
    ctx = _ctx(FakeSupabase(), hs=_hs(CALLS))
    ctx.actor = AskActor(user_id="u1", company_id="co", role="member", timezone="Europe/Madrid")
    out = await run("crm_call_stats", {"month": "2026-08"}, ctx)
    assert out["period"] == {"from": "2026-08-01", "to": "2026-08-31"}  # not 2026-07-31T22:00 in UTC


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure, expected",
    [
        (HubSpotAuthError("401 expired"), {"error": "hubspot_reconnect", "coverage": "unavailable"}),
        (HubSpotRateLimitError("slow down"), {"error": "hubspot_busy", "coverage": "unavailable", "retryable": True}),
        (HubSpotValidationError("Property values were not valid"), {"error": "hubspot_rejected"}),
        (RuntimeError("bug"), {"error": "hubspot_error", "coverage": "unavailable"}),
    ],
)
async def test_each_kind_of_hubspot_failure_says_what_happened(failure, expected):
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=_hs(fail_with=failure)))
    assert out["ok"] is False and {k: out[k] for k in expected} == expected
    assert out.get("error") != "crm_unavailable"  # that sentence is only for "not connected"


@pytest.mark.asyncio
async def test_a_rate_limited_search_is_retried_until_it_goes_through(monkeypatch):
    calls = {"n": 0}
    hs = _hs(CALLS)
    real_post = hs.client.post

    async def flaky(endpoint, data=None):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise HubSpotRateLimitError("SECONDLY limit")  # HubSpot sends no retryAfter here, so the client will not retry it
        return await real_post(endpoint, data)

    hs.client.post = flaky
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=hs))
    assert out["total"] == 4 and calls["n"] > 3


@pytest.mark.asyncio
async def test_persistent_rate_limiting_gives_up_as_busy_after_the_bounded_retries(monkeypatch):
    hs = _hs(fail_with=HubSpotRateLimitError("SECONDLY limit"))
    out = await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=hs))
    assert out["error"] == "hubspot_busy"
    assert len([r for r in hs.client.requests if "/search" in r[0]]) <= 5 * 4  # five searches, each tried at most four times


@pytest.mark.asyncio
async def test_searches_are_spaced_so_a_burst_cannot_trip_the_per_second_limit(monkeypatch):
    import time

    from app.services.crm_copilot import crm_analytics

    monkeypatch.setattr(crm_analytics, "SEARCH_INTERVAL", 0.05)
    hs = _hs(CALLS)
    started = time.monotonic()
    await run("crm_call_stats", {"month": "2026-08"}, _ctx(FakeSupabase(), hs=hs))
    assert time.monotonic() - started >= 0.05 * 4  # five searches, four gaps


# ----- internal memos (a conversation with no customer in it) --------------------------------


def _internal(mid, user, contact, days_ago, **extraction):
    return {**_memo(mid, user, contact, days_ago, **extraction), "sales_motion_key": "internal"}


@pytest.mark.asyncio
async def test_internal_memos_are_left_out_of_the_customer_tools():
    # A meeting agreed with a colleague is not a customer meeting.
    customer = _memo("m1", "u1", "c1", 2, **ANALYSED)
    team = _internal("m2", "u1", "c1", 2, **ANALYSED)
    db = FakeSupabase(memos=[customer, team])
    met = await run("meetings_agreed", {}, _ctx(db))
    assert (met["conversations"], met["agreed"]) == (1, 1)
    assert [i["memo_id"] for i in (await run("find_interactions", {"objection_category": "price"}, _ctx(db)))["items"]] == ["m1"]
    story = await run("deal_story", {"contact_id": "c1"}, _ctx(db))
    assert story["n"] == 1
    assert (await run("objection_breakdown", {"period_days": 30}, _ctx(db)))["objections"]["total"] == 1

    due = dict(ANALYSED)
    due["intelligence"] = {**ANALYSED["intelligence"], "commitments": [{"kind": "send", "origin": "rep_promise", "text": "enviar el caso", "due_at": _iso(1), "evidence_refs": []}]}
    only_internal = FakeSupabase(memos=[_internal("m3", "u1", "c1", 3, **due)])
    assert (await run("next_actions", {}, _ctx(only_internal)))["counts"].get("commitment_due") is None

    # The loader still returns them when a caller asks for internal calls explicitly.
    ctx = _ctx(db)
    assert [m["id"] for m in intel_tools._load_memos(ctx, ctx.actor, ["u1"])] == ["m1"]
    assert {m["id"] for m in intel_tools._load_memos(ctx, ctx.actor, ["u1"], include_internal=True)} == {"m1", "m2"}
