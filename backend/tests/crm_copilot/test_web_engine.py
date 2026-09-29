"""Web Ask engine: session memory per conversation, payloads that survive a restart, real confirm results."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.crm_copilot import web_sessions as ws
from app.services.crm_copilot.actor import current_actor


def setup_function():
    ws._sessions.clear()


def test_bind_sets_a_per_request_actor_with_role_and_conversation():
    ws.bind_ask_actor("u1", "co-1", role="admin", conversation_id="conv-9")
    actor = current_actor()
    assert (actor.user_id, actor.company_id, actor.role, actor.conversation_id) == ("u1", "co-1", "admin", "conv-9")


def test_two_conversations_of_one_user_do_not_share_memory():
    a = ws.session_for("u1", "conv-a")
    b = ws.session_for("u1", "conv-b")
    a.setdefault("copilot", {})["last_contact_id"] = "c-a"
    assert "copilot" not in b
    assert ws.session_for("u1", "conv-a")["copilot"]["last_contact_id"] == "c-a"


def test_a_memory_snapshot_seeds_a_fresh_process():
    memory = {"messages": [{"role": "user", "content": "hola"}], "last_contact_id": "c1"}
    ws.seed_session("u1", "conv-a", memory)
    assert ws.session_for("u1", "conv-a")["copilot"]["last_contact_id"] == "c1"
    ws.seed_session("u1", "conv-a", {"last_contact_id": "other"})  # never overwrite a live session
    assert ws.session_for("u1", "conv-a")["copilot"]["last_contact_id"] == "c1"


def test_the_memory_snapshot_is_bounded_and_keeps_the_pending_operation():
    copilot = {
        "messages": [{"role": "user", "content": str(i)} for i in range(40)],
        "pending_tool": "create_task",
        "pending_args": {"subject": "x"},
        "pending_id": "call-1",
        "unrelated": "dropped",
    }
    snap = ws.memory_snapshot({"copilot": copilot})
    assert len(snap["messages"]) == 24  # the live window: 12 question-and-answer pairs
    assert snap["pending_tool"] == "create_task"
    assert "unrelated" not in snap


def test_a_confirm_payload_keeps_the_tool_and_args_server_side_only():
    artifacts = {"copilot": {"pending_args": {"contact_id": "c1", "subject": "Llamar"}, "pending_id": "call-1", "pending_tool": "create_task"}}
    body = ws.payload_from_turn("Tarea: Llamar", artifacts, kind="confirm")
    confirmation = body["confirmation"]
    assert confirmation["tool"] == "create_task"
    assert confirmation["args"] == {"contact_id": "c1", "subject": "Llamar"}
    assert confirmation["operation_id"] == "call-1"


@pytest.mark.asyncio
async def test_executing_a_stored_operation_reports_the_real_result(monkeypatch):
    async def fake_execute(name, args, ctx):
        assert (name, args) == ("create_task", {"subject": "Llamar"})
        assert ctx.actor.user_id == "u1"
        return {"ok": True, "url": "https://hs/task/1"}

    monkeypatch.setattr("app.services.crm_copilot.tools.execute_tool", fake_execute)
    monkeypatch.setattr("app.deps.get_supabase", lambda: MagicMock())
    ws.bind_ask_actor("u1", "co-1", conversation_id="conv-a")
    out = await ws.execute_stored_operation({"tool": "create_task", "args": {"subject": "Llamar"}, "operation_id": "call-1"})
    assert out["status"] == "succeeded" and out["applied"] is True
    assert out["url"] == "https://hs/task/1"


@pytest.mark.asyncio
async def test_a_failed_write_is_not_reported_as_applied(monkeypatch):
    async def fake_execute(name, args, ctx):
        return {"ok": False, "error": "HubSpot 400"}

    monkeypatch.setattr("app.services.crm_copilot.tools.execute_tool", fake_execute)
    monkeypatch.setattr("app.deps.get_supabase", lambda: MagicMock())
    ws.bind_ask_actor("u1", "co-1", conversation_id="conv-a")
    out = await ws.execute_stored_operation({"tool": "create_task", "args": {}, "operation_id": "call-1"})
    assert out["status"] == "failed" and out["applied"] is False


@pytest.mark.asyncio
async def test_a_timeout_is_uncertain_so_it_is_reconciled_not_retried(monkeypatch):
    async def fake_execute(name, args, ctx):
        return {"ok": False, "error": "ReadTimeout: timed out"}

    monkeypatch.setattr("app.services.crm_copilot.tools.execute_tool", fake_execute)
    monkeypatch.setattr("app.deps.get_supabase", lambda: MagicMock())
    ws.bind_ask_actor("u1", "co-1", conversation_id="conv-a")
    out = await ws.execute_stored_operation({"tool": "create_task", "args": {}, "operation_id": "call-1"})
    assert out["status"] == "uncertain" and out["applied"] is False


@pytest.mark.asyncio
async def test_executing_clears_the_pending_tool_so_the_loop_cannot_run_it_twice(monkeypatch):
    async def fake_execute(name, args, ctx):
        return {"ok": True}

    monkeypatch.setattr("app.services.crm_copilot.tools.execute_tool", fake_execute)
    monkeypatch.setattr("app.deps.get_supabase", lambda: MagicMock())
    ws.bind_ask_actor("u1", "co-1", conversation_id="conv-a")
    copilot = ws.session_for("u1", "conv-a").setdefault("copilot", {})
    copilot.update({"pending_tool": "create_task", "pending_args": {}, "pending_id": "call-1", "messages": [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "create_task", "arguments": "{}"}}]}
    ]})
    await ws.execute_stored_operation({"tool": "create_task", "args": {}, "operation_id": "call-1"})
    assert "pending_tool" not in copilot
    assert copilot["messages"][-1]["role"] == "tool" and copilot["messages"][-1]["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_live_ask_loop_offers_team_tools_only_to_owners_and_admins(monkeypatch):
    seen = {}

    async def fake_run(text, **kwargs):
        seen["tools"] = {t["function"]["name"] for t in kwargs["tools"]}
        seen["verify"] = kwargs.get("verify_numbers")
        result = SimpleNamespace(text="Hecho.", kind="text", evidence=[], envelopes=[], pending=None, artifacts=kwargs["artifacts"])
        return result

    monkeypatch.setattr("app.services.crm_copilot.loop.run_copilot_turn", fake_run)
    monkeypatch.setattr("app.deps.get_supabase", lambda: MagicMock())
    ws.bind_ask_actor("u1", "co-1", role="member", conversation_id="c")
    await ws.live_ask_loop("hola")
    assert "team_health" not in seen["tools"] and "deal_story" in seen["tools"] and seen["verify"] is True
    ws.bind_ask_actor("u2", "co-1", role="owner", conversation_id="c2")
    await ws.live_ask_loop("hola")
    assert "team_health" in seen["tools"]


@pytest.mark.asyncio
async def test_live_ask_loop_numbers_citations_and_reports_coverage(monkeypatch):
    async def fake_run(text, **kwargs):
        return SimpleNamespace(
            text="Caro [ev-a1].",
            kind="text",
            evidence=[{"id": "ev-a1", "quote": "Nos parece caro", "memo_id": "m1"}],
            envelopes=[{"coverage": "partial", "n": 14, "n_analysed": 6}],
            pending=None,
            artifacts=kwargs["artifacts"],
        )

    monkeypatch.setattr("app.services.crm_copilot.loop.run_copilot_turn", fake_run)
    monkeypatch.setattr("app.deps.get_supabase", lambda: MagicMock())
    ws.bind_ask_actor("u1", "co-1", conversation_id="c")
    out = await ws.live_ask_loop("¿qué dijo?")
    assert out["text"] == "Caro [1]."
    assert out["evidence"] == [{"id": "ev-a1", "quote": "Nos parece caro", "memo_id": "m1"}]
    assert out["coverage_note"] == {"level": "partial", "n": 14, "n_analysed": 6}
    assert "memory" in out


def test_the_web_prompt_names_today_the_audience_and_the_one_tool_rule():
    from app.services.crm_copilot.prompts import build_system_prompt

    member = build_system_prompt({}, web=True, manager=False, today="2026-09-29", tz="Europe/Madrid")
    admin = build_system_prompt({}, web=True, manager=True, today="2026-09-29")
    assert "Today is 2026-09-29" in member and "only their own work" in member
    assert "whole team" in admin
    assert "Never merge them" in member and "hubspot_query" in member
    assert "crm_call_stats" in member and "month=YYYY-MM" in member
    assert "Never merge them" not in build_system_prompt({}, web=False)  # WhatsApp keeps its own short persona
    assert "WhatsApp" not in member and "{audience}" not in member and "{limits}" not in member


def test_an_admins_prompt_lists_the_team_ids_a_member_never_sees():
    from app.services.crm_copilot.prompts import build_system_prompt

    team = {"u-luis": "Luis Prieto", "u-ana": "Ana Ruiz"}
    admin = build_system_prompt({}, web=True, manager=True, team=team)
    assert "Ana Ruiz = u-ana; Luis Prieto = u-luis" in admin
    assert "u-ana" not in build_system_prompt({}, web=True, manager=False)


def test_a_members_prompt_tells_them_to_decline_team_questions_without_tools_and_a_managers_does_not():
    from app.services.crm_copilot.prompts import build_system_prompt

    assert "call no tool" in build_system_prompt({}, web=True, manager=False)
    assert "call no tool" not in build_system_prompt({}, web=True, manager=True)


def test_the_prompt_forbids_the_redundancy_the_eval_found():
    from app.services.crm_copilot.prompts import build_system_prompt

    text = build_system_prompt({}, web=True, manager=True)
    for rule in ("no closing offer or question", "Unknown is not zero", "never as raw keys", "not a lost deal", "say nothing about objections", "Do not rank people"):
        assert rule in text


def test_the_web_prompt_names_no_example_people_and_only_lists_the_real_team():
    import re

    from app.services.crm_copilot.prompts import build_system_prompt

    member = build_system_prompt({}, web=True, manager=False)
    assert not re.search(r"\b(Luis|Ana|Marta|Marina|Acme|Dani)\b", member)  # those exist only in the eval's synthetic company
    admin = build_system_prompt({}, web=True, manager=True, team={"u9": "Real Person"})
    assert "the only people who exist" in admin and "Real Person = u9" in admin
    assert "the only people who exist" not in member


def test_what_survives_a_reload_is_the_same_window_the_model_sees_live_and_starts_at_a_question():
    from app.services.crm_copilot.loop import MAX_HISTORY
    from app.services.crm_copilot.web_sessions import memory_snapshot

    messages = []
    for i in range(20):
        messages += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": f"a{i}"}]
    snap = memory_snapshot({"copilot": {"messages": messages}})["messages"]
    assert len(snap) == MAX_HISTORY == 24 and snap[0] == {"role": "user", "content": "q8"} and snap[-1]["content"] == "a19"
