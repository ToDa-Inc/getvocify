"""A WhatsApp visit note goes through the same post-extraction hooks as every other capture."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.models.memo import MemoExtraction
from app.services.whatsapp import processor

MEMO_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _Memos:
    def __init__(self, db: "_DB"):
        self.db = db
        self._insert = None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def insert(self, row):
        self._insert = dict(row)
        return self

    def execute(self):
        if self._insert is not None:
            if self.db.insert_race:
                self.db.insert_race = False
                self.db.existing = [{"id": MEMO_ID, "extraction": MemoExtraction().model_dump()}]
                raise RuntimeError('duplicate key value violates unique constraint "23505"')
            self.db.inserted.append(self._insert)
            return SimpleNamespace(data=[{"id": MEMO_ID, **self._insert}])
        return SimpleNamespace(data=list(self.db.existing))


class _DB:
    def __init__(self, *, existing: list[dict] | None = None, insert_race: bool = False):
        self.existing = list(existing or [])
        self.insert_race = insert_race
        self.inserted: list[dict] = []

    def table(self, _name):
        return _Memos(self)


class _Extraction:
    async def extract(self, *_a, **_k):
        return MemoExtraction(summary="Visita a Ferretería Sol")


class _Glossary:
    def __init__(self, *_a, **_k):
        pass

    async def get_user_glossary(self, _user_id):
        return []


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple] = []

    async def field_specs(*_a, **_k):
        return None

    def hooks(_supabase, *, memo_id, extraction, memo=None):
        seen.append(("hooks", memo_id, extraction.get("summary")))

    async def auto_approve(_supabase, memo_id, user_id):
        seen.append(("auto_approve", memo_id, user_id))
        return False

    monkeypatch.setattr(processor, "get_field_specs", field_specs)
    monkeypatch.setattr(processor, "GlossaryService", _Glossary)
    monkeypatch.setattr(processor, "ExtractionService", _Extraction)
    monkeypatch.setattr(processor, "with_author_company", lambda _s, row: row)
    monkeypatch.setattr("app.services.extraction_context.load_product_context", lambda *_a, **_k: "")
    monkeypatch.setattr("app.services.session_entities.load_stt_profile", lambda *_a, **_k: {})
    monkeypatch.setattr(
        "app.services.transcript_sanitize.prepare_transcript_for_extraction",
        lambda transcript, *_a, **_k: (transcript, ""),
    )
    monkeypatch.setattr("app.services.transcript_sanitize.schedule_transcript_polish", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.followup.schedule_followup", lambda *_a, **_k: False)
    monkeypatch.setattr("app.services.pipeline_lease.update_memo_row", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.intelligence.worker.record_enqueue", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.memo_extraction_hooks.run_post_extraction_hooks", hooks)
    monkeypatch.setattr("app.services.hubspot.auto_sync.maybe_auto_approve_hubspot_call", auto_approve)
    return seen


async def _drain():
    await asyncio.gather(*list(processor._POST_EXTRACTION_TASKS), return_exceptions=True)


async def _create(db):
    return await processor._extract_and_create_memo(
        db, "user-1", "Salgo de la visita a Ferretería Sol, les interesa.", "wamid.1", None, None
    )


async def test_an_extracted_note_runs_the_hooks_once_then_auto_approve(calls):
    db = _DB()
    memo_id, extraction = await _create(db)
    assert memo_id == MEMO_ID
    assert extraction is not None
    await _drain()
    assert calls == [
        ("hooks", MEMO_ID, "Visita a Ferretería Sol"),
        ("auto_approve", MEMO_ID, "user-1"),
    ]


async def test_memo_creation_returns_before_the_hooks_run(calls):
    memo_id, _ = await _create(_DB())
    assert memo_id == MEMO_ID
    assert calls == []
    await _drain()
    assert [name for name, *_ in calls] == ["hooks", "auto_approve"]


@pytest.mark.parametrize(
    "target",
    [
        "app.services.pipeline_lease.update_memo_row",
        "app.services.transcript_sanitize.schedule_transcript_polish",
        "app.services.followup.schedule_followup",
    ],
)
async def test_hooks_still_run_when_a_step_after_the_insert_fails(monkeypatch, calls, target):
    def broken(*_a, **_k):
        raise RuntimeError("step down")

    monkeypatch.setattr(target, broken)
    await _create(_DB())
    await _drain()
    assert [name for name, *_ in calls] == ["hooks", "auto_approve"]


async def test_a_whatsapp_note_is_stamped_as_a_visit(calls):
    db = _DB()
    await _create(db)
    await _drain()
    assert db.inserted[0]["interaction_kind"] == "visit"


async def test_a_retried_message_does_not_run_the_hooks_again(calls):
    db = _DB(existing=[{"id": MEMO_ID, "extraction": MemoExtraction().model_dump()}])
    memo_id, _ = await _create(db)
    await _drain()
    assert memo_id == MEMO_ID
    assert calls == []


async def test_losing_the_insert_race_does_not_run_the_hooks(calls):
    db = _DB(insert_race=True)
    memo_id, _ = await _create(db)
    await _drain()
    assert memo_id == MEMO_ID
    assert calls == []


async def test_a_hook_failure_is_logged_and_does_not_block_auto_approve(monkeypatch, calls, caplog):
    def broken(*_a, **_k):
        raise RuntimeError("hooks down")

    monkeypatch.setattr("app.services.memo_extraction_hooks.run_post_extraction_hooks", broken)
    caplog.set_level(logging.ERROR)
    memo_id, _ = await _create(_DB())
    await _drain()
    assert memo_id == MEMO_ID
    assert calls == [("auto_approve", MEMO_ID, "user-1")]
    assert any("post-extraction" in record.getMessage() for record in caplog.records)


async def test_an_auto_approve_failure_is_logged(monkeypatch, calls, caplog):
    async def broken(*_a, **_k):
        raise RuntimeError("crm down")

    monkeypatch.setattr("app.services.hubspot.auto_sync.maybe_auto_approve_hubspot_call", broken)
    caplog.set_level(logging.ERROR)
    memo_id, _ = await _create(_DB())
    await _drain()
    assert memo_id == MEMO_ID
    assert [name for name, *_ in calls] == ["hooks"]
    assert any("auto-approve" in record.getMessage() for record in caplog.records)


# --- Real hooks over a WhatsApp memo without a contact: the F14 rule, unchanged. ---


class _Query:
    def __init__(self, tables: dict, name: str):
        self.tables = tables
        self.name = name
        self.filters: list[tuple[str, str]] = []
        self._payload = None
        self._delete = False
        self._limit = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, str(value)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._payload = payload
        return self

    upsert = insert

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        rows = list(self.tables.setdefault(self.name, []))
        hit = [row for row in rows if all(str(row.get(c)) == v for c, v in self.filters)]
        if self._delete:
            self.tables[self.name] = [row for row in rows if row not in hit]
            return SimpleNamespace(data=hit)
        if self._payload is not None:
            self.tables[self.name].append(dict(self._payload))
            return SimpleNamespace(data=[self._payload])
        return SimpleNamespace(data=hit[: self._limit] if self._limit else hit)


class _Tables:
    def __init__(self, memo: dict):
        self.tables: dict[str, list] = {"memos": [memo], "meeting_proposals": [], "memo_scores": []}

    def table(self, name):
        return _Query(self.tables, name)


def _whatsapp_memo(transcript: str, extraction: dict) -> dict:
    return {
        "id": MEMO_ID,
        "user_id": "user-1",
        "company_id": "co-1",
        "source": "whatsapp",
        "interaction_kind": "visit",
        "hubspot_contact_id": None,
        "hubspot_deal_id": None,
        "matched_deal_id": None,
        "transcript": transcript,
        "extraction": extraction,
    }


def _current(memo: dict, base: dict, meeting: dict) -> dict:
    from app.services.intelligence.extract import PROMPT_VERSION
    from app.services.intelligence.worker import revision_for_memo

    revision = revision_for_memo({**memo, "extraction": base})
    return {
        **base,
        "intelligence": {
            "version": 1,
            "input_revision": revision,
            "prompt_version": PROMPT_VERSION,
            "meeting": meeting,
            "evidence": [],
        },
    }


@pytest.fixture
def no_auto_approve(monkeypatch):
    async def auto_approve(*_a, **_k):
        return False

    monkeypatch.setattr("app.services.hubspot.auto_sync.maybe_auto_approve_hubspot_call", auto_approve)


async def test_note_without_contact_with_agreement_leaves_a_proposal_for_review(no_auto_approve):
    transcript = "Me ha dicho que sí: quedamos el jueves 1 a las 10 en su tienda."
    base = {"summary": "Visita a Ferretería Sol"}
    memo = _whatsapp_memo(transcript, base)
    booked = {
        "agreed": True,
        "starts_at": "2026-10-01T10:00:00+02:00",
        "timezone": None,
        "precision": "time",
        "evidence_refs": ["ev-jueves"],
    }
    extraction = _current(memo, base, booked)
    memo["extraction"] = extraction
    db = _Tables(memo)
    await processor._run_post_extraction(db, MEMO_ID, "user-1", extraction)
    rows = db.tables["meeting_proposals"]
    assert len(rows) == 1
    assert rows[0]["agreement"] == "agreed"
    assert rows[0]["decision"] == "pending"
    assert rows[0]["crm_status"] == "not_requested"


async def test_note_without_contact_and_without_agreement_leaves_no_proposal(no_auto_approve):
    transcript = "Visita hecha, les dejo el catálogo y ya me dirán."
    base = {"summary": "Visita a Ferretería Sol"}
    memo = _whatsapp_memo(transcript, base)
    empty = {"agreed": None, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": []}
    extraction = _current(memo, base, empty)
    memo["extraction"] = extraction
    db = _Tables(memo)
    await processor._run_post_extraction(db, MEMO_ID, "user-1", extraction)
    assert db.tables["meeting_proposals"] == []


async def test_the_followup_gets_the_company_from_the_inserted_row(monkeypatch, calls):
    seen = {}
    monkeypatch.setattr(processor, "with_author_company", lambda _s, row: {**row, "company_id": "co-1"})
    monkeypatch.setattr("app.services.followup.schedule_followup",
                        lambda _s, memo_id, **kwargs: seen.update(memo_id=memo_id, **kwargs) or False)
    await _create(_DB())
    await _drain()
    assert seen == {"memo_id": MEMO_ID, "company_id": "co-1"}
