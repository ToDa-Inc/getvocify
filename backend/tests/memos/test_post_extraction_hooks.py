"""Score and meeting proposal run when extraction is saved, without the intelligence worker."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-hooks-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-hooks-32")

import hashlib
import json

from app.services.coaching.score_assembly import _cited_refs, build_score_from_extraction
from app.services import memo_extraction_hooks
from app.services.intelligence.extract import PROMPT_VERSION
from app.services.intelligence.worker import revision_for_memo
from app.services.memo_extraction_hooks import (
    refresh_meeting_proposal,
    resolve_input_revision,
    run_post_extraction_hooks,
)

MEMO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _TableQuery:
    def __init__(self, store: dict, name: str, *, fail_patterns_upsert: bool = False):
        self.store = store
        self.name = name
        self.fail_patterns_upsert = fail_patterns_upsert
        self.filters: list[tuple[str, str]] = []
        self._payload = None
        self._limit = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append((column, str(value)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        return self

    def insert(self, payload):
        self._payload = payload
        return self

    def upsert(self, payload):
        self._payload = payload
        self._upsert = True
        return self

    def delete(self):
        self._delete = True
        return self

    def update(self, payload):
        self._update = payload
        return self

    def execute(self):
        rows = list(self.store.get(self.name) or [])
        if getattr(self, "_update", None) is not None:
            hit = [row for row in rows if all(str(row.get(c)) == v for c, v in self.filters)]
            for row in hit:
                row.update(self._update)
            return type("R", (), {"data": hit})()
        if getattr(self, "_delete", False):
            gone = [row for row in rows if all(str(row.get(c)) == v for c, v in self.filters)]
            self.store[self.name] = [row for row in rows if row not in gone]
            return type("R", (), {"data": gone})()
        if self._payload is not None:
            payload = self._payload
            if getattr(self, "_upsert", False) and self.fail_patterns_upsert:
                raise RuntimeError("patterns down")
            if getattr(self, "_upsert", False) and isinstance(payload, dict):
                if self.name == "interaction_patterns":
                    key = (payload.get("memo_id"), payload.get("pattern_id"))
                else:
                    key = (payload.get("memo_id"), payload.get("input_revision"))
                rows = [
                    row
                    for row in rows
                    if (row.get("memo_id"), row.get("pattern_id" if self.name == "interaction_patterns" else "input_revision"))
                    != key
                ]
                rows.append(dict(payload))
            elif isinstance(payload, list):
                rows.extend(dict(row) for row in payload)
            else:
                rows.append(dict(payload))
            self.store[self.name] = rows
            data = payload if isinstance(payload, list) else [payload]
            return type("R", (), {"data": data})()
        for column, value in self.filters:
            rows = [row for row in rows if str(row.get(column)) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return type("R", (), {"data": rows})()


class _SupabaseStub:
    def __init__(
        self,
        *,
        fail_score: bool = False,
        fail_meeting: bool = False,
        fail_patterns: bool = False,
    ):
        self.tables: dict[str, list] = {
            "memos": [],
            "memo_scores": [],
            "post_interaction_briefs": [],
            "meeting_proposals": [],
            "interaction_patterns": [],
        }
        self.fail_score = fail_score
        self.fail_meeting = fail_meeting
        self.fail_patterns = fail_patterns

    def table(self, name: str):
        if self.fail_score and name == "memo_scores":
            raise RuntimeError("score down")
        if self.fail_meeting and name == "meeting_proposals":
            raise RuntimeError("meeting down")
        return _TableQuery(
            self.tables,
            name,
            fail_patterns_upsert=self.fail_patterns and name == "interaction_patterns",
        )


def _memo(**overrides):
    base = {
        "id": MEMO_ID,
        "user_id": "user-1",
        "company_id": "co-1",
        "playbook_version_id": "pv-1",
        "screening_outcome": None,
        "crm_outcome": "open",
        "audio_path": "/audio.wav",
    }
    base.update(overrides)
    return base


def _scoreable_extraction(**overrides):
    base = {
        "summary": "Trabajamos objeción de precio",
        "objections": [{"text": "Está caro", "category": "price"}],
        "intelligence": {
            "version": 1,
            "input_revision": "rev-intel",
            "objections": [{"id": "obj-1", "category": "price", "evidence_refs": ["ev-1"]}],
            "playbook_observations": [
                {
                    "step_id": "handle_price",
                    "playbook_version_id": "pv-1",
                    "status": "met",
                    "evidence_refs": ["ev-1"],
                }
            ],
            "evidence": [
                {
                    "id": "ev-1",
                    "source_type": "transcript",
                    "source_id": MEMO_ID,
                    "quote": "Está caro",
                }
            ],
        },
    }
    base.update(overrides)
    return base


def test_resolve_input_revision_prefers_memo_field():
    memo = _memo(input_revision="rev-on-memo")
    assert resolve_input_revision(memo, {"summary": "x"}) == "rev-on-memo"


def test_resolve_input_revision_hashes_memo_id_and_extraction():
    extraction = {"summary": "Hola", "nextSteps": ["Enviar propuesta"]}
    memo = _memo()
    a = resolve_input_revision(memo, extraction)
    b = resolve_input_revision(memo, extraction)
    blob = json.dumps(extraction, sort_keys=True, default=str, ensure_ascii=False)
    expected = hashlib.sha256(f"{MEMO_ID}:{blob}".encode()).hexdigest()
    assert a == b == expected


def test_hooks_publish_score_without_worker_job():
    supabase = _SupabaseStub()
    memo = _memo()
    extraction = _scoreable_extraction()
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    assert len(supabase.tables["memo_scores"]) == 1
    stored = supabase.tables["memo_scores"][0]["score"]
    assert stored["value"] == 10
    assert stored["input_revision"] == resolve_input_revision(memo, extraction)


def test_hooks_skip_score_when_nothing_to_score():
    supabase = _SupabaseStub()
    memo = _memo()
    run_post_extraction_hooks(
        supabase,
        memo_id=MEMO_ID,
        memo=memo,
        extraction={"summary": "", "objections": []},
    )
    assert supabase.tables["memo_scores"] == []


def test_voicemail_does_not_invent_proposed_value():
    supabase = _SupabaseStub()
    memo = _memo(screening_outcome="voicemail")
    extraction = _scoreable_extraction()
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    score = supabase.tables["memo_scores"][0]["score"]
    assert score["value"] is None


def test_missing_playbook_does_not_invent_mark():
    supabase = _SupabaseStub()
    memo = _memo(playbook_version_id=None)
    extraction = _scoreable_extraction()
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    score = supabase.tables["memo_scores"][0]["score"]
    assert score["status"] == "unavailable"
    assert score["value"] is None
    assert score["reason"] == "missing_playbook"


def _with_intelligence(memo: dict, extraction: dict, meeting: dict) -> dict:
    revision = revision_for_memo({**memo, "extraction": extraction})
    return {
        **extraction,
        "intelligence": {
            "version": 1,
            "input_revision": revision,
            "prompt_version": PROMPT_VERSION,
            "meeting": meeting,
            "evidence": [],
        },
    }


_BOOKED = {
    "agreed": True,
    "starts_at": "2026-10-01T10:00:00+02:00",
    "timezone": None,
    "precision": "time",
    "evidence_refs": ["ev-jueves"],
}


def test_meeting_proposal_reads_the_transcript_not_the_summary():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Vale, quedamos el jueves 1 a las 10.")
    extraction = {"summary": "Reunión la semana del 5", "nextSteps": []}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    rows = supabase.tables["meeting_proposals"]
    assert len(rows) == 1
    assert rows[0]["agreement"] == "agreed"
    assert rows[0]["evidence_refs"] == ["transcript"]
    assert rows[0]["decision"] == "pending"
    assert rows[0]["crm_status"] == "not_requested"


def test_a_meeting_only_in_the_summary_is_not_a_proposal():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Mándame el precio por email.")
    extraction = {"summary": "Quedamos la semana del 5", "nextSteps": ["Reunión la semana del 5"]}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    assert supabase.tables["meeting_proposals"] == []


def test_the_transcript_fallback_always_needs_review():
    supabase = _SupabaseStub()
    memo = _memo(transcript="You: ¿Te va bien? Them: Sí, quedamos el martes a las 17:00.")
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction={"summary": ""})
    row = supabase.tables["meeting_proposals"][0]
    assert row["starts_at"] is None
    assert row["precision"] != "exact"


def test_intelligence_meeting_drives_the_proposal_over_summary_and_keywords():
    supabase = _SupabaseStub()
    memo = _memo(transcript="You: Te pongo una reunión el jueves 1 a las 10 y te mando la invitación. Them: Perfecto.")
    base = {"summary": "Reunión la semana del 5", "nextSteps": []}
    extraction = _with_intelligence(memo, base, _BOOKED)
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    rows = supabase.tables["meeting_proposals"]
    assert len(rows) == 1
    assert rows[0]["agreement"] == "agreed"
    assert rows[0]["starts_at"] == "2026-10-01T10:00:00+02:00"
    assert rows[0]["precision"] == "exact"
    assert rows[0]["evidence_refs"] == ["ev-jueves"]
    assert rows[0]["input_revision"] == revision_for_memo({**memo, "extraction": base})


def test_stale_intelligence_is_ignored_and_the_transcript_fallback_runs():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Quedamos el martes.")
    stale = _with_intelligence(memo, {"summary": "antes"}, _BOOKED)
    extraction = {**stale, "summary": "después"}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    row = supabase.tables["meeting_proposals"][0]
    assert row["starts_at"] is None
    assert row["evidence_refs"] == ["transcript"]


def test_intelligence_arriving_later_replaces_the_undecided_fallback():
    supabase = _SupabaseStub()
    memo = _memo(transcript="You: Te pongo una reunión el jueves 1 a las 10. Them: Perfecto.")
    base = {"summary": "Reunión la semana del 5"}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=base)
    assert supabase.tables["meeting_proposals"][0]["starts_at"] is None
    refresh_meeting_proposal(supabase, {**memo, "extraction": _with_intelligence(memo, base, _BOOKED)})
    rows = supabase.tables["meeting_proposals"]
    assert len(rows) == 1
    assert rows[0]["starts_at"] == "2026-10-01T10:00:00+02:00"
    assert rows[0]["precision"] == "exact"


def test_intelligence_without_agreement_removes_the_undecided_fallback():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Una reunión ahora no, primero mándame un vídeo.")
    base = {"summary": ""}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=base)
    assert len(supabase.tables["meeting_proposals"]) == 1
    empty = {"agreed": None, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": []}
    refresh_meeting_proposal(supabase, {**memo, "extraction": _with_intelligence(memo, base, empty)})
    assert supabase.tables["meeting_proposals"] == []


def test_intelligence_never_overrides_a_human_decision():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Quedamos el jueves.")
    base = {"summary": ""}
    revision = revision_for_memo({**memo, "extraction": base})
    decided = {
        "proposal_id": "meet-human",
        "memo_id": MEMO_ID,
        "input_revision": revision,
        "agreement": "agreed",
        "starts_at": "2026-10-02T09:30:00+02:00",
        "timezone": "Europe/Madrid",
        "precision": "exact",
        "decision": "corrected",
        "crm_status": "succeeded",
        "evidence_refs": [],
    }
    supabase.tables["meeting_proposals"] = [dict(decided)]
    empty = {"agreed": None, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": []}
    refresh_meeting_proposal(supabase, {**memo, "extraction": _with_intelligence(memo, base, empty)})
    refresh_meeting_proposal(supabase, {**memo, "extraction": _with_intelligence(memo, base, _BOOKED)})
    assert supabase.tables["meeting_proposals"] == [decided]


def test_storing_intelligence_reevaluates_the_meeting_proposal():
    import asyncio

    from app.services.intelligence.extract import ensure_intelligence

    class _LLM:
        last_call_meta: dict = {}

        async def chat_json(self, *_args, **_kwargs):
            return {"meeting": {"agreed": True, "starts_at": "2026-10-01T10:00:00+02:00", "quote": "Perfecto, el jueves 1 a las 10"}}

    supabase = _SupabaseStub()
    memo = _memo(
        transcript="You: ¿Te pongo una reunión? Them: Perfecto, el jueves 1 a las 10.",
        extraction={"summary": "Reunión la semana del 5"},
    )
    supabase.tables["memos"] = [memo]
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=memo["extraction"])
    assert supabase.tables["meeting_proposals"][0]["starts_at"] is None
    stored = asyncio.run(ensure_intelligence(supabase, MEMO_ID, llm=_LLM()))
    assert stored["status"] == "stored"
    rows = supabase.tables["meeting_proposals"]
    assert len(rows) == 1
    assert rows[0]["starts_at"] == "2026-10-01T10:00:00+02:00"
    assert rows[0]["agreement"] == "agreed"


def test_refresh_never_raises():
    refresh_meeting_proposal(_SupabaseStub(fail_meeting=True), {**_memo(), "extraction": {"intelligence": {"meeting": _BOOKED}}})
    refresh_meeting_proposal(_SupabaseStub(), {"id": MEMO_ID})


def test_not_agreed_does_not_insert_proposal():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: No, no quedamos, mejor otro día.")
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction={"summary": ""})
    assert supabase.tables["meeting_proposals"] == []


def test_no_meeting_cue_skips_proposal():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Envíame la propuesta por email.")
    extraction = {"summary": "Enviar propuesta por email", "nextSteps": ["Follow up"]}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    assert supabase.tables["meeting_proposals"] == []


def test_duplicate_proposal_for_same_revision_not_inserted():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Quedamos mañana a las 10.")
    extraction = {"summary": "", "nextSteps": []}
    revision = revision_for_memo({**memo, "extraction": extraction})
    supabase.tables["meeting_proposals"] = [
        {
            "proposal_id": "existing",
            "memo_id": MEMO_ID,
            "input_revision": revision,
            "agreement": "agreed",
            "starts_at": None,
            "timezone": "Europe/Madrid",
            "precision": "ambiguous",
            "decision": "pending",
            "crm_status": "not_requested",
            "evidence_refs": [],
        }
    ]
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    assert len(supabase.tables["meeting_proposals"]) == 1


def test_ambiguous_time_stored_with_null_starts_at():
    supabase = _SupabaseStub()
    memo = _memo(transcript="Them: Vale, quedamos a las cinco.")
    extraction = {"summary": "", "nextSteps": []}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    row = supabase.tables["meeting_proposals"][0]
    assert row["precision"] == "ambiguous"
    assert row["starts_at"] is None


def test_score_and_meeting_failures_do_not_raise():
    supabase = _SupabaseStub(fail_score=True, fail_meeting=True)
    memo = _memo()
    extraction = _scoreable_extraction(summary="Quedamos el jueves a las 11")
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)


def test_hooks_project_string_objection_as_commercial():
    supabase = _SupabaseStub()
    memo = _memo()
    extraction = {"summary": "Objeción de precio", "objections": ["Está caro"]}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    rows = [r for r in supabase.tables["interaction_patterns"] if not r.get("superseded")]
    assert len(rows) == 1
    assert rows[0]["kind"] == "objection"
    assert str(rows[0]["pattern_id"]).startswith("objection:")


def test_hooks_project_dict_with_commercial_false_as_obstacle():
    supabase = _SupabaseStub()
    memo = _memo()
    extraction = {
        "summary": "Visita",
        "objections": [{"text": "Falta parking", "commercial_objection": False}],
    }
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    rows = [r for r in supabase.tables["interaction_patterns"] if not r.get("superseded")]
    assert len(rows) == 1
    assert rows[0]["kind"] == "obstacle"


def test_hooks_empty_objections_supersede_objection_rows_only():
    supabase = _SupabaseStub()
    memo = _memo()
    first = {"summary": "Una", "objections": ["Está caro"]}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=first)
    supabase.tables["interaction_patterns"].append(
        {
            "pattern_id": "human-1",
            "memo_id": MEMO_ID,
            "input_revision": "rev-note",
            "kind": "unknown",
            "superseded": False,
        }
    )
    second = {"summary": "Sin objeciones", "objections": []}
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=second)
    active = [r for r in supabase.tables["interaction_patterns"] if not r.get("superseded")]
    assert not any(str(r.get("pattern_id", "")).startswith("objection:") for r in active)
    assert any(r.get("pattern_id") == "human-1" for r in active)


def test_pattern_failure_does_not_block_score_or_meeting():
    supabase = _SupabaseStub(fail_patterns=True)
    memo = _memo(transcript="Them: Quedamos el martes a las 16:00.")
    extraction = _scoreable_extraction()
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)
    assert len(supabase.tables["memo_scores"]) == 1
    assert len(supabase.tables["meeting_proposals"]) == 1


def test_score_receives_projected_objection_patterns(monkeypatch):
    """Projected objection rows must be passed into score assembly before publish."""
    captured: dict = {}

    def recording_build(**kwargs):
        captured["patterns"] = kwargs.get("patterns")
        return build_score_from_extraction(**kwargs)

    monkeypatch.setattr(memo_extraction_hooks, "build_score_from_extraction", recording_build)
    supabase = _SupabaseStub()
    memo = _memo()
    extraction = {
        "summary": "Objeción de precio",
        "objections": ["Está caro"],
        "intelligence": {
            "version": 1,
            "objections": [],
            "playbook_observations": [
                {
                    "step_id": "handle_price",
                    "playbook_version_id": "pv-1",
                    "status": "met",
                    "evidence_refs": ["ev-1"],
                }
            ],
            "evidence": [
                {
                    "id": "ev-1",
                    "source_type": "transcript",
                    "source_id": MEMO_ID,
                    "quote": "Hola",
                },
                {
                    "id": "ev-obj",
                    "source_type": "transcript",
                    "source_id": MEMO_ID,
                    "quote": "Está caro",
                },
            ],
        },
    }
    revision = resolve_input_revision(memo, extraction)
    run_post_extraction_hooks(supabase, memo_id=MEMO_ID, memo=memo, extraction=extraction)

    patterns = captured.get("patterns") or []
    active = [p for p in patterns if not p.get("superseded")]
    objection_rows = [p for p in active if str(p.get("pattern_id", "")).startswith("objection:")]
    assert objection_rows, "score assembly must see projected objection patterns"
    assert objection_rows[0]["input_revision"] == revision

    intel = extraction["intelligence"]
    pattern_with_evidence = {**objection_rows[0], "evidence_refs": ["ev-obj"]}
    assert "ev-obj" not in _cited_refs(intel, [], revision)
    assert "ev-obj" in _cited_refs(intel, [pattern_with_evidence], revision)
    assert captured["patterns"] is not None
    assert build_score_from_extraction(
        extraction=extraction,
        memo=memo,
        input_revision=revision,
        patterns=captured["patterns"],
        crm_outcome=memo.get("crm_outcome"),
        screening=memo.get("screening_outcome"),
    ) is not None

    assert len(supabase.tables["memo_scores"]) == 1
