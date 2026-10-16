"""The guided questions ("Lo que falta"): one session per company, each answer applied to the draft through the same
"Dile a Vocify" path the editor uses, and every step reversible. Nothing reaches the team until it is published."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.services.company import Membership
from app.services.playbooks.api_support import StructureRequest, set_playbook_transcriber
from app.services.playbooks.assistant import (
    AssistantError,
    answer_gap,
    public_session,
    skip_gap,
    start_gaps_session,
    undo_gap,
)
from app.services.playbooks.assistant_store import InMemoryAssistantStore
from app.services.playbooks.fill import FillError
from app.services.playbooks.gaps import Gap
from app.services.playbooks.repository import InMemoryPlaybookRepository
from app.services.playbooks.structure import set_playbook_structure_llm
from app.services.playbooks.versions import StaleDraftError
from tests.playbooks.test_structure import FakeLLM
from tests.reporting.fake_db import FakeDB

COMPANY = "co-1"
MEMBER = Membership(id="m", company_id=COMPANY, user_id="u-1", role="owner", status="active", sales_role=None)
STEP = {"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta y pide un minuto."}
ADDED = {
    "summary": "Añadida la respuesta a «Integración con Salesforce».",
    "objections": [{
        "category": "custom", "label": "Integración con Salesforce", "trigger": "¿Se integra con Salesforce?",
        "guidance": "Sí, con Salesforce y HubSpot.",
    }],
}
ANSWER = StructureRequest(kind="text", payload="Sí, con Salesforce y HubSpot.")
EVENTS = [
    {"id": "e1", "latest_turn": "¿Se integra con Salesforce?", "is_objection": True, "source_id": None, "sales_motion_key": "discovery"},
]


@pytest.fixture(autouse=True)
def _reset():
    yield
    set_playbook_structure_llm(None)
    set_playbook_transcriber(None)


@pytest.fixture
def world():
    repo = InMemoryPlaybookRepository()
    repo.save_draft(COMPANY, "discovery", [STEP], [])
    return repo, InMemoryAssistantStore(), FakeDB()


def start(world, **kwargs):
    repo, store, db = world
    kwargs.setdefault("events", EVENTS)
    return asyncio.run(start_gaps_session(store, repo, db, MEMBER, motion_key="discovery", lang="es", **kwargs))


def answer(world, session, gap_key, source=ANSWER):
    repo, store, db = world
    return asyncio.run(answer_gap(store, repo, db, MEMBER, session_id=session["id"], gap_key=gap_key, source=source))


def draft_labels(repo, key="discovery"):
    version = repo.editor_snapshot(COMPANY, key, include_draft=True)["version"]
    return [e.get("label") or e["category"] for e in version["entries"]]


def test_a_session_holds_at_most_ten_gaps_and_the_open_one_is_reused(world):
    session = start(world)
    view = public_session(session)
    assert 1 <= view["total"] <= 10 and view["answered"] == 0 and view["status"] == "open"
    assert view["current"]["kind"] == "real" and view["current"]["example"] == "¿Se integra con Salesforce?"
    assert start(world)["id"] == session["id"]


def test_answering_a_gap_adds_the_own_question_to_the_draft(world):
    set_playbook_structure_llm(FakeLLM(ADDED))
    session = start(world)
    gap_key = public_session(session)["current"]["key"]
    done = answer(world, session, gap_key)
    assert done["saved_line"] == ADDED["summary"]
    assert draft_labels(world[0]) == ["Integración con Salesforce"]
    assert done["session"]["answered"] == 1 and done["session"]["current"]["key"] != gap_key
    assert [s["step_id"] for s in done["editor"]["steps"]] == ["apertura"]


def test_a_company_with_no_playbook_gets_the_call_type_created(world):
    repo, store, db = InMemoryPlaybookRepository(), InMemoryAssistantStore(), FakeDB()
    set_playbook_structure_llm(FakeLLM(ADDED))
    session = asyncio.run(start_gaps_session(store, repo, db, MEMBER, motion_key="discovery", lang="es", events=EVENTS))
    key = public_session(session)["current"]["key"]
    asyncio.run(answer_gap(store, repo, db, MEMBER, session_id=session["id"], gap_key=key, source=ANSWER))
    assert draft_labels(repo) == ["Integración con Salesforce"]


def test_skipping_changes_nothing_and_moves_on(world):
    session = start(world)
    first = public_session(session)["current"]["key"]
    view = skip_gap(world[1], MEMBER, session_id=session["id"], gap_key=first)
    assert view["skipped"] == 1 and view["current"]["key"] != first
    assert draft_labels(world[0]) == []


def test_undo_restores_the_draft_and_brings_the_question_back(world):
    set_playbook_structure_llm(FakeLLM(ADDED))
    session = start(world)
    key = public_session(session)["current"]["key"]
    answer(world, session, key)
    view = undo_gap(world[1], world[0], MEMBER, session_id=session["id"], gap_key=key)
    assert draft_labels(world[0]) == [] and view["answered"] == 0 and view["current"]["key"] == key
    with pytest.raises(AssistantError) as caught:
        undo_gap(world[1], world[0], MEMBER, session_id=session["id"], gap_key=key)
    assert caught.value.code == "nothing_to_undo"


def test_audio_without_speech_leaves_the_session_as_it_was(world):
    set_playbook_transcriber(lambda _payload: "")
    session = start(world)
    key = public_session(session)["current"]["key"]
    with pytest.raises(HTTPException) as caught:
        answer(world, session, key, StructureRequest(kind="audio", payload="AAAA"))
    assert caught.value.detail == {"code": "audio_has_no_speech"}
    assert world[1].get_session(COMPANY, session["id"])["state"]["answered"] == {}


def test_a_model_that_changes_nothing_is_a_failure_not_a_silent_save(world):
    set_playbook_structure_llm(FakeLLM({"summary": "Nada que cambiar."}))
    session = start(world)
    with pytest.raises(FillError):
        answer(world, session, public_session(session)["current"]["key"])
    assert draft_labels(world[0]) == []


class _StaleOnce(InMemoryPlaybookRepository):
    def __init__(self, times):
        super().__init__()
        self.times = times

    def save_draft(self, *args, **kwargs):
        if kwargs.get("base_updated_at") and self.times > 0:
            self.times -= 1
            raise StaleDraftError()
        return super().save_draft(*args, **kwargs)


def _stale_world(times):
    repo = _StaleOnce(times)
    repo.save_draft(COMPANY, "discovery", [STEP], [])
    return repo, InMemoryAssistantStore(), FakeDB()


def test_a_draft_that_moved_meanwhile_is_retried_once(world):
    stale = _stale_world(1)
    set_playbook_structure_llm(FakeLLM(ADDED))
    session = start(stale)
    answer(stale, session, public_session(session)["current"]["key"])
    assert draft_labels(stale[0]) == ["Integración con Salesforce"]


def test_two_conflicts_in_a_row_keep_what_the_boss_said_for_a_retry():
    stale = _stale_world(2)
    set_playbook_structure_llm(FakeLLM(ADDED))
    session = start(stale)
    key = public_session(session)["current"]["key"]
    with pytest.raises(StaleDraftError):
        answer(stale, session, key)
    assert stale[1].get_session(COMPANY, session["id"])["state"]["pending"][key] == "Sí, con Salesforce y HubSpot."
    assert public_session(stale[1].get_session(COMPANY, session["id"]))["pending_text"] == "Sí, con Salesforce y HubSpot."


def test_the_last_answer_closes_the_session(world):
    set_playbook_structure_llm(FakeLLM(ADDED))
    session = start(world, events=[], limit=1)
    key = public_session(session)["current"]["key"]
    done = answer(world, session, key)
    assert done["session"]["status"] == "done" and done["session"]["current"] is None


def test_a_conflict_is_settled_through_the_company_notes_and_can_be_undone(world):
    repo = world[0]
    repo.save_knowledge(COMPANY, {"pricing": "Desde 39 € al mes por usuario."})
    conflict = Gap("conflict:pricing", "conflict", "Dos precios", "settle pricing", 0, None, None)
    set_playbook_structure_llm(FakeLLM({"summary": "Precio corregido.", "set": {"pricing": "Desde 49 € al mes por usuario."}}))
    session = start(world, events=[], conflicts=[conflict], limit=1)
    done = answer(world, session, "conflict:pricing", StructureRequest(kind="text", payload="El bueno es 49 euros."))
    assert done["saved_line"] == "Precio corregido."
    assert repo.get_knowledge(COMPANY)["data"]["pricing"] == "Desde 49 € al mes por usuario."
    undo_gap(world[1], repo, MEMBER, session_id=session["id"], gap_key="conflict:pricing")
    assert repo.get_knowledge(COMPANY)["data"]["pricing"] == "Desde 39 € al mes por usuario."


def test_unknown_sessions_and_gaps_are_refused(world):
    with pytest.raises(AssistantError) as caught:
        skip_gap(world[1], MEMBER, session_id="nope", gap_key="x")
    assert caught.value.code == "session_not_found"
    session = start(world)
    with pytest.raises(AssistantError) as caught:
        skip_gap(world[1], MEMBER, session_id=session["id"], gap_key="nope")
    assert caught.value.code == "gap_not_found"
