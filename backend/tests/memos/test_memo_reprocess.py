"""Reprocess a company's stored conversations through today's pipeline (admin console)."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-reprocess-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-reprocess-32")

from app.services import memo_reprocess  # noqa: E402


def test_reprocessable_keeps_unapproved_memos_with_a_transcript():
    rows = [
        {"id": "a", "transcript": "hola", "status": "pending_review", "extraction": None},
        {"id": "b", "transcript": "", "status": "pending_review", "extraction": None},
        {"id": "c", "transcript": "hola", "status": "approved", "extraction": None},
        {"id": "d", "transcript": "hola", "status": "pending_review", "extraction": {"x": 1}},
    ]
    assert [r["id"] for r in memo_reprocess.reprocessable(rows, only_unprocessed=True)] == ["a"]
    assert [r["id"] for r in memo_reprocess.reprocessable(rows, only_unprocessed=False)] == ["a", "d"]


class _Store:
    def __init__(self, rows):
        self.rows = rows
        self.updates: list[tuple[str, dict]] = []
        self._payload = None

    def table(self, _name):
        return self

    def select(self, *_a):
        return self

    def eq(self, _col, value):
        self._id = value
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def execute(self):
        if self._payload is not None:
            self.updates.append((self._id, self._payload))
            self._payload = None
            return type("R", (), {"data": []})()
        return type("R", (), {"data": self.rows})()


def test_a_run_pins_then_reextracts_each_memo_once_and_counts_failures(monkeypatch):
    monkeypatch.setattr(
        "app.services.captures.pin_playbook_on_row",
        lambda _s, row: {**row, "playbook_version_id": "pv-1"},
    )
    store = _Store([
        {"id": "a", "user_id": "u", "company_id": "co", "transcript": "uno", "status": "pending_review"},
        {"id": "b", "user_id": "u", "company_id": "co", "transcript": "dos", "status": "pending_review"},
    ])
    seen: list[tuple[str, str | None, str]] = []

    async def reextract(_supabase, memo, *, trigger):
        seen.append((memo["id"], memo.get("playbook_version_id"), trigger))
        if memo["id"] == "b":
            raise RuntimeError("boom")

    async def go():
        started = memo_reprocess.start_reprocess(store, "co", limit=10, reextract=reextract)
        assert started["total"] == 2 and started["running"] is True
        # A second press while running does not start another batch.
        assert memo_reprocess.start_reprocess(store, "co", reextract=reextract)["total"] == 2
        await asyncio.gather(*list(memo_reprocess._TASKS))

    asyncio.run(go())
    assert seen == [("a", "pv-1", "reprocess"), ("b", "pv-1", "reprocess")]
    assert store.updates == [("a", {"playbook_version_id": "pv-1"}), ("b", {"playbook_version_id": "pv-1"})]
    done = memo_reprocess.progress("co")
    assert (done["running"], done["done"], done["failed"]) == (False, 1, 1)


def test_nothing_to_do_finishes_at_once():
    memo_reprocess._RUNS.pop("empty", None)
    run = memo_reprocess.start_reprocess(_Store([]), "empty")
    assert (run["running"], run["total"]) == (False, 0)
