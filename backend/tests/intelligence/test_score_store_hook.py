"""Intelligence worker store hook: payload score persists memo_scores and brief."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.services.coaching.score_jobs import store_coaching_from_job_payload
from app.services.intelligence.worker import database_bindings

MEMO = {
    "id": "memo-1",
    "user_id": "user-1",
    "company_id": "company-1",
    "extraction": {"summary": "Quiere el caso", "nextSteps": ["Enviar caso"]},
}


class _TableQuery:
    def __init__(self, store: dict, name: str):
        self.store = store
        self.name = name
        self.filters: list[tuple[str, str]] = []
        self._payload = None
        self._update = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def upsert(self, payload):
        self._payload = payload
        return self

    def update(self, payload):
        self._update = payload
        return self

    def execute(self):
        rows = list(self.store.get(self.name) or [])
        if self._update is not None:
            return type("R", (), {"data": [{**MEMO, "extraction": self._update.get("extraction", MEMO["extraction"])}]})()
        if self._payload is not None:
            key = (self._payload["memo_id"], self._payload["input_revision"])
            rows = [row for row in rows if (row["memo_id"], row["input_revision"]) != key]
            rows.append(dict(self._payload))
            self.store[self.name] = rows
            return type("R", (), {"data": [self._payload]})()
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return type("R", (), {"data": rows})()


class _SupabaseStub:
    def __init__(self):
        self.tables: dict[str, list] = {
            "memo_jobs": [
                {
                    "memo_id": "memo-1",
                    "kind": "intelligence",
                    "input_revision": "rev-4",
                    "revision_seq": 4,
                }
            ],
            "memo_scores": [],
            "post_interaction_briefs": [],
            "interaction_patterns": [],
        }

    def table(self, name: str):
        return _TableQuery(self.tables, name)


def test_store_coaching_from_job_payload_persists_score_and_brief():
    supabase = _SupabaseStub()
    payload = {
        "version": 1,
        "status": "ready",
        "input_revision": "rev-4",
        "score": {
            "input_revision": "rev-4",
            "status": "ready",
            "value": 8,
            "playbook_version_id": "pv-1",
            "strengths": [],
            "improvements": [],
        },
        "patterns": [{"input_revision": "rev-4", "superseded": False, "evidence_refs": ["ev-1"]}],
    }
    store_coaching_from_job_payload(supabase, MEMO, payload)
    assert len(supabase.tables["memo_scores"]) == 1
    assert len(supabase.tables["post_interaction_briefs"]) == 1
    store_coaching_from_job_payload(supabase, MEMO, payload)
    assert len(supabase.tables["post_interaction_briefs"]) == 1


def test_intelligence_store_callback_invokes_score_hook():
    supabase = _SupabaseStub()
    _, _, _, _, store = database_bindings(supabase)
    payload = {
        "version": 1,
        "status": "unavailable",
        "input_revision": "rev-4",
        "score": {
            "input_revision": "rev-4",
            "status": "ready",
            "value": 7,
            "playbook_version_id": "pv-1",
            "strengths": [],
            "improvements": [],
        },
    }
    store(MEMO, payload)
    assert len(supabase.tables["memo_scores"]) == 1
    assert supabase.tables["post_interaction_briefs"][0]["input_revision"] == "rev-4"
