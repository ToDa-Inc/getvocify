"""The MCP server over HTTP: who gets in, what each role sees, the tools' answers, ask_vocify and the limits."""

from __future__ import annotations

import asyncio
import time

import jwt as pyjwt
import pytest

from app.config import settings
from tests.mcp.conftest import (
    COMPANY,
    M_INTERNAL,
    M_MEETING,
    M_PRICE,
    M_PROCESSING,
    M_TEAMMATE,
    MANAGER,
    OUTSIDER,
    REP,
    TEAMMATE,
    TRANSCRIPT,
    call,
    rpc,
)

TOOLS = {"list_interactions", "get_interaction", "get_coaching", "ask_vocify", "get_ask_result"}


def _session_jwt(user_id: str, *, role: str = "authenticated", client_id: str | None = None) -> str:
    claims = {"sub": user_id, "role": role, "aud": "authenticated", "exp": int(time.time()) + 600}
    if client_id:
        claims["client_id"] = client_id
    return pyjwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256")


# ----- who gets in ------------------------------------------------------------------------------------


def test_no_credential_is_401_pointing_at_the_resource_metadata(mcp_client):
    response = rpc(mcp_client, None, "tools/list")
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert 'resource_metadata="' in challenge
    assert "/.well-known/oauth-protected-resource/mcp" in challenge


def test_resource_metadata_names_the_mcp_url_and_supabase_as_issuer(mcp_client):
    body = mcp_client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert body["resource"] == settings.BACKEND_PUBLIC_URL.rstrip("/") + "/mcp"
    assert body["authorization_servers"] == [settings.SUPABASE_URL.rstrip("/") + "/auth/v1"]


def test_an_api_key_lists_the_five_read_only_tools(mcp_client, key_for):
    response = rpc(mcp_client, key_for(REP), "tools/list")
    tools = response.json()["result"]["tools"]
    assert {t["name"] for t in tools} == TOOLS
    assert all(t["annotations"]["readOnlyHint"] is True and t.get("title") for t in tools)


def test_a_regenerated_key_retires_the_old_one_and_a_revoked_key_stops(mcp_client, key_for, db):
    from app.services.mcp import api_keys

    old = key_for(REP)
    new = key_for(REP)
    assert rpc(mcp_client, old, "tools/list").status_code == 401
    assert rpc(mcp_client, new, "tools/list").status_code == 200
    api_keys.revoke_key(db, REP)
    assert rpc(mcp_client, new, "tools/list").status_code == 401


def test_only_the_hash_of_a_key_is_stored(key_for, db):
    key = key_for(REP)
    row = next(r for r in db.tables["user_profiles"] if r["id"] == REP)
    assert key not in row.values()
    assert row["api_key_prefix"] == key[:10]


def test_a_wrong_key_is_401(mcp_client):
    assert rpc(mcp_client, "vk_not-a-real-key", "tools/list").status_code == 401


def test_an_oauth_token_is_the_same_user_as_that_users_key(mcp_client, key_for):
    _, by_key = call(mcp_client, key_for(REP), "list_interactions")
    _, by_token = call(mcp_client, _session_jwt(REP, client_id="claude-ai"), "list_interactions")
    assert by_token == by_key


def test_the_anon_or_service_role_jwt_is_not_a_caller(mcp_client):
    assert rpc(mcp_client, _session_jwt(REP, role="anon"), "tools/list").status_code == 401
    assert rpc(mcp_client, _session_jwt(REP, role="service_role"), "tools/list").status_code == 401


def test_a_removed_member_is_told_on_the_next_call(mcp_client, key_for, db):
    key = key_for(REP)
    db.tables["company_members"] = [m for m in db.tables["company_members"] if m["user_id"] != REP]
    is_error, text = call(mcp_client, key, "list_interactions")
    assert is_error and "no active Vocify workspace" in text


def test_a_workspace_with_mcp_off_is_told_how_to_turn_it_on(mcp_client, key_for):
    is_error, text = call(mcp_client, key_for(OUTSIDER), "list_interactions")
    assert is_error and "turned off" in text and "Settings" in text


# ----- what each role sees ----------------------------------------------------------------------------


def test_a_rep_lists_only_their_own_usable_interactions(mcp_client, key_for):
    _, body = call(mcp_client, key_for(REP), "list_interactions")
    ids = [row["id"] for row in body["interactions"]]
    assert ids == [M_PRICE, M_MEETING]  # newest first; internal, processing and the teammate's are left out
    assert M_INTERNAL not in ids and M_PROCESSING not in ids and M_TEAMMATE not in ids


def test_a_list_row_carries_the_facts_to_count_without_opening_it(mcp_client, key_for):
    _, body = call(mcp_client, key_for(REP), "list_interactions")
    row = body["interactions"][0]
    assert row["contact"] == "Ana" and row["company"] == "Acme"
    assert row["objections"] == ["price"] and row["competitors"] == ["Gong"]
    assert row["outcome"] == "follow_up" and row["summary"] == "Pricing call with Acme."
    assert row["url"].endswith(f"/dashboard/memos/{M_PRICE}")


def test_a_manager_sees_the_team_and_can_narrow_to_one_rep(mcp_client, key_for):
    key = key_for(MANAGER)
    _, team = call(mcp_client, key, "list_interactions")
    assert {row["id"] for row in team["interactions"]} == {M_PRICE, M_MEETING, M_TEAMMATE}
    _, one = call(mcp_client, key, "list_interactions", {"rep_id": TEAMMATE})
    assert [row["id"] for row in one["interactions"]] == [M_TEAMMATE]


def test_a_rep_asking_for_a_teammate_is_refused_not_given_empty_data(mcp_client, key_for):
    is_error, text = call(mcp_client, key_for(REP), "list_interactions", {"rep_id": TEAMMATE})
    assert is_error and "outside what your Vocify role can see" in text


def test_a_rep_cannot_open_a_teammates_interaction(mcp_client, key_for):
    is_error, text = call(mcp_client, key_for(REP), "get_interaction", {"id": M_TEAMMATE})
    assert is_error and "list_interactions" in text


# ----- list filters and paging --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"kind": "meeting"}, [M_MEETING]),
        ({"outcome": "follow_up"}, [M_PRICE]),
        ({"objection_category": "timing"}, [M_MEETING]),
        ({"q": "acme"}, [M_PRICE]),
        ({"date_from": "2026-10-10"}, [M_PRICE]),
        ({"date_to": "2026-10-09"}, [M_MEETING]),
        ({"contact_id": "c-ana"}, [M_PRICE, M_MEETING]),
    ],
)
def test_list_filters(mcp_client, key_for, arguments, expected):
    _, body = call(mcp_client, key_for(REP), "list_interactions", arguments)
    assert [row["id"] for row in body["interactions"]] == expected


def test_paging_walks_the_whole_history_once(mcp_client, key_for):
    key = key_for(MANAGER)
    seen, cursor = [], None
    for _ in range(5):
        _, body = call(mcp_client, key, "list_interactions", {"limit": 1, **({"cursor": cursor} if cursor else {})})
        seen += [row["id"] for row in body["interactions"]]
        cursor = body.get("next_cursor")
        if not cursor:
            break
    assert seen == [M_PRICE, M_MEETING, M_TEAMMATE]


def test_a_bad_argument_says_how_to_fix_it(mcp_client, key_for):
    is_error, text = call(mcp_client, key_for(REP), "list_interactions", {"date_from": "last week"})
    assert is_error and "ISO date" in text


# ----- get_interaction --------------------------------------------------------------------------------


def test_the_full_record_has_what_the_memo_page_shows(mcp_client, key_for):
    _, record = call(mcp_client, key_for(REP), "get_interaction", {"id": M_PRICE})
    assert record["summary"].startswith("Pricing call")
    assert record["objections"][0]["category"] == "price" and record["objections"][0]["state"] == "open"
    assert record["commitments"] == [{"text": "Send the proposal", "due_at": "2026-10-17", "by": "rep"}]
    assert record["evidence"][0] == {"id": "ev1", "quote": "It's too expensive for us", "speaker": "prospect", "at_ms": 61000}
    assert record["coaching"] == {"status": "not_scored", "reason": "not_scored"}
    assert "transcript" not in record


def test_a_record_still_processing_says_so(mcp_client, key_for):
    _, record = call(mcp_client, key_for(REP), "get_interaction", {"id": M_PROCESSING})
    assert record["status"] == "processing"


def test_transcripts_are_off_until_the_workspace_turns_them_on(mcp_client, key_for, db):
    key = key_for(REP)
    _, record = call(mcp_client, key, "get_interaction", {"id": M_PRICE, "include_transcript": True})
    assert record["transcript"]["available"] is False

    db.tables["company_feature_flags"].append({"company_id": COMPANY, "flag": "MCP_TRANSCRIPTS_ENABLED", "enabled": True})
    from app.services import feature_flags

    feature_flags.clear_cache()
    _, first = call(mcp_client, key, "get_interaction", {"id": M_PRICE, "include_transcript": True})
    page = first["transcript"]
    assert page["text"].startswith("Rep: line 0") and page["next_cursor"]
    assert len(page["text"]) <= 12_000 and page["text"].endswith("\n")
    _, second = call(mcp_client, key, "get_interaction", {"id": M_PRICE, "include_transcript": True, "transcript_cursor": page["next_cursor"]})
    assert TRANSCRIPT.startswith(page["text"] + second["transcript"]["text"])  # pages follow on, no gap or overlap


# ----- get_coaching -----------------------------------------------------------------------------------


def test_coaching_returns_the_producers_numbers_unchanged(mcp_client, key_for, monkeypatch):
    from app.services.crm_copilot import brain_tools

    produced = {"coverage": "complete", "flow": "sdr", "this_week": {"conversations": 4}, "focus": {"step": "Ask for the meeting"}}

    async def my_coaching(args, ctx, actor):
        assert actor.user_id == REP
        return produced

    monkeypatch.setitem(brain_tools.HANDLERS, "my_coaching", my_coaching)
    _, body = call(mcp_client, key_for(REP), "get_coaching")
    assert body == produced


def test_team_coaching_is_for_managers(mcp_client, key_for, monkeypatch):
    from app.services.crm_copilot import brain_tools

    async def team_health(args, ctx, actor):
        return {"ok": True, "scope": "whole team", "period_key": args["period"]}

    monkeypatch.setitem(brain_tools.HANDLERS, "team_health", team_health)
    is_error, _ = call(mcp_client, key_for(REP), "get_coaching", {"scope": "team"})
    assert is_error
    _, body = call(mcp_client, key_for(MANAGER), "get_coaching", {"scope": "team", "period": "month"})
    assert body["period_key"] == "month"


# ----- ask_vocify -------------------------------------------------------------------------------------


@pytest.fixture
def ask_loop(monkeypatch):
    """Stands in for the Ask engine (a paid model run). Records how it was called."""
    from app.services.crm_copilot import web_sessions

    seen: dict = {"delay": 0.0, "body": {"text": "Price came up 2 times.", "evidence": [{"id": "ev1", "memo_id": M_PRICE, "quote": "too expensive"}]}}

    async def loop(text, confirm=None, on_event=None, *, read_only=False, max_rounds=None):
        from app.services.crm_copilot.actor import current_actor

        seen.update(text=text, read_only=read_only, max_rounds=max_rounds, actor=current_actor().user_id)
        await asyncio.sleep(seen["delay"])
        return seen["body"]

    monkeypatch.setattr(web_sessions, "live_ask_loop", loop)
    return seen


def test_ask_answers_read_only_with_fewer_rounds_and_cites_its_sources(mcp_client, key_for, ask_loop, db):
    _, body = call(mcp_client, key_for(REP), "ask_vocify", {"question": "How often did price come up?"})
    assert body["status"] == "completed" and body["answer"] == "Price came up 2 times."
    assert body["evidence"][0]["memo_id"] == M_PRICE
    assert ask_loop["read_only"] is True and ask_loop["max_rounds"] == settings.MCP_ASK_MAX_ROUNDS
    assert ask_loop["actor"] == REP
    stored = db.tables["copilot_web_turns"]
    assert len(stored) == 1 and stored[0]["conversation_id"].startswith("mcp:") and stored[0]["status"] == "completed"


def test_a_slow_question_returns_a_run_id_to_poll(mcp_client, key_for, ask_loop, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ASK_WAIT_SECONDS", 0.05)
    ask_loop["delay"] = 0.3
    key = key_for(REP)
    _, first = call(mcp_client, key, "ask_vocify", {"question": "Top objections this month?"})
    assert first["status"] == "running" and first["run_id"]
    for _ in range(40):
        _, polled = call(mcp_client, key, "get_ask_result", {"run_id": first["run_id"]})
        if polled["status"] != "running":
            break
        time.sleep(0.05)
    assert polled["status"] == "completed" and polled["answer"] == "Price came up 2 times."


def test_another_user_cannot_read_a_run(mcp_client, key_for, ask_loop, db):
    call(mcp_client, key_for(REP), "ask_vocify", {"question": "Q?"})
    run_id = db.tables["copilot_web_turns"][0]["conversation_id"].removeprefix("mcp:")
    _, own = call(mcp_client, key_for(REP), "get_ask_result", {"run_id": run_id})
    _, other = call(mcp_client, key_for(TEAMMATE), "get_ask_result", {"run_id": run_id})
    assert own["status"] == "completed" and other["status"] == "not_found"


def test_a_failed_run_tells_the_agent_to_read_the_data_directly(mcp_client, key_for, ask_loop):
    ask_loop["body"] = None
    _, body = call(mcp_client, key_for(REP), "ask_vocify", {"question": "Q?"})
    assert body["status"] == "failed" and "list_interactions" in body["error"]


def test_the_daily_ask_cap_stops_the_next_question(mcp_client, key_for, ask_loop, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ASK_PER_DAY", 2)
    key = key_for(REP)
    for _ in range(2):
        assert call(mcp_client, key, "ask_vocify", {"question": "Q?"})[0] is False
    is_error, text = call(mcp_client, key, "ask_vocify", {"question": "Q?"})
    assert is_error and "daily limit of 2" in text


def test_mcp_questions_stay_out_of_the_web_ask_history():
    from app.services.mcp.ask_runs import is_mcp_conversation

    assert is_mcp_conversation("mcp:abc") and not is_mcp_conversation("c-123")


def test_read_only_ask_hides_every_write_tool():
    from app.services.crm_copilot.tools import WRITE_TOOLS
    from app.services.crm_copilot.web_sessions import READ_ONLY_HIDDEN_TOOLS

    assert WRITE_TOOLS <= READ_ONLY_HIDDEN_TOOLS and "preview_write" in READ_ONLY_HIDDEN_TOOLS


# ----- limits -----------------------------------------------------------------------------------------


def test_the_per_minute_limit_says_when_to_retry(mcp_client, key_for, monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOOL_CALLS_PER_MINUTE", 2)
    key = key_for(REP)
    assert call(mcp_client, key, "list_interactions")[0] is False
    assert call(mcp_client, key, "list_interactions")[0] is False
    is_error, text = call(mcp_client, key, "list_interactions")
    assert is_error and "2 per minute" in text and "Retry in" in text
