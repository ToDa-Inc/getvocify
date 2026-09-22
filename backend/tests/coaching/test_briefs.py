"""F11 brief: a voicemail is skipped, and a missing score does not invent advice."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-briefs-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-briefs-32b+")

from app.services.coaching.briefs import absent_brief, aggregate_brief, materialize_brief
from app.services.coaching.scoring import store_memo_score

PATTERNS = [{
    "input_revision": "rev-4",
    "superseded": False,
    "evidence_refs": ["ev-1", "ev-2", "ev-3", "ev-4"],
}]


def test_a_missing_row_is_not_a_running_job_or_a_missing_playbook():
    brief = absent_brief()
    assert brief["status"] == "pending"
    assert brief["reason"] == "not_started"
    assert brief["waiting"] is False
    assert brief["strength"] is None
    assert brief["sections"] == []
    for screening in ("voicemail", "no_response"):
        brief = aggregate_brief(
            screening=screening,
            score=None,
            patterns=PATTERNS,
            playbook_present=True,
            job_error=False,
            input_revision="rev-4",
            audio_available=False,
        )
        assert brief["status"] == "skipped"
        assert brief["waiting"] is False
        assert brief["sections"] == []


def test_ready_objections_without_a_score_stay_partial():
    brief = aggregate_brief(
        screening=None,
        score=None,
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert brief["status"] == "partial"
    assert brief["reason"] == "score_pending"
    assert brief["sections"] == [{"kind": "objections", "evidence_refs": ["ev-1", "ev-2", "ev-3"]}]
    assert brief["strength"] is None
    assert brief["audio_available"] is False


def test_missing_playbook_is_unavailable_and_a_job_error_is_failed():
    missing = aggregate_brief(
        screening=None,
        score={"input_revision": "rev-4", "status": "ready", "value": 8, "strengths": ["Sigue así"]},
        patterns=PATTERNS,
        playbook_present=False,
        job_error=False,
        input_revision="rev-4",
        audio_available=True,
    )
    assert missing["status"] == "unavailable"
    assert missing["reason"] == "missing_playbook"
    assert missing["strength"] is None
    failed = aggregate_brief(
        screening=None,
        score={"status": "pending", "input_revision": "rev-4"},
        patterns=[],
        playbook_present=True,
        job_error=True,
        input_revision="rev-4",
        audio_available=False,
    )
    assert failed["status"] == "failed"
    assert failed["waiting"] is False


def test_an_old_score_is_not_mixed_with_the_current_revision():
    brief = aggregate_brief(
        screening=None,
        score={
            "input_revision": "rev-3",
            "status": "ready",
            "value": 9,
            "strengths": ["Cerró el siguiente paso"],
            "improvements": ["Preguntó tarde"],
        },
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=True,
    )
    assert brief["status"] == "partial"
    assert brief["strength"] is None
    assert brief["improvement"] is None
    assert brief["sections"][0]["evidence_refs"] == ["ev-1", "ev-2", "ev-3"]


def test_materialize_ready_score_keeps_revision_and_objection_section():
    score = {
        "input_revision": "rev-4",
        "status": "ready",
        "value": 8,
        "strengths": ["Nombró el precio"],
        "improvements": [],
    }
    patterns = [{"input_revision": "rev-4", "superseded": False, "evidence_refs": ["ev-1"]}]
    row = materialize_brief(
        screening=None,
        score=score,
        patterns=patterns,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert row["status"] == "ready"
    assert row["input_revision"] == "rev-4"
    assert row["body"]["input_revision"] == "rev-4"
    assert row["body"]["sections"] == [{"kind": "objections", "evidence_refs": ["ev-1"]}]
    assert row["body"]["strength"] == "Nombró el precio"


def test_materialize_voicemail_screening_is_skipped():
    row = materialize_brief(
        screening="voicemail",
        score={"input_revision": "rev-4", "status": "ready", "value": 7, "strengths": ["X"]},
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=True,
    )
    assert row["status"] == "skipped"
    assert row["body"]["reason"] == "no_conversation"
    assert row["body"]["sections"] == []
    assert row["body"]["strength"] is None


class _TableQuery:
    def __init__(self, store: dict, name: str):
        self.store = store
        self.name = name
        self.filters: list[tuple[str, str]] = []
        self._payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def upsert(self, payload):
        self._payload = payload
        return self

    def execute(self):
        rows = list(self.store.get(self.name) or [])
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
        self.tables: dict[str, list] = {"memo_scores": [], "post_interaction_briefs": []}

    def table(self, name: str):
        return _TableQuery(self.tables, name)


def test_store_memo_score_upserts_brief_for_the_same_revision():
    supabase = _SupabaseStub()
    score = {
        "input_revision": "rev-4",
        "status": "ready",
        "value": 8,
        "playbook_version_id": "pv-1",
        "strengths": [],
        "improvements": [],
    }
    patterns = [{"input_revision": "rev-4", "superseded": False, "evidence_refs": ["ev-1"]}]
    assert store_memo_score(
        supabase,
        memo_id="memo-1",
        input_revision="rev-4",
        revision_seq=4,
        score=score,
        patterns=patterns,
    )
    briefs = supabase.tables["post_interaction_briefs"]
    assert len(briefs) == 1
    assert briefs[0]["input_revision"] == "rev-4"
    assert briefs[0]["status"] == "ready"
    assert briefs[0]["body"]["input_revision"] == "rev-4"
    assert briefs[0]["body"]["sections"][0]["evidence_refs"] == ["ev-1"]
