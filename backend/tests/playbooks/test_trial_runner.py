"""Running one case of the trial: the same turn check and the same card writer live help uses, fed with the DRAFT.
Nothing is published and the live code is only called, so a test compares what it sends with what the live endpoint sends."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.api import copilot
from app.api.copilot import SuggestRequest, suggest_objection_handling
from app.services.company import Membership
from app.services.copilot.grounding import SuggestGrounding
from app.services.playbooks import trial
from app.services.playbooks.trial import draft_snapshot, run_case

CASE = {"id": "c1", "source": "typical", "client_text": "Me parece caro para lo que hacéis.", "motion_key": "discovery"}
PRICE = {"entry_id": "objection:price", "category": "price", "guidance": "Pregunta cuánto pierden hoy.", "source_ref": "editor"}
EMAIL = {
    "entry_id": "objection:custom:mandame_un_email", "category": "custom", "label": "Mándame un email",
    "trigger": "Mándame un email y lo vemos", "guidance": "Pide cinco minutos antes.", "source_ref": "editor",
}
SNAPSHOT = {"sales_motion_key": "discovery", "version_id": "draft-1", "steps": [{"step_id": "apertura"}], "entries": [PRICE, EMAIL]}
KNOWLEDGE = {"value_short": "Vocify te ayuda a vender."}
CARD = {"type": "result", "suggestion": {"say_this": "Pregunta cuánto tiempo pierden.", "source_id": "objection:price", "is_objection": True}, "grounded": True}


class Spy:
    """Stands in for read_turn and stream_objection_suggestion and remembers how they were called."""

    def __init__(self, reading, events=(CARD,)):
        self.reading, self.events, self.turn_args, self.suggest_kwargs = reading, list(events), None, None

    async def read_turn(self, conversation, latest, custom=None):
        self.turn_args = (conversation, latest, custom)
        return self.reading

    async def stream(self, **kwargs):
        self.suggest_kwargs = kwargs
        for event in self.events:
            yield event


def run(spy, snapshot=SNAPSHOT, case=CASE):
    with patch.object(trial, "read_turn", spy.read_turn), patch.object(trial, "stream_objection_suggestion", spy.stream):
        return asyncio.run(run_case(case, snapshot=snapshot, knowledge=KNOWLEDGE, product_context="Software de ventas", lang="es"))


def test_the_card_is_written_from_the_draft_and_the_turn_check_knows_its_own_objections():
    spy = Spy({"finished": True, "objection": "price"})
    result = run(spy)
    grounding = spy.suggest_kwargs["grounding"]
    assert isinstance(grounding, SuggestGrounding) and grounding.playbook_snapshot == SNAPSHOT and grounding.playbook_version_id == "draft-1"
    assert spy.turn_args[2] == {"objection:custom:mandame_un_email": {"label": "Mándame un email", "trigger": "Mándame un email y lo vemos"}}
    assert result == {
        "detected": "price", "entry_id": None, "label": None, "grounded": True,
        "card": {"say_this": "Pregunta cuánto tiempo pierden.", "source_id": "objection:price", "objection_type": "price"},
    }


def test_a_fixed_kind_goes_through_and_an_unknown_one_does_not():
    spy = Spy({"finished": True, "objection": "weird"})
    run(spy)
    assert spy.suggest_kwargs["objection_type"] is None


def test_the_teams_own_objection_is_followed_through_its_entry():
    spy = Spy({"finished": True, "objection": "custom", "entry_id": EMAIL["entry_id"], "label": "Mándame un email"})
    result = run(spy, case={**CASE, "client_text": "Mándame un email y lo vemos"})
    assert spy.suggest_kwargs["objection_type"] is None and spy.suggest_kwargs["entry"] == EMAIL
    assert result["detected"] == "custom" and result["entry_id"] == EMAIL["entry_id"] and result["label"] == "Mándame un email"


def test_when_the_turn_check_sees_nothing_live_help_would_show_nothing():
    spy = Spy({"finished": True, "objection": "none"})
    result = run(spy)
    assert result == {"detected": "none", "entry_id": None, "label": None, "card": None, "grounded": False}
    assert spy.suggest_kwargs is None


def test_when_the_turn_check_cannot_be_reached_the_card_writer_is_asked_directly():
    spy = Spy({"finished": None, "objection": None})
    run(spy)
    assert spy.suggest_kwargs["objection_type"] is None and spy.suggest_kwargs["entry"] is None


def test_no_result_or_an_empty_line_means_no_card():
    assert run(Spy({"objection": "price"}, events=[{"type": "token", "text": "x"}]))["card"] is None
    empty = {"type": "result", "suggestion": {"say_this": "", "is_objection": True}, "grounded": False}
    assert run(Spy({"objection": "price"}, events=[empty]))["card"] is None


def test_a_draft_is_turned_into_the_snapshot_live_help_reads():
    editor = {"version": {"id": "v-9", "steps": [{"step_id": "apertura"}], "entries": [PRICE], "qualification": []}}
    assert draft_snapshot(editor, "discovery") == {
        "sales_motion_key": "discovery", "version_id": "v-9", "steps": [{"step_id": "apertura"}], "entries": [PRICE], "qualification": [],
    }
    empty = draft_snapshot({"version": None}, "discovery")
    assert empty["entries"] == [] and empty["version_id"] == "draft" and empty["sales_motion_key"] == "discovery"


# --- the trial asks the card writer exactly what the live endpoint asks it ---------------------------------


def _live_kwargs(objection_type, entry_id):
    seen: dict = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield {"type": "result", "suggestion": {}}

    grounding = SuggestGrounding(interaction_kind="call", playbook_version_id="draft-1", evidence_ids=frozenset(), playbook_snapshot=SNAPSHOT)
    member = Membership(id="m-1", company_id="co-1", user_id="u-1", role="owner", status="active")
    body = SuggestRequest(
        transcript_window=f"Them: {CASE['client_text']}", latest_turn=CASE["client_text"], call_mode="softphone",
        speaker_role="prospect", sales_motion_key="discovery", objection_type=objection_type, entry_id=entry_id,
    )

    async def go():
        with (
            patch.object(copilot, "stream_objection_suggestion", fake_stream),
            patch("app.services.extraction_context.load_product_context", return_value="Software de ventas"),
            patch.object(copilot, "load_company_knowledge", return_value=KNOWLEDGE),
            patch.object(copilot.call_type, "grounding_for_type", return_value=grounding),
        ):
            response = await suggest_objection_handling(body, membership=member, supabase=MagicMock())
            async for _ in response.body_iterator:
                pass

    asyncio.run(go())
    return seen


def test_the_trial_sends_what_the_live_endpoint_sends():
    keys = ("objection_type", "entry", "call_mode", "speaker_role", "language", "company_knowledge", "product_context", "latest_turn", "transcript_window")
    for reading, live_type, live_entry in (
        ({"objection": "price"}, "price", None),
        ({"objection": "custom", "entry_id": EMAIL["entry_id"]}, None, EMAIL["entry_id"]),
        ({"objection": None}, None, None),
    ):
        spy = Spy(reading)
        run(spy)
        ours, live = spy.suggest_kwargs, _live_kwargs(live_type, live_entry)
        assert {k: ours[k] for k in keys} == {k: live[k] for k in keys}, reading
        assert ours["grounding"].playbook_snapshot == live["grounding"].playbook_snapshot
        assert ours["grounding"].interaction_kind == live["grounding"].interaction_kind
