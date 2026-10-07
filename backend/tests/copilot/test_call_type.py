"""The call type during a live call: a free guess at the start, one AI proposal once the
conversation says enough, and live help grounded in the type the call ends up with."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.copilot import call_type
from tests.playbooks.live_double import TablesWithLiveView

COMPANY = "co-1"
USER = "user-1"


class _Chain:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eq: dict[str, str] = {}
        self._neq: dict[str, str] = {}
        self._in: dict[str, set[str]] = {}
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value):
        self._eq[column] = str(value)
        return self

    def neq(self, column: str, value):
        self._neq[column] = str(value)
        return self

    def in_(self, column: str, values):
        self._in[column] = {str(v) for v in values}
        return self

    def order(self, column: str, desc: bool = False):
        self._order = (column, desc)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self):
        rows = [
            dict(row) for row in self._rows
            if all(str(row.get(k)) == v for k, v in self._eq.items())
            and all(str(row.get(k)) != v for k, v in self._neq.items())
            and all(str(row.get(k)) in wanted for k, wanted in self._in.items())
        ]
        if self._order:
            column, desc = self._order
            rows.sort(key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


class _FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = TablesWithLiveView(tables)

    def table(self, name: str):
        return _Chain(self._tables.get(name, []))


def _published(motion: str, version_id: str, steps: list[str]) -> tuple[dict, dict]:
    playbook = {"id": f"pb-{motion}", "company_id": COMPANY, "sales_motion_key": motion, "active_version_id": version_id}
    version = {
        "id": version_id,
        "playbook_id": f"pb-{motion}",
        "status": "published",
        "steps": [{"step_id": label.lower(), "label": label, "criterion": "x"} for label in steps],
        "entries": [],
    }
    return playbook, version


def _company() -> _FakeSupabase:
    discovery, discovery_v = _published("discovery", "pv-disc", ["Pain", "Next meeting"])
    closing, closing_v = _published("closing", "pv-close", ["Demo", "Proposal"])
    return _FakeSupabase({"playbooks": [discovery, closing], "playbook_versions": [discovery_v, closing_v]})


# --- the free guess at the start --------------------------------------------------------------------


def test_the_last_conversation_with_the_contact_wins_over_the_rule():
    assert call_type.provisional_type("closing", "discovery", {"discovery", "closing"}) == ("closing", "history")


def test_a_last_type_that_is_no_longer_published_falls_back_to_the_rule():
    assert call_type.provisional_type("negotiation", "discovery", {"discovery", "closing"}) == ("discovery", "rule")


def test_an_internal_last_conversation_says_nothing_about_a_customer_call():
    assert call_type.provisional_type("internal", "discovery", {"discovery", "closing"}) == ("discovery", "rule")


def test_no_history_and_no_rule_is_no_guess():
    assert call_type.provisional_type(None, None, {"discovery"}) == (None, None)
    assert call_type.provisional_type(None, "closing", {"discovery"}) == (None, None)


def test_last_contact_type_is_the_newest_memo_about_that_contact():
    fake = _FakeSupabase({"memos": [
        {"company_id": COMPANY, "hubspot_contact_id": "c-1", "sales_motion_key": "discovery", "created_at": "2026-09-01", "status": "approved"},
        {"company_id": COMPANY, "hubspot_contact_id": "c-1", "sales_motion_key": "closing", "created_at": "2026-09-20", "status": "approved"},
        {"company_id": COMPANY, "hubspot_contact_id": "c-1", "sales_motion_key": "negotiation", "created_at": "2026-09-25", "status": "failed"},
        {"company_id": COMPANY, "hubspot_contact_id": "c-2", "sales_motion_key": "negotiation", "created_at": "2026-09-30", "status": "approved"},
    ]})
    assert call_type.last_contact_type(fake, COMPANY, "c-1") == "closing"
    assert call_type.last_contact_type(fake, COMPANY, "c-9") is None
    assert call_type.last_contact_type(fake, COMPANY, None) is None


# --- the AI proposal ---------------------------------------------------------------------------------


def test_the_proposal_offers_only_the_published_types_with_their_steps():
    types = call_type.published_types(_company(), COMPANY, {"discovery": "Discovery", "closing": "Demo y cierre", "other": "X"})
    assert [t["key"] for t in types] == ["closing", "discovery"]
    assert types[0] == {"key": "closing", "label": "Demo y cierre", "steps": ["Demo", "Proposal"]}
    messages = call_type.proposal_messages("Them: ¿qué incluye la demo?", types)
    prompt = json.dumps(messages, ensure_ascii=False)
    assert "Demo y cierre" in prompt and "Next meeting" in prompt and "¿qué incluye la demo?" in prompt
    assert "other" not in prompt


def test_a_proposal_must_name_a_published_type():
    published = {"discovery", "closing"}
    assert call_type.parse_proposal({"type": "closing", "confident": True}, published) == ("closing", True)
    assert call_type.parse_proposal({"type": "discovery"}, published) == ("discovery", False)
    assert call_type.parse_proposal({"type": "negotiation", "confident": True}, published) is None
    assert call_type.parse_proposal({"type": "internal", "confident": True}, published) is None
    assert call_type.parse_proposal({}, published) is None


# --- live help grounded in the call's type -------------------------------------------------------------


def test_live_help_uses_the_playbook_of_the_type_it_is_given():
    grounding = call_type.grounding_for_type(_company(), COMPANY, "closing", "call")
    assert grounding is not None
    assert grounding.playbook_version_id == "pv-close"
    assert grounding.interaction_kind == "call"
    assert call_type.grounding_for_type(_company(), COMPANY, "negotiation", "call") is None


# --- HTTP -------------------------------------------------------------------------------------------


def _client(fake, monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_supabase] = lambda: fake
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m-1", company_id=COMPANY, user_id=USER, role="member", status="active",
    )
    from app.services import extraction_context

    monkeypatch.setattr(extraction_context, "load_product_context", lambda *_a, **_k: "")
    monkeypatch.setattr(copilot_api, "load_company_knowledge", lambda *_a, **_k: None)
    return TestClient(app)


def _events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_an_internal_call_gets_no_live_help_and_asks_no_model(monkeypatch):
    async def never(**_kwargs):
        raise AssertionError("the model must not be asked about an internal call")
        yield  # pragma: no cover

    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", never)
    response = _client(_company(), monkeypatch).post("/api/v1/copilot/suggest", json={
        "transcript_window": "Them: ¿cuánto cuesta?", "latest_turn": "¿cuánto cuesta?",
        "call_mode": "meeting", "speaker_role": "prospect", "sales_motion_key": "internal",
    })
    assert response.status_code == 200
    result = next(event for event in _events(response) if event["type"] == "result")
    assert result["suggestion"]["is_objection"] is False


def test_suggest_grounds_help_in_the_type_the_call_has(monkeypatch):
    seen = {}

    async def fake_stream(**kwargs):
        seen["grounding"] = kwargs["grounding"]
        yield {"type": "result", "suggestion": {"is_objection": False}}

    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
    response = _client(_company(), monkeypatch).post("/api/v1/copilot/suggest", json={
        "transcript_window": "Them: ¿cuánto cuesta?", "latest_turn": "¿cuánto cuesta?",
        "call_mode": "softphone", "speaker_role": "prospect", "sales_motion_key": "closing",
    })
    assert response.status_code == 200
    assert seen["grounding"].playbook_version_id == "pv-close"
    assert seen["grounding"].interaction_kind == "call"


def test_guess_endpoint_names_the_type_and_why(monkeypatch):
    monkeypatch.setattr(call_type, "rule_type", lambda *_a, **_k: "discovery")
    monkeypatch.setattr(call_type, "last_contact_type", lambda *_a, **_k: "closing")
    response = _client(_company(), monkeypatch).post(
        "/api/v1/copilot/call-type/guess", json={"interaction_kind": "call", "contact_id": "c-1"},
    )
    assert response.status_code == 200
    assert response.json() == {"type": "closing", "source": "history"}


def test_propose_endpoint_returns_a_published_type_or_nothing(monkeypatch):
    async def fake_ask(messages):
        return {"type": "closing", "confident": True}

    monkeypatch.setattr(call_type, "ask_model", fake_ask)
    client = _client(_company(), monkeypatch)
    body = {"transcript_window": "Them: enséñame la demo", "options": [{"key": "discovery", "label": "Discovery"}, {"key": "closing", "label": "Demo y cierre"}]}
    response = client.post("/api/v1/copilot/call-type/propose", json=body)
    assert response.status_code == 200
    assert response.json() == {"type": "closing", "confident": True}

    async def made_up(messages):
        return {"type": "negotiation", "confident": True}

    monkeypatch.setattr(call_type, "ask_model", made_up)
    assert client.post("/api/v1/copilot/call-type/propose", json=body).json() == {"type": None, "confident": False}


def test_an_objection_with_no_line_is_asked_once_more_without_the_playbook(monkeypatch):
    calls = []

    async def fake_stream(**kwargs):
        calls.append(kwargs["grounding"])
        if len(calls) == 1:
            yield {"type": "result", "suggestion": {"is_objection": True, "objection_type": "trust", "say_this": ""}}
        else:
            yield {"type": "token", "text": '{"is_objection": true'}
            yield {"type": "result", "suggestion": {"is_objection": True, "objection_type": "trust", "say_this": "¿Qué os preocupa que escriba mal?"}}

    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
    response = _client(_company(), monkeypatch).post("/api/v1/copilot/suggest", json={
        "transcript_window": "Them: me da miedo que la IA escriba mal", "latest_turn": "me da miedo que la IA escriba mal",
        "call_mode": "meeting", "speaker_role": "prospect", "sales_motion_key": "closing",
    })
    results = [event for event in _events(response) if event["type"] == "result"]
    assert len(calls) == 2 and calls[0] is not None and calls[1] is None
    assert results[-1]["suggestion"]["say_this"] == "¿Qué os preocupa que escriba mal?"
    assert len(results) == 1, "the empty answer is never sent: the island would show and withdraw it"


# --- types by channel ---------------------------------------------------------------------------

from app.services.playbooks import channel_types  # noqa: E402

BY_CHANNEL_TYPES = {
    "discovery": {"status": "published", "label": None, "applies_to": None},  # catalog: call
    "inbound_lead": {"status": "missing", "label": "Lead inbound", "recognize": "Someone who asked us to call.",
                     "applies_to": {"role": "any", "channels": ["call"], "contact": "any", "deal_stages": []}},
    "closing": {"status": "published", "label": None, "applies_to": None},  # catalog: meeting
}


def _by_channel(monkeypatch):
    monkeypatch.setattr(channel_types, "enabled", lambda *_a, **_k: True)
    monkeypatch.setattr(channel_types, "_types", lambda *_a, **_k: BY_CHANNEL_TYPES)


def test_by_channel_the_guess_ignores_a_last_type_of_the_other_channel(monkeypatch):
    _by_channel(monkeypatch)
    monkeypatch.setattr(call_type, "last_contact_type", lambda *_a, **_k: "closing")
    response = _client(_company(), monkeypatch).post(
        "/api/v1/copilot/call-type/guess", json={"interaction_kind": "call", "contact_id": "c-1"},
    )
    assert response.json() == {"type": None, "source": None}


def test_by_channel_the_guess_takes_a_last_type_of_this_channel_even_without_a_playbook(monkeypatch):
    _by_channel(monkeypatch)
    monkeypatch.setattr(call_type, "last_contact_type", lambda *_a, **_k: "inbound_lead")
    response = _client(_company(), monkeypatch).post(
        "/api/v1/copilot/call-type/guess", json={"interaction_kind": "call", "contact_id": "c-1"},
    )
    assert response.json() == {"type": "inbound_lead", "source": "history"}


def test_by_channel_the_proposal_offers_the_channels_types_described(monkeypatch):
    _by_channel(monkeypatch)
    seen = {}

    async def fake_ask(messages):
        seen["prompt"] = messages[1]["content"]
        return {"type": "inbound_lead", "confident": True}

    monkeypatch.setattr(call_type, "ask_model", fake_ask)
    body = {
        "transcript_window": "Them: rellené el formulario",
        "interaction_kind": "call",
        "options": [{"key": "discovery", "label": "Llamada en frío"}, {"key": "inbound_lead", "label": "Lead inbound"},
                    {"key": "closing", "label": "Cierre"}],
    }
    response = _client(_company(), monkeypatch).post("/api/v1/copilot/call-type/propose", json=body)
    assert response.json() == {"type": "inbound_lead", "confident": True}
    assert 'key "inbound_lead"' in seen["prompt"] and "Someone who asked us to call." in seen["prompt"]
    assert 'key "closing"' not in seen["prompt"]
