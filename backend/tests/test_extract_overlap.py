"""extract_memo_async repairs the transcript while it reads the call and extracts: the memo is ready
as soon as the slower of the two is done, with the fixes applied to the transcript and the note."""

import asyncio
import time
from types import SimpleNamespace

import pytest

from app.api import memos as memos_api
from app.services import transcript_patch as tp

TRANSCRIPT = (
    "SPEAKER: S1\nHola, soy Toni de Voicify, te llamo por el seguimiento de la propuesta que te envié ayer.\n\n"
    "SPEAKER: S2\nSí, la vi, déjame revisarla con el equipo y te cuento la semana que viene."
)
MEMO_ID, USER_ID = "memo-1", "user-1"


class FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_k):
        return self

    eq = limit = select

    def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeDB:
    def table(self, _name):
        return FakeTable([{"transcript_stt_meta": None, "created_at": "2026-10-07T10:00:00", "source": "web", "source_type": "web"}])


class FakeExtraction:
    seconds = 0.05
    fail = False

    def model_dump(self):
        return {"summary": "Llamada sobre Voicify", "next_steps": ["Revisar Voicify"], "crm_fields": {}}

    async def extract(self, transcript, *_a, **_k):
        self.seen = transcript
        self.world.extraction_started.set()
        # Extraction only gets past this point if the repair has already started: overlap, not sequence.
        await asyncio.wait_for(self.world.patch_started.wait(), timeout=2)
        await asyncio.sleep(self.seconds)
        if self.fail:
            raise RuntimeError("extraction down")
        return self


@pytest.fixture
def world(monkeypatch):
    w = SimpleNamespace(updates=[], stages=None, patch_cancelled=False, patch_text=None, patch_after=None,
                        patch_started=None, extraction_started=None)

    def update_memo_row(_db, memo_id, payload):
        w.updates.append(payload)

    async def glossary(*_a, **_k):
        return []

    async def context(*_a, **_k):
        return "", {}

    async def read_first(_db, _memo, transcript, **_k):
        await asyncio.sleep(0.2)
        return None, transcript

    async def patch(text, terms, roles, **_k):
        w.patch_started.set()
        try:
            if w.patch_after is not None:
                await w.patch_after()
            else:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            w.patch_cancelled = True
            raise
        return tp.PatchResult(text=text.replace("Voicify", "Vocify") if w.patch_text is None else w.patch_text,
                              edits=[("Voicify", "Vocify")], model="m", provider="together")

    def persist(_db, _memo, stages, **_k):
        w.stages = list(stages)

    nothing = lambda *_a, **_k: None  # noqa: E731
    monkeypatch.setattr("app.services.pipeline_lease.update_memo_row", update_memo_row)
    monkeypatch.setattr("app.services.pipeline_meta.persist_pipeline_meta", persist)
    monkeypatch.setattr("app.services.glossary.GlossaryService.get_user_glossary", glossary, raising=False)
    monkeypatch.setattr("app.services.extraction_context.load_extraction_llm_context", context)
    monkeypatch.setattr("app.services.session_entities.load_stt_profile", lambda *_a, **_k: {"full_name": "Toni"})
    monkeypatch.setattr(memos_api, "_read_call_first", read_first)
    monkeypatch.setattr(memos_api, "schedule_followup", nothing)
    monkeypatch.setattr("app.services.playbooks.type_classifier.apply_reading_type", nothing)
    monkeypatch.setattr("app.services.memo_extraction_hooks.run_post_extraction_hooks", nothing)
    monkeypatch.setattr("app.services.intelligence.worker.record_enqueue", nothing)

    async def no_approve(*_a, **_k):
        return None

    monkeypatch.setattr("app.services.hubspot.auto_sync.maybe_auto_approve_hubspot_call", no_approve)
    monkeypatch.setattr(tp, "patch_transcript", patch)
    return w


def run(world, extraction=None):
    extraction = extraction or FakeExtraction()

    async def go():
        world.patch_started, world.extraction_started = asyncio.Event(), asyncio.Event()
        extraction.world = world
        await memos_api.extract_memo_async(
            MEMO_ID, USER_ID, TRANSCRIPT, FakeDB(), extraction, None, source_type="web", run_id="run-1",
        )

    started = time.perf_counter()
    asyncio.run(go())
    return time.perf_counter() - started, extraction


def test_the_repair_starts_before_reading_and_extracting_are_done(world):
    run(world)  # FakeExtraction.extract waits for the repair to have started and times out otherwise
    assert world.patch_started.is_set() and world.extraction_started.is_set()


def test_extraction_reads_the_rule_cleaned_text_and_the_fixes_reach_the_transcript_and_the_note(world):
    _, extraction = run(world)
    assert "Voicify" in extraction.seen  # it started before the repair finished
    transcript_updates = [u["transcript"] for u in world.updates if "transcript" in u]
    assert transcript_updates and "Vocify" in transcript_updates[-1] and "Voicify" not in transcript_updates[-1]
    final = next(u for u in world.updates if u.get("status") == "pending_review")
    assert final["extraction"]["summary"] == "Llamada sobre Vocify"
    assert final["extraction"]["next_steps"] == ["Revisar Vocify"]


def test_the_stages_show_where_the_time_went_and_that_the_repair_was_hidden(world):
    async def finished_long_ago():
        await world.extraction_started.wait()  # done as soon as extraction has started

    world.patch_after = finished_long_ago
    run(world)
    stages = {s["name"]: s for s in world.stages}
    assert {"context", "sanitize", "reading", "finish"} <= set(stages)
    assert stages["sanitize"]["provider"] == "together" and stages["sanitize"]["waited_ms"] < 150
    assert stages["sanitize"]["edits_applied"] == 1 and "rules_ms" in stages["sanitize"]


def test_a_slow_repair_makes_the_memo_wait_for_it(world):
    async def after_extraction():
        await world.extraction_started.wait()
        await asyncio.sleep(0.4)  # still running when extraction is long done

    world.patch_after = after_extraction
    run(world)
    stage = {s["name"]: s for s in world.stages}["sanitize"]
    assert stage["waited_ms"] >= 100 and stage["edits_applied"] == 1


def test_when_extraction_fails_the_repair_is_cancelled_and_the_memo_fails(world):
    extraction = FakeExtraction()
    extraction.fail = True
    async def forever():
        await asyncio.sleep(30)

    world.patch_after = forever
    with pytest.raises(RuntimeError):
        run(world, extraction)
    assert world.patch_cancelled
    assert any(u.get("status") == "failed" for u in world.updates)


def test_a_repair_that_finds_nothing_leaves_the_transcript_as_it_was(world, monkeypatch):
    async def nothing(text, terms, roles, **_k):
        world.patch_started.set()
        return tp.PatchResult(text=text)

    monkeypatch.setattr(tp, "patch_transcript", nothing)
    run(world)
    assert not [u for u in world.updates if "transcript" in u]
    final = next(u for u in world.updates if u.get("status") == "pending_review")
    assert final["extraction"]["summary"] == "Llamada sobre Voicify"  # nothing was fixed, so nothing is rewritten
