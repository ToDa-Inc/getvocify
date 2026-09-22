import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

from app.config import settings
from app.services import followup as svc


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
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"subject": "Caso de logística", "body": "Hola Marina, te paso el caso.", "language": "es"}
        self.error, self.calls = error, 0

    async def chat_json(self, messages, **kwargs):
        self.calls += 1
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
        asyncio.run(svc.ensure_followup(client_for(errored), "m1", llm=FakeLLM(error=TimeoutError())))
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


if __name__ == "__main__":
    unittest.main()
