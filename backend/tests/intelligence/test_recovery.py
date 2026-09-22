"""Recovery: a saved extraction without a job is enqueued once, on every path."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.services.intelligence.worker import (
    enqueue_plan,
    record_enqueue,
    revision_for_memo,
    start_worker,
    stop_worker,
    sweep_missing,
)

MEMO = {
    "id": "memo-1",
    "user_id": "user-1",
    "company_id": "company-1",
    "extraction": {"summary": "Quiere el caso", "nextSteps": ["Enviar caso"]},
}


def test_sweep_creates_the_missing_job_once():
    first = sweep_missing([MEMO], [])
    assert len(first) == 1
    assert first[0]["kind"] == "intelligence"
    assert first[0]["input_revision"]
    second = sweep_missing([MEMO], first)
    assert second == []


def test_three_paths_share_one_revision_and_do_not_duplicate():
    paths = [
        {**MEMO, "trigger": "extract"},
        {**MEMO, "trigger": "re_extract"},
        {**MEMO, "trigger": "whatsapp"},
    ]
    revisions = {revision_for_memo(memo) for memo in paths}
    assert len(revisions) == 1
    jobs = []
    for memo in paths:
        row = enqueue_plan(memo, jobs)
        if row:
            jobs.append(row)
    assert len(jobs) == 1


def test_record_enqueue_swallows_a_store_error():
    class Boom:
        def table(self, _name):
            raise RuntimeError("down")

    assert record_enqueue(Boom(), MEMO) is None


def test_worker_starts_once_and_stops():
    async def scenario():
        assert start_worker() is True
        assert start_worker() is False
        await stop_worker()
        assert start_worker() is True
        await stop_worker()

    asyncio.run(scenario())


def test_an_empty_claim_inside_the_worker_does_not_classify():
    from app.services.intelligence.interpret import drain_once
    from app.services.intelligence.worker import set_worker_tick

    calls = {"classify": 0}

    def classify(*_args, **_kwargs):
        calls["classify"] += 1
        return {"answers": []}

    def tick():
        return drain_once({}, lambda: None, lambda *_a, **_k: None, classify, {})

    async def scenario():
        set_worker_tick(tick)
        try:
            assert start_worker() is True
            await asyncio.sleep(0.05)
            await stop_worker()
        finally:
            set_worker_tick(None)

    asyncio.run(scenario())
    assert calls["classify"] == 0
