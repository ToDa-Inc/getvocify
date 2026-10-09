"""F11 brief: a voicemail is skipped, and a missing score does not invent advice."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-briefs-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-briefs-32b+")

from app.services.coaching.briefs import (
    absent_brief,
    aggregate_brief,
    build_highlights,
    build_phrases,
    label_missed_items,
    materialize_brief,
)
from app.services.coaching.scoring import publish_memo_score, store_memo_score

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


def test_improvement_is_omitted_without_evidence_sections():
    bare = aggregate_brief(
        screening=None,
        score={
            "input_revision": "rev-4",
            "status": "ready",
            "value": 8,
            "strengths": ["Nombró el precio"],
            "improvements": ["No cerró el paso"],
        },
        patterns=[],
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert bare["status"] == "ready"
    assert bare["improvement"] is None
    assert bare["strength"] == "Nombró el precio"
    backed = aggregate_brief(
        screening=None,
        score={
            "input_revision": "rev-4",
            "status": "ready",
            "value": 8,
            "strengths": ["Nombró el precio"],
            "improvements": ["No cerró el paso"],
        },
        patterns=[{"input_revision": "rev-4", "superseded": False, "evidence_refs": ["ev-1"]}],
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert backed["improvement"] == "No cerró el paso"
    assert backed["sections"][0]["evidence_refs"] == ["ev-1"]


def test_ready_brief_keeps_one_coaching_line_and_three_evidence_refs():
    brief = aggregate_brief(
        screening=None,
        score={
            "input_revision": "rev-4",
            "status": "ready",
            "value": 8,
            "strengths": ["Uno", "Dos"],
            "improvements": ["Mejora"],
        },
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert brief["strength"] == "Uno"
    assert brief["improvement"] == "Mejora"
    assert brief["sections"] == [{"kind": "objections", "evidence_refs": ["ev-1", "ev-2", "ev-3"]}]


def test_terminal_brief_states_never_wait_forever():
    skipped = aggregate_brief(
        screening="voicemail",
        score={"input_revision": "rev-4", "status": "pending"},
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert skipped["status"] == "skipped"
    assert skipped["waiting"] is False
    failed = aggregate_brief(
        screening=None,
        score=None,
        patterns=[],
        playbook_present=True,
        job_error=True,
        input_revision="rev-4",
        audio_available=False,
    )
    assert failed["status"] == "failed"
    assert failed["waiting"] is False


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
    def __init__(self, store: dict, name: str, *, fail_upsert: bool = False):
        self.store = store
        self.name = name
        self.filters: list[tuple[str, str]] = []
        self._payload = None
        self.fail_upsert = fail_upsert

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
            if self.fail_upsert and self.name == "post_interaction_briefs":
                raise RuntimeError("brief upsert failed")
            key = (self._payload["memo_id"], self._payload["input_revision"])
            rows = [row for row in rows if (row["memo_id"], row["input_revision"]) != key]
            rows.append(dict(self._payload))
            self.store[self.name] = rows
            return type("R", (), {"data": [self._payload]})()
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return type("R", (), {"data": rows})()


class _SupabaseStub:
    def __init__(self, *, fail_brief_upsert: bool = False):
        self.tables: dict[str, list] = {"memo_scores": [], "post_interaction_briefs": []}
        self.fail_brief_upsert = fail_brief_upsert

    def table(self, name: str):
        return _TableQuery(
            self.tables,
            name,
            fail_upsert=self.fail_brief_upsert and name == "post_interaction_briefs",
        )


def test_publish_memo_score_materializes_one_brief_for_the_same_revision():
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
    assert publish_memo_score(
        supabase,
        memo_id="memo-1",
        input_revision="rev-4",
        revision_seq=4,
        score=score,
        patterns=patterns,
    )
    assert publish_memo_score(
        supabase,
        memo_id="memo-1",
        input_revision="rev-4",
        revision_seq=4,
        score=score,
        patterns=patterns,
    ) is False
    briefs = supabase.tables["post_interaction_briefs"]
    assert len(briefs) == 1
    assert len(supabase.tables["memo_scores"]) == 1


def test_publish_memo_score_voicemail_screening_skips_brief():
    supabase = _SupabaseStub()
    score = {
        "input_revision": "rev-4",
        "status": "ready",
        "value": 7,
        "strengths": ["No debe copiarse"],
        "improvements": [],
    }
    assert publish_memo_score(
        supabase,
        memo_id="memo-1",
        input_revision="rev-4",
        revision_seq=4,
        score=score,
        screening="voicemail",
        patterns=[{"input_revision": "rev-4", "superseded": False, "evidence_refs": ["ev-1"]}],
    )
    brief = supabase.tables["post_interaction_briefs"][0]
    assert brief["status"] == "skipped"
    assert brief["body"]["strength"] is None


def test_publish_memo_score_keeps_score_when_brief_write_fails():
    supabase = _SupabaseStub(fail_brief_upsert=True)
    score = {
        "input_revision": "rev-4",
        "status": "ready",
        "value": 8,
        "playbook_version_id": "pv-1",
        "strengths": [],
        "improvements": [],
    }
    assert publish_memo_score(
        supabase,
        memo_id="memo-1",
        input_revision="rev-4",
        revision_seq=4,
        score=score,
    )
    assert len(supabase.tables["memo_scores"]) == 1
    assert supabase.tables["memo_scores"][0]["score"]["value"] == 8
    assert supabase.tables["post_interaction_briefs"] == []


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


# T10/DEBRIEF_V2_ENABLED: flow, missed steps/objections with their playbook phrase, timestamped
# highlights and the rep's recent progress in the same flow.

SCORE_READY = {
    "input_revision": "rev-4",
    "status": "ready",
    "value": 7,
    "playbook_version_id": "pv-1",
    "strengths": [],
    "improvements": [],
}

STEPS = [
    {
        "step_id": "confirm_budget",
        "label": "Confirmar presupuesto",
        "criterion": "Pregunta el presupuesto disponible",
        "example": "¿Con qué presupuesto contáis para esto?",
    },
]
ENTRIES = [
    {"entry_id": "price-1", "category": "price", "guidance": "Compara el coste con lo que ya pierden por no actuar"},
]


def test_debrief_v2_off_leaves_the_body_as_before():
    brief = aggregate_brief(
        screening=None,
        score=SCORE_READY,
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert "flow" not in brief
    assert "missed" not in brief
    assert "phrases" not in brief
    assert "highlights" not in brief
    assert "progress" not in brief


def test_debrief_v2_adds_flow_missed_phrases_highlights_and_progress():
    missed = label_missed_items(
        [{"kind": "step", "id": "confirm_budget"}, {"kind": "objection", "id": "obj-1", "category": "price"}],
        steps=STEPS,
        entries=ENTRIES,
    )
    evidence = [
        {"quote": "cita tardía", "start_ms": 192000},
        {"quote": "cita temprana", "start_ms": 12000},
        {"quote": "sin minuto", "start_ms": None},
    ]
    brief = aggregate_brief(
        screening=None,
        score=SCORE_READY,
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
        debrief_v2=True,
        flow="sdr",
        missed=missed,
        evidence=evidence,
        progress=[0.5, None, 0.8],
        meeting_agreed=True,
    )
    assert brief["flow"] == "sdr"
    assert [item["id"] for item in brief["missed"]] == ["confirm_budget", "obj-1"]
    # A step's phrase is its literal example; its criterion is how it is judged, never "how to say it".
    assert brief["phrases"] == [
        "¿Con qué presupuesto contáis para esto?",
        "Compara el coste con lo que ya pierden por no actuar",
    ]
    # earliest first, capped at 5, only evidence with a timestamp
    assert brief["highlights"] == ["min 00:12 · cita temprana", "min 03:12 · cita tardía"]
    assert brief["progress"] == [0.5, None, 0.8]
    assert brief["meeting_booked"] is True
    assert "next_step_agreed" not in brief


def test_debrief_v2_ae_flow_gets_next_step_not_meeting():
    brief = aggregate_brief(
        screening=None,
        score=SCORE_READY,
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
        debrief_v2=True,
        flow="ae",
        next_step_agreed=False,
    )
    assert brief["next_step_agreed"] is False
    assert "meeting_booked" not in brief


def test_build_phrases_stops_at_three_and_drops_repeats():
    missed = [
        {"guidance": "a"}, {"guidance": "b"}, {"guidance": "a"}, {"guidance": "c"}, {"guidance": "d"},
    ]
    assert build_phrases(missed) == ["a", "b", "c"]


def test_build_highlights_ignores_missing_timestamp_and_caps_at_five():
    evidence = [{"quote": f"q{i}", "start_ms": i * 1000} for i in range(6, 0, -1)] + [{"quote": "no time"}]
    highlights = build_highlights(evidence)
    assert len(highlights) == 5
    assert highlights[0].startswith("min 00:01")
    assert highlights[-1].startswith("min 00:05")


def test_label_missed_items_drops_ids_the_playbook_no_longer_has():
    missed = [{"kind": "step", "id": "gone"}, {"kind": "objection", "id": "obj-2", "category": "timing"}]
    labeled = label_missed_items(missed, steps=STEPS, entries=ENTRIES)
    assert labeled == []


def test_label_missed_items_matches_category_case_insensitively():
    entries = [{"entry_id": "price-1", "category": "Price", "guidance": "Compara el coste"}]
    labeled = label_missed_items([{"kind": "objection", "id": "obj-1", "category": "price"}], steps=[], entries=entries)
    assert labeled == [{"id": "obj-1", "kind": "objection", "label": "price", "guidance": "Compara el coste"}]


def test_label_missed_items_never_repeats_the_label_as_its_own_guidance():
    """A step with no criterion, or an objection whose entry mirrors the category, gets no phrase
    rather than showing the same text as both the missed label and the playbook phrase."""
    bare_step = [{"step_id": "s1", "label": "Confirmar presupuesto"}]  # no criterion
    labeled = label_missed_items([{"kind": "step", "id": "s1"}], steps=bare_step, entries=[])
    assert labeled == [{"id": "s1", "kind": "step", "label": "Confirmar presupuesto"}]
    assert "guidance" not in labeled[0]
    mirrored_entries = [{"entry_id": "price-1", "category": "price", "guidance": "price"}]
    labeled = label_missed_items([{"kind": "objection", "id": "obj-1", "category": "price"}], steps=[], entries=mirrored_entries)
    assert "guidance" not in labeled[0]


class _DebriefTable:
    """Minimal chainable query double: playbook_versions/memos/memo_scores reads only."""

    def __init__(self, rows: list[dict]):
        self._all = rows
        self._rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._rows = [row for row in self._rows if row.get(column) == value]
        return self

    def in_(self, column, values):
        values = set(values)
        self._rows = [row for row in self._rows if row.get(column) in values]
        return self

    def order(self, column, desc=False):
        self._rows = sorted(self._rows, key=lambda row: row.get(column) or "", reverse=desc)
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def execute(self):
        return type("R", (), {"data": list(self._rows)})()


class _DebriefSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, name: str):
        return _DebriefTable(self._tables.get(name, []))


def _debrief_tables() -> dict:
    return {
        "playbook_versions": [
            {"id": "pv-1", "status": "published", "steps": STEPS, "entries": ENTRIES},
            {"id": "pv-draft", "status": "draft", "steps": STEPS, "entries": ENTRIES},
        ],
        "memos": [
            {"id": "memo-older", "user_id": "u1", "company_id": "co-1", "sales_motion_key": "discovery", "created_at": "2026-09-01T00:00:00Z"},
            {"id": "memo-current", "user_id": "u1", "company_id": "co-1", "sales_motion_key": "discovery", "created_at": "2026-09-02T00:00:00Z"},
            {"id": "memo-other-co", "user_id": "u1", "company_id": "co-2", "sales_motion_key": "discovery", "created_at": "2026-09-01T12:00:00Z"},
        ],
        "memo_scores": [
            {"memo_id": "memo-older", "revision_seq": 1, "score": {"adherence": 0.5}},
            {"memo_id": "memo-other-co", "revision_seq": 1, "score": {"adherence": 0.1}},
        ],
    }


def test_debrief_v2_context_joins_playbook_evidence_and_progress():
    from app.services.coaching.briefs import debrief_v2_context

    supabase = _DebriefSupabase(_debrief_tables())
    memo = {"id": "memo-current", "user_id": "u1", "company_id": "co-1", "sales_motion_key": "discovery"}
    intelligence = {
        "evidence": [{"quote": "min tardío", "start_ms": 5000}, {"quote": "min temprano", "start_ms": 1000}],
        "meeting": {"agreed": True},
        "commitments": [],
    }
    score = {
        "playbook_version_id": "pv-1",
        "missed_items": [{"kind": "step", "id": "confirm_budget"}],
    }
    context = debrief_v2_context(supabase, memo=memo, intelligence=intelligence, score=score, memo_id="memo-current")
    assert context["flow"] == "sdr"
    assert context["missed"][0]["label"] == "Confirmar presupuesto"
    assert context["evidence"][0]["start_ms"] == 5000
    # Only this company's own history, and never the current memo itself.
    assert context["progress"] == [0.5]
    assert context["meeting_agreed"] is True
    # A meeting both sides accepted is an agreed next step.
    assert context["next_step_agreed"] is True


def test_debrief_v2_context_never_pulls_a_draft_playbook():
    from app.services.coaching.briefs import debrief_v2_context

    supabase = _DebriefSupabase(_debrief_tables())
    memo = {"id": "memo-current", "user_id": "u1", "company_id": "co-1", "sales_motion_key": "discovery"}
    score = {"playbook_version_id": "pv-draft", "missed_items": [{"kind": "step", "id": "confirm_budget"}]}
    context = debrief_v2_context(supabase, memo=memo, intelligence={}, score=score, memo_id="memo-current")
    assert context["missed"] == []


def test_recent_progress_never_crosses_companies():
    from app.services.coaching.briefs import recent_progress

    supabase = _DebriefSupabase(_debrief_tables())
    values = recent_progress(supabase, user_id="u1", company_id="co-1", sales_motion_key="discovery", exclude_memo_id="memo-current")
    assert values == [0.5]



# The coach block: one kept, one fix, in the playbook's words.

from app.services.coaching.briefs import build_coach, next_step_agreed  # noqa: E402

COACH_STEPS = [
    {"step_id": "opening", "label": "Apertura con permiso", "criterion": "Pide 30 segundos antes de contar nada."},
    {"step_id": "pain", "label": "Descubrir el dolor", "criterion": "Pregunta cómo lo hacen hoy."},
    {
        "step_id": "meeting",
        "label": "Reunión con día y hora",
        "criterion": "Propone un día y una hora concretos.",
        "example": "¿Te va bien el jueves a las 10?",
    },
]


def _obs(step_id, status, quote=None, refs=("ev-1",)):
    return {"step_id": step_id, "status": status, "quote": quote, "evidence_refs": list(refs) if status in {"met", "missed"} else []}


def test_coach_keeps_the_first_done_step_and_fixes_the_first_missed_one():
    coach = build_coach(
        observations=[_obs("opening", "met", "¿Tienes 30 segundos?"), _obs("pain", "missed"), _obs("meeting", "missed")],
        evidence_ids=["ev-1"],
        steps=COACH_STEPS,
        entries=[],
        missed=[],
    )
    assert coach["kept"] == {"step_id": "opening", "label": "Apertura con permiso", "quote": "¿Tienes 30 segundos?"}
    assert coach["fix"] == {
        "kind": "step",
        "id": "pain",
        "label": "Descubrir el dolor",
        "criterion": "Pregunta cómo lo hacen hoy.",
        "say": None,
        "focus": False,
    }


def test_coach_puts_the_weekly_focus_first_both_ways():
    missed_focus = build_coach(
        observations=[_obs("opening", "met", "Hola"), _obs("pain", "missed"), _obs("meeting", "missed")],
        evidence_ids=["ev-1"], steps=COACH_STEPS, entries=[], missed=[], focus_step_id="meeting",
    )
    assert missed_focus["fix"]["id"] == "meeting"
    assert missed_focus["fix"]["focus"] is True
    assert missed_focus["fix"]["say"] == "¿Te va bien el jueves a las 10?"
    kept_focus = build_coach(
        observations=[_obs("opening", "met", "Hola"), _obs("meeting", "met", "¿El jueves a las 10?")],
        evidence_ids=["ev-1"], steps=COACH_STEPS, entries=[], missed=[], focus_step_id="meeting",
    )
    assert kept_focus["kept"]["step_id"] == "meeting"
    assert kept_focus["fix"] is None


def test_coach_ignores_uncited_observations():
    coach = build_coach(
        observations=[_obs("opening", "met", "Hola", refs=("ev-gone",)), _obs("pain", "missed", refs=())],
        evidence_ids=["ev-1"], steps=COACH_STEPS, entries=[], missed=[],
    )
    assert coach == {"kept": None, "fix": None}


def test_coach_falls_back_to_an_open_objection_the_playbook_answers():
    coach = build_coach(
        observations=[_obs("opening", "met", "Hola")],
        evidence_ids=["ev-1"],
        steps=COACH_STEPS,
        entries=ENTRIES,
        missed=[{"kind": "objection", "id": "obj-1", "category": "price"}, {"kind": "objection", "id": "obj-2", "category": "timing"}],
    )
    assert coach["fix"] == {
        "kind": "objection",
        "id": "obj-1",
        "label": "price",
        "category": "price",
        "criterion": None,
        "say": "Compara el coste con lo que ya pierden por no actuar",
        "focus": False,
    }


def test_coach_only_reaches_the_body_for_a_measured_conversation():
    coach = {"kept": {"step_id": "opening", "label": "Apertura", "quote": "Hola"}, "fix": None}
    ready = aggregate_brief(
        screening=None, score=SCORE_READY, patterns=PATTERNS, playbook_present=True, job_error=False,
        input_revision="rev-4", audio_available=False, debrief_v2=True, flow="sdr", coach=coach,
    )
    assert ready["coach"] == coach
    voicemail = aggregate_brief(
        screening="voicemail", score=SCORE_READY, patterns=PATTERNS, playbook_present=True, job_error=False,
        input_revision="rev-4", audio_available=False, debrief_v2=True, flow="sdr", coach=coach,
    )
    assert voicemail["coach"] is None
    empty = aggregate_brief(
        screening=None, score=SCORE_READY, patterns=PATTERNS, playbook_present=True, job_error=False,
        input_revision="rev-4", audio_available=False, debrief_v2=True, flow="sdr", coach={"kept": None, "fix": None},
    )
    assert empty["coach"] is None


def test_next_step_is_a_meeting_or_a_dated_call_not_any_promise():
    assert next_step_agreed({"agreed": True}, []) is True
    assert next_step_agreed({}, [{"kind": "send", "due_at": "2026-10-01T10:00:00+02:00"}]) is False
    assert next_step_agreed({}, [{"kind": "call", "due_at": "2026-10-01T10:00:00+02:00"}]) is True
    assert next_step_agreed({}, [{"kind": "call", "due_at": None}]) is False
    assert next_step_agreed({}, None) is None


def test_cited_step_improvement_shows_without_objection_sections():
    brief = aggregate_brief(
        screening=None,
        score={
            "input_revision": "rev-4",
            "status": "ready",
            "value": 5,
            "strengths": [],
            "improvements": ["Reunión con día y hora: Propone un día y una hora concretos."],
            "improvements_cited": True,
        },
        patterns=[],
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert brief["improvement"] == "Reunión con día y hora: Propone un día y una hora concretos."
