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


def test_database_tick_does_not_classify_or_publish_without_a_job():
    from app.services.intelligence.worker import install_intelligence_tick, make_database_tick

    class Result:
        def __init__(self, data):
            self.data = data

        def execute(self):
            return self

    class Client:
        def __init__(self, rows):
            self.rows = rows
            self.rpc_names = []

        def rpc(self, name, _params):
            self.rpc_names.append(name)
            return Result(self.rows)

        def table(self, _name):
            raise AssertionError("no memo read without a claim")

    calls = {"classify": 0}

    def classify(_memo):
        calls["classify"] += 1
        return {"answers": {}}

    client = Client([])
    assert make_database_tick(client, classify)() is None
    assert client.rpc_names == ["claim_memo_job"]
    assert calls["classify"] == 0
    install_intelligence_tick()
    from app.services.intelligence import worker as worker_mod
    assert worker_mod._worker_tick is None


def test_a_claimed_job_publishes_with_job_and_run_and_a_missing_memo_does_not():
    from app.services.intelligence.worker import make_database_tick, run_claimed

    published = []

    def classify(_memo):
        return {"status": "unavailable", "answers": {}}

    missing = run_claimed(
        lambda: {"job_id": "job-1", "run_id": "run-1", "memo_id": "memo-1"},
        lambda _memo_id: None,
        lambda *_args: published.append(_args),
        classify,
        lambda _memo: {},
    )
    assert missing == {"outcome": "missing_memo", "published": False}
    assert published == []

    outcome = run_claimed(
        lambda: {"job_id": "job-1", "run_id": "run-1", "memo_id": "memo-1"},
        lambda _memo_id: MEMO,
        lambda job_id, run_id, payload: published.append((job_id, run_id, payload["status"])),
        classify,
        lambda _memo: {},
    )
    assert outcome["published"] is True
    assert published == [("job-1", "run-1", "unavailable")]

    class Result:
        def __init__(self, data):
            self.data = data

        def execute(self):
            return self

    class Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return Result([])

    class Client:
        def __init__(self):
            self.rpc_names = []

        def rpc(self, name, _params):
            self.rpc_names.append(name)
            if name == "claim_memo_job":
                return Result([{
                    "job_id": "job-1",
                    "claimed_run_id": "run-1",
                    "claimed_memo_id": "memo-1",
                    "claimed_revision": "rev",
                }])
            return Result("published")

        def table(self, _name):
            return Query()

    client = Client()
    assert make_database_tick(client, classify)()["published"] is False
    assert client.rpc_names == ["claim_memo_job"]


def test_startup_tick_does_not_claim_without_an_api_key(monkeypatch):
    from app.config import settings
    from app.services.intelligence import worker as worker_mod
    from app.services.intelligence.worker import install_intelligence_tick, set_worker_tick

    monkeypatch.setattr(settings, "INTELLIGENCE_WORKER_PUBLISH", True)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    def boom():
        raise AssertionError("supabase")

    monkeypatch.setattr("app.deps.get_supabase", boom)
    install_intelligence_tick()
    try:
        assert worker_mod._worker_tick is not None
        assert asyncio.run(worker_mod._worker_tick()) is None
    finally:
        set_worker_tick(None)


def test_an_async_classifier_publishes_the_claimed_job():
    from app.services.intelligence.worker import run_claimed_awaiting

    published = []

    async def classify(_memo):
        return {"status": "unavailable", "answers": {}}

    outcome = asyncio.run(run_claimed_awaiting(
        lambda: {"job_id": "job-1", "run_id": "run-1", "memo_id": "memo-1"},
        lambda _memo_id: MEMO,
        lambda job_id, run_id, payload: published.append((job_id, run_id, payload["status"])),
        classify,
        lambda _memo: {},
    ))
    assert outcome["published"] is True
    assert published == [("job-1", "run-1", "unavailable")]


def test_stored_intelligence_keeps_the_revision_and_a_failed_write_does_not_publish():
    from app.services.intelligence.interpret import extraction_with_intelligence
    from app.services.intelligence.worker import run_claimed

    payload = {"version": 1, "status": "unavailable", "pain_confirmed": None}
    merged = extraction_with_intelligence(MEMO["extraction"], payload)
    assert merged["summary"] == "Quiere el caso"
    assert merged["intelligence"]["pain_confirmed"] is None
    updated = {**MEMO, "extraction": merged}
    assert revision_for_memo(updated) == revision_for_memo(MEMO)
    job = enqueue_plan(MEMO, [])
    assert sweep_missing([updated], [job]) == []

    published = []

    def explode(_memo, _payload):
        raise RuntimeError("down")

    try:
        run_claimed(
            lambda: {"job_id": "job-1", "run_id": "run-1", "memo_id": "memo-1"},
            lambda _memo_id: MEMO,
            lambda *_args: published.append(_args),
            lambda _memo: {"status": "unavailable", "answers": {}},
            lambda _memo: {},
            explode,
        )
    except RuntimeError:
        pass
    assert published == []

    class Result:
        def __init__(self, data):
            self.data = data

        def execute(self):
            return self

    class Client:
        def __init__(self, publish_data):
            self.publish_data = publish_data
            self.updates = []

        def rpc(self, name, _params):
            if name == "claim_memo_job":
                return Result([{
                    "job_id": "job-1",
                    "claimed_run_id": "run-1",
                    "claimed_memo_id": "memo-1",
                    "claimed_revision": "rev",
                }])
            return Result(self.publish_data)

        def table(self, _name):
            client = self

            class Table:
                def select(self, *_args, **_kwargs):
                    return self

                def eq(self, *_args, **_kwargs):
                    return self

                def limit(self, *_args, **_kwargs):
                    return self

                def update(self, row):
                    client.updates.append(row)
                    return self

                def execute(self):
                    return Result([MEMO])

            return Table()

    from app.services.intelligence.worker import make_database_tick

    client = Client("success")
    outcome = make_database_tick(client, lambda _memo: {"status": "unavailable", "answers": {}})()
    assert outcome["outcome"] == "success"
    assert client.updates[0]["extraction"]["summary"] == "Quiere el caso"
    assert client.updates[0]["extraction"]["intelligence"]["pain_confirmed"] is None
