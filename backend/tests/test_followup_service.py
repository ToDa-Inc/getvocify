import asyncio
import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

import pytest

from app.config import settings
from app.services import feature_flags
from app.services import followup as svc
from app.services.intelligence import extract
from app.services.intelligence.worker import revision_for_memo


class FakeQuery:
    """supabase-py chain with the filters this service uses, including PostgREST's quirk
    of re-applying PATCH filters to RETURNING (what forces the confirm-by-PK read)."""

    def __init__(self, rows: list[dict]):
        self.rows, self.filters, self.ors, self.patch, self.n = rows, [], None, None, None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def or_(self, expression):
        self.ors = expression
        return self

    def limit(self, n, *_a, **_k):
        self.n = n
        return self

    def update(self, patch):
        self.patch = patch
        return self

    @staticmethod
    def _value(row, column):
        if "->>" in column:
            base, key = column.split("->>", 1)
            value = (row.get(base) or {}).get(key)
            return None if value is None else str(value)
        return row.get(column)

    def _condition(self, row, cond):
        column, op, value = cond.split(".", 2)
        current = self._value(row, column)
        if op == "is" and value == "null":
            return current is None
        if op == "lt":
            return current is not None and str(current) < value
        raise NotImplementedError(cond)

    def _match(self, row):
        if any(self._value(row, c) != v for c, v in self.filters):
            return False
        return not self.ors or any(self._condition(row, c) for c in self.ors.split(","))

    def execute(self):
        matched = [r for r in self.rows if self._match(r)]
        if self.patch is not None:
            for row in matched:
                row.update(self.patch)
            return SimpleNamespace(data=[dict(r) for r in matched if self._match(r)])
        return SimpleNamespace(data=[dict(r) for r in matched[: self.n or None]])


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables[name])


class FakeLLM:
    def __init__(self, payload=None, error=None, log=None):
        self.payload = payload or {"subject": "Caso de logística", "body": "Hola Marina, te paso el caso.", "language": "es"}
        self.error, self.calls, self.log = error, 0, log if log is not None else []

    async def chat_json(self, messages, **kwargs):
        self.calls += 1
        self.log.append("draft")
        self.messages, self.kwargs = messages, kwargs
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return self.payload


def memo_row(**overrides):
    return {
        "id": "m1", "user_id": "u1", "transcript": "Marina: me interesa el caso.",
        "extraction": {"summary": "Quiere el caso de logística", "nextSteps": ["Enviar caso"], "contactName": "Marina"},
        "screening_outcome": None, "followup": None, "followup_run_started_at": None, **overrides,
    }


def client_for(memo):
    return FakeClient({"memos": [memo], "user_profiles": [{"id": "u1", "full_name": "Lucía Pérez", "writing_samples": ["Hola X, te paso lo que hablamos."]}]})


class EnsureFollowup(unittest.TestCase):
    def setUp(self):
        settings.FOLLOWUP_ENABLED = True
        svc._live.clear()

    def tearDown(self):
        settings.FOLLOWUP_ENABLED = True

    def test_drafts_once_and_releases_the_lease(self):
        memo, llm = memo_row(), FakeLLM()
        client = client_for(memo)
        asyncio.run(svc.ensure_followup(client, "m1", llm=llm))
        self.assertEqual((memo["followup"]["status"], memo["followup"]["subject"]), ("ready", "Caso de logística"))
        self.assertIsNone(memo["followup_run_started_at"])
        self.assertIn("Lucía Pérez", llm.messages[1]["content"])
        self.assertIn("Never invent prices, dates", llm.messages[0]["content"])
        self.assertEqual(llm.kwargs["timeout"], svc.LLM_TIMEOUT_S)
        asyncio.run(svc.ensure_followup(client, "m1", llm=llm))
        self.assertEqual(llm.calls, 1, "a ready draft is never regenerated")

    def test_concurrent_calls_generate_once(self):
        memo, llm = memo_row(), FakeLLM()
        client = client_for(memo)

        async def both():
            await asyncio.gather(svc.ensure_followup(client, "m1", llm=llm), svc.ensure_followup(client, "m1", llm=llm))

        asyncio.run(both())
        self.assertEqual(llm.calls, 1)

    def test_respects_a_fresh_run_elsewhere_and_reclaims_a_stale_one(self):
        now = datetime.now(timezone.utc)
        fresh = (now - timedelta(seconds=20)).isoformat()
        llm = FakeLLM()
        busy = memo_row(followup={"status": "generating", "started_at": fresh, "run_id": "other"}, followup_run_started_at=fresh)
        asyncio.run(svc.ensure_followup(client_for(busy), "m1", llm=llm))
        self.assertEqual(llm.calls, 0)

        stale = (now - timedelta(minutes=5)).isoformat()
        dead = memo_row(followup={"status": "generating", "started_at": stale, "run_id": "dead"}, followup_run_started_at=stale)
        asyncio.run(svc.ensure_followup(client_for(dead), "m1", llm=llm))
        self.assertEqual((llm.calls, dead["followup"]["status"]), (1, "ready"))

    def test_voicemail_and_kill_switch_do_nothing(self):
        llm = FakeLLM()
        asyncio.run(svc.ensure_followup(client_for(memo_row(screening_outcome="voicemail")), "m1", llm=llm))
        settings.FOLLOWUP_ENABLED = False
        asyncio.run(svc.ensure_followup(client_for(memo_row()), "m1", llm=llm))

        async def schedule():
            return svc.schedule_followup(client_for(memo_row()), "m1", llm=llm)

        self.assertFalse(asyncio.run(schedule()), "switched off, the GET must not promise a draft")
        self.assertEqual(llm.calls, 0)

    def test_failures_mark_unavailable_and_never_raise(self):
        errored = memo_row()
        extraction_before = dict(errored["extraction"])
        asyncio.run(svc.ensure_followup(client_for(errored), "m1", llm=FakeLLM(error=TimeoutError())))
        self.assertEqual(errored["extraction"], extraction_before, "memo extraction stays available when draft fails")
        self.assertEqual((errored["followup"]["status"], errored["followup"]["reason"]), ("unavailable", "error"))
        empty = memo_row()
        asyncio.run(svc.ensure_followup(client_for(empty), "m1", llm=FakeLLM(payload={"subject": "", "body": ""})))
        self.assertEqual((empty["followup"]["status"], empty["followup"]["reason"]), ("unavailable", "empty_draft"))
        self.assertIsNone(empty["followup_run_started_at"])

    def test_schedule_is_a_noop_without_a_loop_and_completes_inside_one(self):
        memo, llm = memo_row(), FakeLLM()
        client = client_for(memo)
        self.assertFalse(svc.schedule_followup(client, "m1", llm=llm))
        self.assertIsNone(memo["followup"])

        async def scheduled():
            self.assertTrue(svc.schedule_followup(client, "m1", llm=llm))
            await asyncio.gather(*list(svc._tasks))

        asyncio.run(scheduled())
        self.assertEqual(memo["followup"]["status"], "ready")


C04_BLOCK = {
    "version": 1, "status": "ready", "interest": "high", "pain_confirmed": True, "objections": [],
    "commitments": [{
        "id": "com-a", "kind": "send", "origin": "rep_promise", "text": "Enviar el caso de logística",
        "due_at": "2026-10-01T09:00:00+00:00", "temporal_precision": "time", "evidence_refs": ["ev-a"],
    }],
    "meeting": {"agreed": True, "starts_at": "2026-10-02T09:30:00+00:00", "timezone": None,
                "precision": "time", "evidence_refs": ["ev-m"]},
    "competitor_mentions": [], "playbook_observations": [],
    "evidence": [
        {"id": "ev-p", "quote": "Perdemos leads cada semana"},
        {"id": "ev-a", "quote": "Te mando el caso el jueves"},
        {"id": "ev-m", "quote": "El viernes a las once y media"},
    ],
    "prompt_version": extract.PROMPT_VERSION,
}
TODAY_KEYS = ["rep_name", "contact_name", "summary", "next_steps", "voice_samples", "transcript"]


def c04_for(memo):
    return {**C04_BLOCK, "input_revision": revision_for_memo(memo)}


def company_memo(**overrides):
    return memo_row(company_id="co-1", **overrides)


def flags_client(memo, flags=()):
    client = client_for(memo)
    client.tables["company_feature_flags"] = [{"company_id": c, "flag": f, "enabled": e} for c, f, e in flags]
    return client


def context_of(llm):
    return json.loads(llm.messages[1]["content"])


def fake_c04(monkeypatch, memo, log, *, delay=0.02, fail=False):
    """Stands in for ensure_intelligence behind the real schedule_intelligence."""
    async def ensure(_supabase, memo_id, **_kwargs):
        await asyncio.sleep(delay)
        if fail:
            raise RuntimeError("model down")
        memo["extraction"] = {**memo["extraction"], "intelligence": c04_for(memo)}
        log.append("c04")
        return {"status": "stored"}

    monkeypatch.setattr(extract, "ensure_intelligence", ensure)


def trigger_like_memos(client, llm):
    """memos.py: schedule_followup, then run_post_extraction_hooks schedules C04 before the next await."""
    async def go():
        svc.schedule_followup(client, "m1", llm=llm)
        extract.schedule_intelligence(client, "m1", company_id="co-1")
        await asyncio.gather(*list(svc._tasks), *list(extract._tasks))

    asyncio.run(go())


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    feature_flags.clear_cache()
    svc._live.clear()
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(settings, "INTELLIGENCE_EXTRACT_ENABLED", True)
    yield
    feature_flags.clear_cache()


def test_the_draft_waits_for_c04_and_carries_its_facts(monkeypatch):
    memo, log = company_memo(), []
    client, llm = flags_client(memo), FakeLLM(log=log)
    fake_c04(monkeypatch, memo, log, delay=0.05)
    trigger_like_memos(client, llm)
    assert log == ["c04", "draft"]
    ctx = context_of(llm)
    assert ctx["commitments"] == [{"text": "Enviar el caso de logística", "day": "Thursday 2026-10-01", "time": "11:00"}]
    assert ctx["meeting"] == {"day": "Friday 2026-10-02", "time": "11:30"}
    assert ctx["pain_quote"] == "Perdemos leads cada semana"
    assert (memo["followup"]["status"], memo["followup"]["prompt_version"]) == ("ready", "followup_v2")
    assert "commitments and meeting" in llm.messages[0]["content"]


def test_whatsapp_order_also_waits_for_c04(monkeypatch):
    memo, log = company_memo(), []
    client, llm = flags_client(memo), FakeLLM(log=log)
    fake_c04(monkeypatch, memo, log, delay=0.05)

    async def go():
        async def hooks():
            extract.schedule_intelligence(client, "m1", company_id="co-1")

        hooks_task = asyncio.get_running_loop().create_task(hooks())
        svc.schedule_followup(client, "m1", llm=llm)
        await hooks_task
        await asyncio.gather(*list(svc._tasks), *list(extract._tasks))

    asyncio.run(go())
    assert log == ["c04", "draft"]
    assert context_of(llm)["meeting"] == {"day": "Friday 2026-10-02", "time": "11:30"}


def test_the_task_schedule_intelligence_creates_is_found_by_name(monkeypatch):
    memo, log = company_memo(), []
    fake_c04(monkeypatch, memo, log)

    async def go():
        assert extract.schedule_intelligence(flags_client(memo), "m1", company_id="co-1")
        found = svc._c04_task("m1")
        assert found is not None and found in extract._tasks
        assert svc._c04_task("other") is None
        await found

    asyncio.run(go())


def test_a_failed_c04_releases_the_draft_at_once(monkeypatch):
    monkeypatch.setattr(svc, "C04_WAIT_S", 5.0)
    memo, log = company_memo(), []
    client, llm = flags_client(memo), FakeLLM(log=log)
    fake_c04(monkeypatch, memo, log, delay=0.02, fail=True)
    started = time.monotonic()
    trigger_like_memos(client, llm)
    assert time.monotonic() - started < 1.0
    assert list(context_of(llm)) == TODAY_KEYS
    assert memo["followup"]["status"] == "ready"


def test_a_slow_c04_is_not_awaited_past_the_limit_nor_cancelled(monkeypatch):
    monkeypatch.setattr(svc, "C04_WAIT_S", 0.05)
    memo, log = company_memo(), []
    client, llm = flags_client(memo), FakeLLM(log=log)
    fake_c04(monkeypatch, memo, log, delay=0.4)

    async def go():
        svc.schedule_followup(client, "m1", llm=llm)
        extract.schedule_intelligence(client, "m1", company_id="co-1")
        c04 = svc._c04_task("m1")
        await asyncio.gather(*list(svc._tasks))
        drafted_first = not c04.done()
        await c04
        return drafted_first, c04.cancelled()

    assert asyncio.run(go()) == (True, False)
    assert log == ["draft", "c04"]
    assert list(context_of(llm)) == TODAY_KEYS
    assert memo["extraction"]["intelligence"]["commitments"], "C04 still lands for CRM and Hoy"


@pytest.mark.parametrize("off", ["global", "company"])
def test_with_intelligence_off_the_draft_is_todays_and_does_not_wait(monkeypatch, off):
    memo, log = company_memo(), []
    flags = []
    if off == "global":
        monkeypatch.setattr(settings, "INTELLIGENCE_EXTRACT_ENABLED", False)
    else:
        flags = [("co-1", "INTELLIGENCE_EXTRACT_ENABLED", False)]
    client, llm = flags_client(memo, flags), FakeLLM(log=log)
    fake_c04(monkeypatch, memo, log)
    trigger_like_memos(client, llm)
    assert log == ["draft"]
    assert list(context_of(llm)) == TODAY_KEYS
    assert memo["followup"]["status"] == "ready"


def test_a_current_c04_is_used_without_waiting():
    memo = company_memo()
    memo["extraction"] = {**memo["extraction"], "intelligence": c04_for(memo)}
    llm = FakeLLM()
    asyncio.run(svc.ensure_followup(flags_client(memo), "m1", llm=llm))
    assert context_of(llm)["commitments"][0]["text"] == "Enviar el caso de logística"


def test_a_stale_c04_leaves_todays_input():
    memo = company_memo()
    memo["extraction"] = {**memo["extraction"], "intelligence": {**c04_for(memo), "input_revision": "older"}}
    llm = FakeLLM()
    asyncio.run(svc.ensure_followup(flags_client(memo), "m1", llm=llm))
    assert list(context_of(llm)) == TODAY_KEYS


def test_one_draft_while_waiting_and_never_regenerated(monkeypatch):
    memo, log = company_memo(), []
    client, llm = flags_client(memo), FakeLLM(log=log)
    fake_c04(monkeypatch, memo, log, delay=0.05)

    async def go():
        svc.schedule_followup(client, "m1", llm=llm)
        svc.schedule_followup(client, "m1", llm=llm)
        extract.schedule_intelligence(client, "m1", company_id="co-1")
        await asyncio.gather(*list(svc._tasks), *list(extract._tasks))
        svc.schedule_followup(client, "m1", llm=llm)
        await asyncio.gather(*list(svc._tasks))

    asyncio.run(go())
    assert llm.calls == 1
    assert memo["followup"]["status"] == "ready"


def test_followup_off_for_the_company_drafts_nothing():
    memo, llm = company_memo(), FakeLLM()
    client = flags_client(memo, [("co-1", "FOLLOWUP_ENABLED", False)])
    asyncio.run(svc.ensure_followup(client, "m1", llm=llm))

    async def schedule(**kwargs):
        return svc.schedule_followup(client, "m1", llm=llm, **kwargs)

    assert asyncio.run(schedule()) is False, "company read from the memo"
    assert asyncio.run(schedule(company_id="co-1")) is False
    assert (llm.calls, memo["followup"]) == (0, None)


def test_without_a_company_row_followup_is_todays():
    memo, llm = company_memo(), FakeLLM()
    client = flags_client(memo)

    async def go():
        assert svc.schedule_followup(client, "m1", llm=llm) is True
        await asyncio.gather(*list(svc._tasks))

    asyncio.run(go())
    assert memo["followup"]["status"] == "ready"


def test_company_on_while_global_off(monkeypatch):
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", False)
    memo, llm = company_memo(), FakeLLM()
    client = flags_client(memo, [("co-1", "FOLLOWUP_ENABLED", True)])

    async def go():
        assert svc.schedule_followup(client, "m1", llm=llm, company_id="co-1") is True
        await asyncio.gather(*list(svc._tasks))

    asyncio.run(go())
    assert memo["followup"]["status"] == "ready"


def test_the_prompt_gets_the_three_newest_samples_pasted_included():
    memo, llm = memo_row(), FakeLLM()
    client = client_for(memo)
    client.tables["user_profiles"][0]["writing_samples"] = ["l1", {"text": "p1", "source": "pasted"}, "l2", "l3"]
    asyncio.run(svc.ensure_followup(client, "m1", llm=llm))
    assert context_of(llm)["voice_samples"] == ["p1", "l2", "l3"]


if __name__ == "__main__":
    unittest.main()
