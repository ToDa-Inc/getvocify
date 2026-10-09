"""A desktop recording knows who spoke from its channels (mic = rep = S1): the call reading keeps
that instead of guessing the roles from what was said."""

import asyncio
from types import SimpleNamespace

from app.api import memos as memos_api
from app.services.intelligence.call_reading import keep_channel_roles, split_turns

# The prospect (S2) opens the call and gives the facts; the rep (S1, the mic) asks.
CALL = (
    "SPEAKER: S2\nHola, ¿qué tal? ¿Se me escucha bien?\n\n"
    "SPEAKER: S1\nSí, hola.\n\n"
    "SPEAKER: S2\nTengo cinco SDRs y cinco AEs, y estamos con Pipedrive.\n\n"
    "SPEAKER: S1\n¿Cuántos comerciales tenías?\n\n"
    "SPEAKER: S2\nDiez en total.\n\n"
    "SPEAKER: S1\nVale, ¿cuándo quedamos?"
)
FLIPPED = {"call_type": "meeting_confirmation", "rep_turns": [1, 3, 5], "other_turns": [2, 4, 6], "roles_marked": True}


def test_the_mic_side_is_the_rep_whatever_the_reading_guessed():
    kept = keep_channel_roles(split_turns(CALL), FLIPPED)
    assert kept["rep_turns"] == [2, 4, 6] and kept["other_turns"] == [1, 3, 5]
    assert kept["roles_from"] == "channels" and kept["call_type"] == "meeting_confirmation"


def test_labels_that_cant_tell_the_sides_apart_leave_the_reading_alone():
    one_side = "SPEAKER: S1\nHola.\n\nSPEAKER: S1\nAdiós."
    assert keep_channel_roles(split_turns(one_side), FLIPPED) is FLIPPED
    no_rep = "SPEAKER: S2\nHola.\n\nSPEAKER: S3\nAdiós."
    assert keep_channel_roles(split_turns(no_rep), FLIPPED) is FLIPPED


class _DB:
    def table(self, _name):
        rows = [{"id": "memo-1", "company_id": "company-1", "user_id": "user-1", "hubspot_contact_id": None, "created_at": "2026-10-07"}]
        chain = SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))
        chain.select = chain.eq = chain.limit = lambda *_a, **_k: chain
        return chain


def _read(monkeypatch, verified: bool):
    async def read_call(transcript, *_a, **_k):
        return dict(FLIPPED), "relabeled by the model", {}

    monkeypatch.setattr("app.services.feature_flags.is_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("app.services.intelligence.call_reading.read_call", read_call)
    monkeypatch.setattr("app.services.intelligence.extract.call_context", lambda *_a, **_k: {})
    monkeypatch.setattr("app.services.playbooks.type_classifier.reading_playbooks", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.llm.LLMClient", lambda *_a, **_k: object())
    return asyncio.run(memos_api._read_call_first(_DB(), "memo-1", CALL, profile={}, call_date=None, speakers_verified=verified))


def test_a_channel_recording_reaches_extraction_with_the_prospect_as_them(monkeypatch):
    reading, transcript = _read(monkeypatch, verified=True)
    assert reading["rep_turns"] == [2, 4, 6]
    assert "Them: Tengo cinco SDRs y cinco AEs, y estamos con Pipedrive." in transcript
    assert "You: ¿Cuántos comerciales tenías?" in transcript


def test_other_sources_keep_the_reading_as_it_came(monkeypatch):
    reading, transcript = _read(monkeypatch, verified=False)
    assert reading["rep_turns"] == [1, 3, 5] and transcript == "relabeled by the model"


class _PinnedDB(_DB):
    def __init__(self, pin_source):
        self.pin_source = pin_source

    def table(self, _name):
        meta = {"playbook_pin": {"source": self.pin_source}} if self.pin_source else None
        rows = [{"id": "memo-1", "company_id": "company-1", "user_id": "user-1", "hubspot_contact_id": None,
                 "created_at": "2026-10-07", "pipeline_meta": meta}]
        chain = SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))
        chain.select = chain.eq = chain.limit = lambda *_a, **_k: chain
        return chain


def _read_pinned(monkeypatch, pin_source, verified=True):
    calls = []

    async def read_call(transcript, *_a, **_k):
        calls.append(transcript)
        return dict(FLIPPED), "relabeled by the model", {}

    monkeypatch.setattr("app.services.feature_flags.is_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("app.services.intelligence.call_reading.read_call", read_call)
    monkeypatch.setattr("app.services.intelligence.extract.call_context", lambda *_a, **_k: {})
    monkeypatch.setattr("app.services.playbooks.type_classifier.reading_playbooks", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.llm.LLMClient", lambda *_a, **_k: object())
    result = asyncio.run(
        memos_api._read_call_first(_PinnedDB(pin_source), "memo-1", CALL, profile={}, call_date=None, speakers_verified=verified)
    )
    return result, calls


def test_a_channel_call_with_the_islands_type_is_not_read_before_extraction(monkeypatch):
    for source in ("live", "manual"):
        (reading, transcript), calls = _read_pinned(monkeypatch, source)
        assert reading is None and transcript == CALL and calls == []


def test_a_channel_call_without_a_type_from_the_island_is_still_read(monkeypatch):
    for source in (None, "role_default", "rule"):
        (reading, _), calls = _read_pinned(monkeypatch, source)
        assert reading is not None and len(calls) == 1


def test_a_call_without_channel_roles_is_read_even_with_the_islands_type(monkeypatch):
    (reading, _), calls = _read_pinned(monkeypatch, "live", verified=False)
    assert reading is not None and len(calls) == 1
