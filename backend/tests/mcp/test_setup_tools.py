"""The setup tools over HTTP: who may edit, drafts vs publishing, what an answer says changed, the API's error codes,
and edit access on API keys and OAuth sign-ins. Playbooks live in the in-memory repository the playbooks tests use."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_supabase, get_user_id  # the real dependencies, before the db fixture patches get_supabase
# The modules the setup tools call, imported now so they bind the real get_supabase (not the db fixture's).
import app.api.auth  # noqa: E402,F401
import app.api.company  # noqa: E402,F401
import app.api.playbook_company  # noqa: E402,F401
import app.api.playbook_rules  # noqa: E402,F401
import app.api.playbooks  # noqa: E402,F401
from tests.mcp.conftest import COMPANY, MANAGER, REP, call, rpc
from tests.mcp.test_oauth_http import (  # noqa: F401 - `server` is a fixture
    CLAUDE_CALLBACK,
    authorization_id,
    authorize,
    exchange_code,
    pkce,
    register,
    server,
)

SETUP_TOOLS = {
    "get_setup", "save_call_type", "save_playbook_draft", "publish_playbook", "set_playbook_state",
    "save_playbook_conduct", "update_company",
}
WRITE_TOOLS = SETUP_TOOLS - {"get_setup"}
STEPS = [
    {"label": "Apertura con permiso", "criterion": "Pide unos segundos antes de contar nada."},
    {"label": "Descubrir el dolor", "criterion": "Pregunta cómo lo hacen hoy."},
]


@pytest.fixture(autouse=True)
def stores(db):
    from app.services.playbooks.conduct import InMemoryConductStore, set_conduct_store
    from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository

    repository = InMemoryPlaybookRepository()
    set_playbook_repository(repository)
    set_conduct_store(InMemoryConductStore())
    db.tables["companies"] = [{"id": COMPANY, "name": "Acme Sales", "product_context": "", "auto_create_contact_company": False}]
    yield repository
    set_playbook_repository(None)
    set_conduct_store(None)


@pytest.fixture
def company_settings(monkeypatch, db):
    """GET /company reads billing and seats this fake database does not have: Settings' values come from the row."""
    from app.services.company import CompanyService
    from app.services.mcp import setup

    async def read(supabase, membership):
        row = next(r for r in db.tables["companies"] if r["id"] == membership.company_id)
        return {
            "name": row.get("name"), "sales_strategy": None, "callback_after_days": None, "followup_cadence": None,
            "auto_create_contact_company": bool(row.get("auto_create_contact_company")),
        }

    async def update_company(body, user_id, supabase):
        if body.name:
            CompanyService(supabase).update_company_name(COMPANY, body.name)

    monkeypatch.setattr(setup, "_company_settings", read)
    monkeypatch.setattr("app.api.company.update_company", update_company)


@pytest.fixture
def write_key_for(db):
    from app.services.mcp import api_keys

    return lambda user_id: api_keys.generate_key(db, user_id, write=True)["key"]


def ok(client, token, tool, arguments=None):
    is_error, body = call(client, token, tool, arguments)
    assert not is_error, body
    return body


def refused(client, token, tool, arguments=None) -> str:
    is_error, text = call(client, token, tool, arguments)
    assert is_error, text
    prefix = f"Error executing tool {tool}: "  # the SDK's
    return text[len(prefix):] if text.startswith(prefix) else text


# ----- listing and access -----------------------------------------------------------------------------


def test_the_setup_tools_are_listed_and_only_get_setup_is_read_only(mcp_client, key_for):
    tools = {t["name"]: t for t in rpc(mcp_client, key_for(REP), "tools/list").json()["result"]["tools"]}
    assert SETUP_TOOLS <= set(tools)
    assert tools["get_setup"]["annotations"]["readOnlyHint"] is True
    for name in WRITE_TOOLS:
        assert tools[name]["annotations"]["readOnlyHint"] is False, name
        assert "coach" in tools[name]["description"] or "live" in tools[name]["description"], name


def test_a_read_only_key_reads_the_setup_but_cannot_edit_it(mcp_client, key_for, stores, company_settings):
    key = key_for(MANAGER)
    assert key.startswith("vk_")
    body = ok(mcp_client, key, "get_setup")
    assert body["can_edit"] is True and body["connection_can_edit"] is False
    text = refused(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS})
    assert "read-only" in text and "Settings → AI agents" in text
    assert stores.list_types(COMPANY) == {}


def test_a_write_key_of_a_rep_is_refused_with_the_apis_code(mcp_client, write_key_for, stores):
    text = refused(mcp_client, write_key_for(REP), "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS})
    assert "Only owners and admins" in text  # told plainly, not sent to reconnect
    assert stores.list_types(COMPANY) == {}


# ----- playbooks: type, draft, publish, state ------------------------------------------------------------


def test_a_manager_creates_a_type_drafts_it_and_publishes_only_when_asked(mcp_client, write_key_for, company_settings):
    key = write_key_for(MANAGER)
    created = ok(mcp_client, key, "save_call_type", {"sales_motion_key": "discovery", "name": "Llamada en frío"})
    assert created["created"] is True and created["type"]["state"]

    saved = ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS})
    assert saved["changed"]["steps"]["added"] == ["apertura_con_permiso", "descubrir_el_dolor"]
    assert saved["playbook"]["source"] == "draft" and saved["playbook"]["has_live"] is False

    live = ok(mcp_client, key, "get_setup", {"sales_motion_key": "discovery"})
    assert live["playbook"]["source"] == "draft"
    assert ok(mcp_client, key, "get_setup")["playbooks"]["motions"]["discovery"] != "published"

    published = ok(mcp_client, key, "publish_playbook", {"sales_motion_key": "discovery"})
    assert published["state"] == "published" and published["version_id"]
    assert published["playbook"]["source"] == "published"


def test_a_list_left_out_keeps_what_the_draft_has_and_a_sent_one_replaces_it(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS})
    answer = {"category": "price", "guidance": "Pregunta con qué lo comparan.", "trigger": "Es caro"}
    saved = ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "objections": [answer]})
    assert saved["changed"] == {"objections": {"added": ["price"]}}
    assert [s["step_id"] for s in saved["playbook"]["steps"]] == ["apertura_con_permiso", "descubrir_el_dolor"]

    one = [{**saved["playbook"]["steps"][1], "criterion": "Pregunta cómo lo hacen hoy y repregunta."}]
    saved = ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": one})
    assert saved["changed"] == {"steps": {"removed": ["apertura_con_permiso"], "changed": ["descubrir_el_dolor"]}}
    assert saved["playbook"]["objections"][0]["guidance"] == "Pregunta con qué lo comparan."


def test_an_edit_on_top_of_a_moved_draft_is_stale(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    first = ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS})
    ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS[:1]})
    text = refused(mcp_client, key, "save_playbook_draft", {
        "sales_motion_key": "discovery", "steps": STEPS, "base_updated_at": first["playbook"]["updated_at"],
    })
    assert text.startswith("stale_draft:") and "get_setup" in text


def test_the_normalizers_codes_come_back_with_where(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    text = refused(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": [{"label": "x" * 81}]})
    assert text.startswith("label_too_long:") and "index 0" in text
    text = refused(mcp_client, key, "save_playbook_draft", {
        "sales_motion_key": "discovery", "steps": STEPS, "objections": [{"category": "weather", "guidance": "?"}],
    })
    assert text.startswith("bad_category:")
    assert refused(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": []}).startswith("no_steps:")


def test_publishing_without_a_draft_and_bad_lifecycle_moves_say_why(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    ok(mcp_client, key, "save_call_type", {"sales_motion_key": "discovery"})
    assert refused(mcp_client, key, "publish_playbook", {"sales_motion_key": "discovery"}).startswith("no_draft:")
    assert refused(mcp_client, key, "set_playbook_state", {"sales_motion_key": "discovery", "action": "resume"}).startswith("not_paused:")


def test_pause_resume_delete_restore_and_discard(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS})
    ok(mcp_client, key, "publish_playbook", {"sales_motion_key": "discovery"})
    paused = ok(mcp_client, key, "set_playbook_state", {"sales_motion_key": "discovery", "action": "pause"})
    assert paused["state"] == {"before": "published", "after": "paused"}
    assert ok(mcp_client, key, "set_playbook_state", {"sales_motion_key": "discovery", "action": "resume"})["state"]["after"] == "published"
    gone = ok(mcp_client, key, "set_playbook_state", {"sales_motion_key": "discovery", "action": "delete"})
    assert gone["state"]["after"] is None
    assert ok(mcp_client, key, "set_playbook_state", {"sales_motion_key": "discovery", "action": "restore"})["state"]["after"] == "published"

    ok(mcp_client, key, "save_playbook_draft", {"sales_motion_key": "discovery", "steps": STEPS[:1]})
    discarded = ok(mcp_client, key, "set_playbook_state", {"sales_motion_key": "discovery", "action": "discard_draft"})
    assert discarded["playbook"]["source"] == "published" and len(discarded["playbook"]["steps"]) == 2


def test_a_types_rule_is_validated_by_the_api(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    ok(mcp_client, key, "save_call_type", {"sales_motion_key": "discovery"})
    rule = {"role": "sdr", "channels": ["call"], "contact": "inbound", "deal_stages": []}
    changed = ok(mcp_client, key, "save_call_type", {"sales_motion_key": "discovery", "applies_to": rule})
    assert changed["created"] is False and changed["type"]["applies_to"]["contact"] == "inbound"
    assert "applies_to" in changed["changed"]
    bad = refused(mcp_client, key, "save_call_type", {"sales_motion_key": "discovery", "applies_to": {"contact": "warm"}})
    assert bad.startswith("bad_rule:")
    text = refused(mcp_client, key, "save_call_type", {"sales_motion_key": "discovery", "name": "Fría"})
    assert text.startswith("type_edit_unavailable:")  # this workspace has no types by channel


# ----- «Cómo trabajamos» -------------------------------------------------------------------------------------


def test_conduct_parts_left_out_keep_what_is_stored(mcp_client, write_key_for):
    key = write_key_for(MANAGER)
    ok(mcp_client, key, "save_playbook_conduct", {
        "sales_motion_key": "discovery", "goal": "Una demo con alguien con necesidad real",
        "core": [{"name": "Principio", "text": "Una pregunta cada vez."}],
    })
    saved = ok(mcp_client, key, "save_playbook_conduct", {"sales_motion_key": "discovery", "criteria": ["cuando dice que es caro → pregunta con qué compara"]})
    assert saved["changed"] == {"criteria": "changed"}
    conduct = ok(mcp_client, key, "get_setup", {"sales_motion_key": "discovery"})["conduct"]
    assert conduct["goal"] == "Una demo con alguien con necesidad real"
    assert conduct["core"][0]["name"] == "Principio" and len(conduct["criteria"]) == 1


# ----- the company -----------------------------------------------------------------------------------------


def test_knowledge_sections_sent_replace_those_only_and_go_through_normalize(mcp_client, write_key_for, company_settings):
    key = write_key_for(MANAGER)
    first = ok(mcp_client, key, "update_company", {"knowledge": {"icp": "  Startups B2B   con SDRs ", "competitors": [{"name": "Gong", "how_to_talk": "Más caro"}]}})
    assert first["changed"] == {"knowledge": ["icp", "competitors"]}
    assert first["company_knowledge"]["knowledge"]["icp"] == "Startups B2B con SDRs"
    second = ok(mcp_client, key, "update_company", {
        "knowledge": {"pricing": "Desde 49 €/usuario"}, "base_updated_at": first["company_knowledge"]["updated_at"],
    })
    assert second["changed"] == {"knowledge": ["pricing"]}
    assert second["company_knowledge"]["knowledge"]["competitors"][0]["name"] == "Gong"
    text = refused(mcp_client, key, "update_company", {"knowledge": {"icp": "x"}, "base_updated_at": first["company_knowledge"]["updated_at"]})
    assert text.startswith("stale_knowledge:")
    assert refused(mcp_client, key, "update_company", {"knowledge": {"mission": "x"}}).startswith("invalid:")


def test_the_offer_and_settings_are_written_where_the_dashboard_writes_them(mcp_client, write_key_for, company_settings, db):
    key = write_key_for(MANAGER)
    body = ok(mcp_client, key, "update_company", {"offer": "Vocify: coaching de llamadas.", "settings": {"auto_create_contact_company": True, "name": "Acme"}})
    row = db.tables["companies"][0]
    assert row["product_context"] == "Vocify: coaching de llamadas." and row["auto_create_contact_company"] is True and row["name"] == "Acme"
    assert body["changed"]["offer"] is True and set(body["changed"]["settings"]) == {"auto_create_contact_company", "name"}
    assert ok(mcp_client, key, "get_setup")["offer"] == "Vocify: coaching de llamadas."
    assert refused(mcp_client, key, "update_company", {"settings": {"seat_limit": 99}}).startswith("invalid:")


def test_a_rep_with_a_write_key_changes_nothing_of_the_company(mcp_client, write_key_for, company_settings, db):
    text = refused(mcp_client, write_key_for(REP), "update_company", {"offer": "x", "knowledge": {"icp": "y"}})
    assert "Only owners and admins" in text
    assert db.tables["companies"][0]["product_context"] == ""


# ----- edit access: API keys --------------------------------------------------------------------------------


@pytest.fixture
def as_user(db):
    from app.api import mcp_access

    def client_for(user_id: str) -> TestClient:
        app = FastAPI()
        app.include_router(mcp_access.router)
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_user_id] = lambda: user_id
        return TestClient(app, headers={"Authorization": "Bearer session-token"})

    return client_for


def test_only_an_owner_or_admin_makes_an_edit_key_and_a_plain_key_stays_read_only(as_user):
    assert as_user(REP).post("/api/v1/mcp/key", json={"write": True}).status_code == 403
    assert as_user(REP).get("/api/v1/mcp/settings").json()["can_grant_write"] is False
    made = as_user(MANAGER).post("/api/v1/mcp/key", json={"write": True}).json()
    assert made["key"].startswith("vkw_") and made["can_write"] is True
    plain = as_user(MANAGER).post("/api/v1/mcp/key").json()  # what the dashboard sent before edit access existed
    assert plain["key"].startswith("vk_") and plain["can_write"] is False


# ----- edit access: OAuth sign-in ---------------------------------------------------------------------------


def _sign_in(server, *, user, allow_write):
    client_id = register(server)
    verifier, challenge = pkce()
    aid = authorization_id(authorize(server, client_id, challenge=challenge))
    server.who["id"] = user
    asked = server.get(f"/api/v1/oauth/authorizations/{aid}").json()
    consent = server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve", "allow_write": allow_write})
    if consent.status_code != 200:
        return asked, consent, None
    code = parse_qs(urlparse(consent.json()["redirect_url"]).query)["code"][0]
    token = exchange_code(server, client_id, code, verifier, CLAUDE_CALLBACK).json()["access_token"]
    return asked, consent, token


def test_an_app_signed_in_without_edits_reads_only(server, mcp_client):
    asked, _, token = _sign_in(server, user=MANAGER, allow_write=False)
    assert asked["can_allow_write"] is True
    assert "read-only" in refused(mcp_client, token, "save_call_type", {"sales_motion_key": "discovery"})


def test_an_app_the_manager_allowed_to_edit_can_and_the_grant_says_so(server, mcp_client):
    _, _, token = _sign_in(server, user=MANAGER, allow_write=True)
    assert ok(mcp_client, token, "save_call_type", {"sales_motion_key": "discovery"})["created"] is True
    assert server.get("/api/v1/oauth/grants").json()["grants"][0]["can_write"] is True


def test_a_rep_cannot_let_an_app_edit(server):
    asked, consent, _ = _sign_in(server, user=REP, allow_write=True)
    assert asked["can_allow_write"] is False and consent.status_code == 403


def test_an_app_connected_before_edit_access_existed_stays_read_only_and_says_where_to_allow_edits(mcp_client, oauth_token_for):
    token = oauth_token_for(MANAGER)  # a grant with no `write`
    text = refused(mcp_client, token, "save_call_type", {"sales_motion_key": "discovery"})
    assert "Claude is connected to Vocify read-only" in text and "Allow edits" in text
    assert "/dashboard/settings/agents" in text and "No need to reconnect" in text


def test_a_manager_allows_edits_on_an_app_already_connected_without_reconnecting(server, mcp_client, oauth_token_for, db):
    from app.services.mcp import oauth

    token = oauth_token_for(MANAGER)
    server.who["id"] = MANAGER
    client_id = server.get("/api/v1/oauth/grants").json()["grants"][0]["client"]["client_id"]
    turned_on = server.patch(f"/api/v1/oauth/grants?client_id={client_id}", json={"can_write": True})
    assert turned_on.status_code == 200 and turned_on.json()["grants"][0]["can_write"] is True
    oauth._grants_cache.clear()  # the instance that serves /mcp sees it within the cache's 30 s
    assert ok(mcp_client, token, "save_call_type", {"sales_motion_key": "discovery"})["created"] is True
    server.patch(f"/api/v1/oauth/grants?client_id={client_id}", json={"can_write": False})
    oauth._grants_cache.clear()
    assert "read-only" in refused(mcp_client, token, "save_call_type", {"sales_motion_key": "demo"})


def test_a_rep_cannot_allow_edits_on_their_app_and_an_unknown_app_is_404(server, oauth_token_for):
    oauth_token_for(REP)
    server.who["id"] = REP
    client_id = server.get("/api/v1/oauth/grants").json()["grants"][0]["client"]["client_id"]
    assert server.patch(f"/api/v1/oauth/grants?client_id={client_id}", json={"can_write": True}).status_code == 403
    assert server.patch(f"/api/v1/oauth/grants?client_id={client_id}", json={"can_write": False}).status_code == 200
    server.who["id"] = MANAGER
    assert server.patch("/api/v1/oauth/grants?client_id=nope", json={"can_write": True}).status_code == 404
