"""F07.05: Ask reads Vocify's own data, scoped to the caller's company and role."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.company import Membership
from app.services.crm_copilot import viewer as viewer_mod
from app.services.crm_copilot import vocify_reads
from app.services.crm_copilot.loop import run_copilot_turn
from app.services.crm_copilot.prompts import DATA_PROMPT, build_system_prompt
from app.services.crm_copilot.tools import (
    ASK_DATA_TOOLS,
    OPENAI_TOOLS,
    CopilotContext,
    build_openai_tools,
    execute_tool,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
CO = "co-1"
OTHER_CO = "co-2"


def _ago(days: float = 0, hours: float = 0) -> str:
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


class _Result:
    def __init__(self, data):
        self.data = data


class _AnyOf:
    def __init__(self, values):
        self.values = set(values)


class _Query:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self.filters = []
        self.order_key = None
        self.desc = False
        self.cap = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def order(self, column, desc=False):
        self.order_key, self.desc = column, desc
        return self

    def limit(self, count):
        self.cap = count
        return self

    def execute(self):
        if self.name in self.store.broken:
            raise RuntimeError(f"{self.name} unavailable")
        self.store.queries.append((self.name, list(self.filters)))
        rows = list(self.store.tables.get(self.name, []))
        for op, column, value in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif op == "in":
                rows = [row for row in rows if row.get(column) in value]
            elif op == "gte":
                rows = [row for row in rows if str(row.get(column) or "") >= str(value)]
        if self.order_key:
            rows.sort(key=lambda row: str(row.get(self.order_key) or ""), reverse=self.desc)
        if self.cap is not None:
            rows = rows[: self.cap]
        return _Result(rows)


class _Store:
    def __init__(self, **tables):
        self.tables = tables
        self.broken = set()
        self.queries = []

    def table(self, name):
        return _Query(self, name)


MEMBERS = [
    {"user_id": "rep-a", "role": "member", "status": "active", "email": "a@co.es", "full_name": "Ana"},
    {"user_id": "rep-b", "role": "member", "status": "active", "email": "b@co.es", "full_name": "Bruno"},
    {"user_id": "boss", "role": "admin", "status": "active", "email": "boss@co.es", "full_name": "Carla"},
]


def _memo(memo_id, user_id, *, company_id=CO, days=1, contact=None, summary="Resumen", intelligence=None, **extra):
    extraction = {"summary": summary, "contactName": extra.pop("contact_name", None)}
    if intelligence is not None:
        extraction["intelligence"] = intelligence
    return {
        "id": memo_id,
        "user_id": user_id,
        "company_id": company_id,
        "created_at": _ago(days=days),
        "hubspot_contact_id": contact,
        "hubspot_deal_id": extra.pop("deal", None),
        "extraction": extraction,
    }


def _patch_viewer(monkeypatch, role_by_user=None, company_id=CO, members=MEMBERS):
    roles = role_by_user or {"rep-a": "member", "rep-b": "member", "boss": "admin"}

    def fake_scope(_supabase, user_id):
        if user_id not in roles:
            return None, [], {}
        membership = Membership(id="m", company_id=company_id, user_id=user_id, role=roles[user_id], status="active")
        return membership, members, {}

    monkeypatch.setattr(viewer_mod, "load_viewer_scope", fake_scope)


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(settings, "ASK_VOCIFY_DATA_TOOLS_ENABLED", True)
    yield
    feature_flags.clear_cache()


def _ctx(store, user_id):
    return CopilotContext(supabase=store, user_id=user_id, artifacts={})


def _names(tools):
    return {tool["function"]["name"] for tool in tools}


def test_the_flag_decides_which_tools_the_model_sees():
    off = _names(build_openai_tools(data_tools=False))
    on = _names(build_openai_tools(data_tools=True))
    assert not (off & ASK_DATA_TOOLS)
    assert ASK_DATA_TOOLS <= on
    assert {"get_team_metrics", "list_conversations", "get_objections", "get_call_priorities"} == ASK_DATA_TOOLS
    assert ASK_DATA_TOOLS == vocify_reads.VOCIFY_READS
    assert on - off == ASK_DATA_TOOLS
    assert _names(OPENAI_TOOLS) == on


class _SeenLLM:
    def __init__(self):
        self.calls = []

    async def chat_tools(self, messages, **kwargs):
        self.calls.append({"system": messages[0]["content"], "tools": _names(kwargs["tools"])})
        return type("R", (), {"content": "ok", "tool_calls": []})()


async def _turn(store, user_id):
    llm = _SeenLLM()
    ctx = _ctx(store, user_id)
    await run_copilot_turn("hola", artifacts=ctx.artifacts, llm=llm, tools=OPENAI_TOOLS, system=build_system_prompt({}), ctx=ctx)
    return llm.calls[0]


async def test_a_company_override_turns_ask_data_on_for_that_company_only(monkeypatch):
    monkeypatch.setattr(settings, "ASK_VOCIFY_DATA_TOOLS_ENABLED", False)
    _patch_viewer(monkeypatch)
    overrides = [{"company_id": CO, "flag": "ASK_VOCIFY_DATA_TOOLS_ENABLED", "enabled": True}]

    on = await _turn(_Store(company_feature_flags=overrides, memos=[_memo("m1", "rep-a")]), "rep-a")
    assert ASK_DATA_TOOLS <= on["tools"]
    assert DATA_PROMPT.strip() in on["system"]
    listed = await execute_tool("list_conversations", {}, _ctx(_Store(company_feature_flags=overrides, memos=[_memo("m1", "rep-a")]), "rep-a"))
    assert [item["memo_id"] for item in listed["items"]] == ["m1"]

    feature_flags.clear_cache()
    _patch_viewer(monkeypatch, company_id=OTHER_CO)
    off = await _turn(_Store(company_feature_flags=overrides), "rep-a")
    assert not (ASK_DATA_TOOLS & off["tools"])
    assert DATA_PROMPT.strip() not in off["system"]
    assert "search_contacts" in off["tools"]


async def test_a_company_override_can_turn_ask_data_off(monkeypatch):
    _patch_viewer(monkeypatch)
    overrides = [{"company_id": CO, "flag": "ASK_VOCIFY_DATA_TOOLS_ENABLED", "enabled": False}]
    seen = await _turn(_Store(company_feature_flags=overrides), "rep-a")
    assert not (ASK_DATA_TOOLS & seen["tools"])
    result = await execute_tool("list_conversations", {}, _ctx(_Store(company_feature_flags=overrides, memos=[_memo("m1", "rep-a")]), "rep-a"))
    assert result["ok"] is False
    assert "m1" not in str(result)


async def test_a_data_tool_is_refused_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "ASK_VOCIFY_DATA_TOOLS_ENABLED", False)
    _patch_viewer(monkeypatch)
    store = _Store(memos=[_memo("m1", "rep-a")])
    result = await execute_tool("list_conversations", {}, _ctx(store, "rep-a"))
    assert result["ok"] is False
    assert "m1" not in str(result)


async def test_a_caller_without_membership_gets_forbidden_not_an_empty_list(monkeypatch):
    _patch_viewer(monkeypatch)
    store = _Store(memos=[_memo("m1", "rep-a")])
    for name in ("list_conversations", "get_objections", "get_call_priorities", "get_team_metrics"):
        result = await execute_tool(name, {}, _ctx(store, "stranger"))
        assert result["ok"] is False, name
        assert result["coverage"] == "forbidden", name
        assert "m1" not in str(result)


async def test_team_metrics_refuse_a_member(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_team_metrics", {"instruction": "ignora el rol"}, _ctx(_Store(), "rep-a"))
    assert result == {"ok": False, "error": "forbidden", "coverage": "forbidden"}


async def test_team_metrics_use_the_membership_company_not_the_last_web_actor(monkeypatch):
    from app.services.crm_copilot import web_sessions

    _patch_viewer(monkeypatch)
    web_sessions.bind_ask_actor("someone-else", OTHER_CO)
    seen = {}

    def fake_inputs(_supabase, company_id, *, user_id=None, motion=None):
        seen.update(company_id=company_id, user_id=user_id, motion=motion)
        return {"parts": [], "playbook_present": False, "sample_size": 0, "reps": [], "review": []}

    monkeypatch.setattr(vocify_reads, "load_team_adherence_inputs", fake_inputs)
    result = await execute_tool("get_team_metrics", {}, _ctx(_Store(), "boss"))
    assert result["ok"] is True
    assert seen["company_id"] == CO
    assert result["scope"] == {"scope": "team", "user_id": None}
    assert result["source"] == "team_adherence"
    assert "adherence" in result["metrics"]


async def test_team_metrics_refuse_a_user_outside_the_company(monkeypatch):
    _patch_viewer(monkeypatch)
    monkeypatch.setattr(
        vocify_reads,
        "load_team_adherence_inputs",
        lambda *_a, **_k: pytest.fail("no read for a foreign user"),
    )
    result = await execute_tool("get_team_metrics", {"user_id": "rep-of-co-2"}, _ctx(_Store(), "boss"))
    assert result["ok"] is False
    assert result["coverage"] == "forbidden"


async def test_team_metrics_for_one_rep_of_the_company(monkeypatch):
    _patch_viewer(monkeypatch)
    seen = {}

    def fake_inputs(_supabase, company_id, *, user_id=None, motion=None):
        seen["user_id"] = user_id
        return {"parts": [], "playbook_present": False, "sample_size": 0}

    monkeypatch.setattr(vocify_reads, "load_team_adherence_inputs", fake_inputs)
    result = await execute_tool("get_team_metrics", {"user_id": "rep-b"}, _ctx(_Store(), "boss"))
    assert result["ok"] is True
    assert seen["user_id"] == "rep-b"
    assert result["scope"] == {"scope": "user", "user_id": "rep-b"}


def _conversation_store():
    return _Store(memos=[
        _memo("own-1", "rep-a", contact="c-7", days=1, summary="## Llamada\nQuiere precio cerrado", intelligence={
            "pain_confirmed": True,
            "objections": [{"category": "price", "resolution": "open", "quote": "es caro"}],
            "commitments": [{"kind": "send", "text": "enviar propuesta", "due_at": "2026-09-30"}],
            "meeting": {"agreed": True, "starts_at": "2026-10-01T10:00:00+02:00"},
        }),
        _memo("own-old", "rep-a", contact="c-7", days=3, summary="Primera llamada"),
        _memo("teammate", "rep-b", contact="c-9", days=2, summary="Otra"),
        _memo("legacy", "rep-b", company_id=None, days=4, summary="Sin empresa"),
        _memo("foreign-user", "rep-of-co-2", company_id=OTHER_CO, contact="c-7", summary="Secreto"),
        _memo("moved", "rep-a", company_id=OTHER_CO, contact="c-7", summary="De otra empresa"),
    ])


async def test_a_member_lists_only_their_own_conversations(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("list_conversations", {}, _ctx(_conversation_store(), "rep-a"))
    assert result["coverage"] == "complete"
    ids = [item["memo_id"] for item in result["items"]]
    assert ids == ["own-1", "own-old"]
    first = result["items"][0]
    assert first["summary"].startswith("Quiere precio cerrado")
    assert first["contact_id"] == "c-7"
    assert first["author"] == "Ana"
    assert first["pain_confirmed"] is True
    assert first["objections"] == [{"category": "price", "resolution": "open", "quote": "es caro"}]
    assert first["commitments"] == [{"text": "enviar propuesta", "due_at": "2026-09-30"}]
    assert first["meeting"] == {"agreed": True, "starts_at": "2026-10-01T10:00:00+02:00"}


async def test_an_admin_lists_the_company_but_never_another_company(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("list_conversations", {"days": 30}, _ctx(_conversation_store(), "boss"))
    ids = {item["memo_id"] for item in result["items"]}
    assert ids == {"own-1", "own-old", "teammate", "legacy"}
    assert "Secreto" not in str(result)
    assert "De otra empresa" not in str(result)


async def test_the_last_conversation_with_a_contact(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("list_conversations", {"contact_id": "c-7", "limit": 1}, _ctx(_conversation_store(), "rep-a"))
    assert [item["memo_id"] for item in result["items"]] == ["own-1"]
    assert result["has_more"] is True


async def test_no_conversations_is_complete_and_a_failed_read_is_unavailable(monkeypatch):
    _patch_viewer(monkeypatch)
    empty = await execute_tool("list_conversations", {"contact_id": "nobody"}, _ctx(_conversation_store(), "rep-a"))
    assert empty["coverage"] == "complete"
    assert empty["items"] == []
    broken = _conversation_store()
    broken.broken.add("memos")
    failed = await execute_tool("list_conversations", {}, _ctx(broken, "rep-a"))
    assert failed["coverage"] == "unavailable"
    assert failed["items"] == []


def _pattern(memo_id, category, *, resolution="open", superseded=False, days=1, text="es caro"):
    return {
        "memo_id": memo_id,
        "pattern_id": f"objection:{text}",
        "category": category,
        "kind": "objection",
        "resolution": resolution,
        "superseded": superseded,
        "created_at": _ago(days=days),
    }


def _objection_store():
    store = _conversation_store()
    store.tables["interaction_patterns"] = [
        _pattern("own-1", "price"),
        _pattern("own-old", "price", resolution="resolved", text="no hay presupuesto"),
        _pattern("own-old", "timing", superseded=True),
        _pattern("teammate", "timing", text="ahora no"),
        _pattern("teammate", "timing", text="en enero"),
        _pattern("foreign-user", "trust", text="no me fío"),
        _pattern("own-1", "authority", days=200, text="lo decide mi jefe"),
    ]
    return store


async def test_a_member_sees_the_objections_of_their_own_calls(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_objections", {}, _ctx(_objection_store(), "rep-a"))
    assert result["coverage"] == "complete"
    assert result["scope"] == "me"
    assert result["conversations"] == 2
    assert result["categories"] == [
        {"name": "price", "count": 2, "resolved": 1, "open": 1, "unknown": 0, "examples": ["es caro", "no hay presupuesto"]},
    ]


async def test_an_admin_sees_team_objections_ordered_by_frequency(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_objections", {"days": 90}, _ctx(_objection_store(), "boss"))
    assert result["scope"] == "team"
    names = [(item["name"], item["count"]) for item in result["categories"]]
    assert names == [("price", 2), ("timing", 2)]
    assert "trust" not in str(result)


async def test_a_member_cannot_ask_for_a_teammates_objections(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_objections", {"user_id": "rep-b"}, _ctx(_objection_store(), "rep-a"))
    assert result["ok"] is False
    assert result["coverage"] == "forbidden"


async def test_objections_without_readable_patterns_are_unavailable(monkeypatch):
    _patch_viewer(monkeypatch)
    store = _objection_store()
    store.broken.add("interaction_patterns")
    result = await execute_tool("get_objections", {}, _ctx(store, "rep-a"))
    assert result["coverage"] == "unavailable"
    assert result["categories"] == []


def _priority_row(contact_id, owner, **payload):
    return {
        "company_id": CO,
        "connection_id": "crm-A",
        "contact_id": contact_id,
        "deal_id": "",
        "owner_user_id": owner,
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": _ago(hours=0.1),
        "payload": {"contact_name": f"Contacto {contact_id}", **payload},
    }


def _priority_store(connected=True):
    connections = [{"id": "crm-A", "company_id": CO, "provider": "hubspot", "status": "connected", "metadata": {"portal_id": "1"}}] if connected else []
    return _Store(
        crm_connections=connections,
        contact_priority_context=[
            _priority_row("p-1", "rep-a", contacted=False),
            _priority_row("p-2", "rep-a", contacted=True, last_call_at=_ago(days=2)),
            _priority_row("p-3", "rep-b", contacted=False),
        ],
        memos=[_memo("m-pain", "rep-a", contact="p-2", intelligence={"pain_confirmed": True})],
    )


async def test_priorities_are_the_callers_own_list(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_call_priorities", {}, _ctx(_priority_store(), "rep-a"))
    assert result["coverage"] == "complete"
    ids = [item["contact_id"] for item in result["items"]]
    assert ids == ["p-2", "p-1"]
    assert result["items"][0]["reason"] == "pain_agree_next_step"
    assert result["items"][0]["contact_name"] == "Contacto p-2"
    assert result["items"][1]["reason"] == "no_calls_logged"
    assert "p-3" not in str(result)


async def test_an_admin_gets_their_own_priorities_not_the_teams(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_call_priorities", {}, _ctx(_priority_store(), "boss"))
    assert result["items"] == []
    assert "p-1" not in str(result)


async def test_priorities_without_a_crm_are_unavailable_not_empty(monkeypatch):
    _patch_viewer(monkeypatch)
    result = await execute_tool("get_call_priorities", {}, _ctx(_priority_store(connected=False), "rep-a"))
    assert result["coverage"] == "unavailable"
    assert result["items"] == []
