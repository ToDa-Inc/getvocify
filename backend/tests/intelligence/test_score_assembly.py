"""Deterministic score from extraction for the intelligence store hook."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.services.coaching.score_assembly import attach_score_to_job_payload, build_score_from_extraction
from app.services.intelligence.extract import shape_intelligence

MEMO = {
    "id": "memo-1",
    "playbook_version_id": "pv-1",
    "screening_outcome": None,
}

EXTRACTION = {
    "summary": "Objeción de precio trabajada",
    "objections": [{"text": "Está caro", "category": "price"}],
    "intelligence": {
        "version": 1,
        "input_revision": "rev-4",
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
                "source_id": "memo-1",
                "quote": "Está caro",
            }
        ],
    },
}


def test_cited_objection_and_playbook_yield_score_without_crm_bonus():
    open_deal = build_score_from_extraction(
        extraction=EXTRACTION,
        memo=MEMO,
        input_revision="rev-4",
        crm_outcome="open",
    )
    won_deal = build_score_from_extraction(
        extraction=EXTRACTION,
        memo=MEMO,
        input_revision="rev-4",
        crm_outcome="closed_won",
    )
    assert open_deal is not None
    assert open_deal["input_revision"] == "rev-4"
    assert open_deal["value"] == won_deal["value"]
    assert open_deal["value"] is not None
    assert open_deal["crm_outcome"] == "open"
    assert won_deal["crm_outcome"] == "closed_won"


def test_empty_extraction_does_not_add_score_key():
    payload = {"version": 1, "status": "partial", "input_revision": "rev-4"}
    enriched = attach_score_to_job_payload(
        MEMO,
        payload,
        extraction={"summary": "", "objections": []},
    )
    assert "score" not in enriched


def test_voicemail_does_not_publish_a_mark():
    score = build_score_from_extraction(
        extraction=EXTRACTION,
        memo={**MEMO, "screening_outcome": "voicemail"},
        input_revision="rev-4",
    )
    assert score is not None
    assert score["value"] is None


def test_missing_playbook_is_unavailable():
    score = build_score_from_extraction(
        extraction=EXTRACTION,
        memo={"id": "memo-1"},
        input_revision="rev-4",
    )
    assert score is not None
    assert score["status"] == "unavailable"
    assert score["value"] is None
    assert score["reason"] == "missing_playbook"


def test_met_without_evidence_does_not_publish_a_mark():
    extraction = {
        **EXTRACTION,
        "intelligence": {
            **EXTRACTION["intelligence"],
            "playbook_observations": [
                {"step_id": "handle_price", "status": "met", "evidence_refs": []},
            ],
        },
    }
    score = build_score_from_extraction(extraction=extraction, memo=MEMO, input_revision="rev-4")
    assert score is not None
    assert score["value"] is None
    assert score["met_steps"] == 0
    assert score["unknown_steps"] == 1


# T10/SCORING_OBJECTION_CREDIT_ENABLED: an objection_handling criterion per real, evidenced
# objection. Objections come from `shape_intelligence` itself (the real C04 shape, including
# `response`/`response_evidence_refs`/`rep_replied_after`), not hand-built dicts.

_STEPS = [
    {"step_id": "s1", "playbook_version_id": "pv-1", "status": "met", "evidence_refs": ["ev-1"]},
    {"step_id": "s2", "playbook_version_id": "pv-1", "status": "met", "evidence_refs": ["ev-1"]},
    {"step_id": "s3", "playbook_version_id": "pv-1", "status": "missed", "evidence_refs": ["ev-1"]},
]
_EVIDENCE = [{"id": "ev-1", "source_type": "transcript", "source_id": "memo-1", "quote": "Quedamos el jueves"}]

OBJ_MEMO = {"id": "memo-1", "company_id": "co-1", "user_id": "u-1"}
_PRICE_QUOTE = "Está caro comparado con lo que pago ahora"


def _objection_intelligence(transcript: str, raw_objection: dict, *, input_revision: str) -> dict:
    """The real C04 shape for one objection, plus our own synthetic step observations."""
    memo = {**OBJ_MEMO, "transcript": transcript}
    shaped = shape_intelligence(memo, {"objections": [raw_objection]})
    return {
        **shaped,
        "input_revision": input_revision,
        "playbook_observations": _STEPS,
        "evidence": _EVIDENCE + shaped["evidence"],
    }


EASY_EXTRACTION = {
    "summary": "Reunión agendada sin fricción",
    "intelligence": {
        "version": 1,
        "input_revision": "rev-easy",
        "objections": [],
        "playbook_observations": _STEPS,
        "evidence": _EVIDENCE,
    },
}

OBJECTION_HANDLED_EXTRACTION = {
    "summary": "Misma llamada, con una objeción bien trabajada",
    "intelligence": _objection_intelligence(
        "Them: " + _PRICE_QUOTE + ". "
        "You: El retraso del mes pasado les costó más que la diferencia. "
        "Them: Tiene sentido, mándame el desglose.",
        {
            "category": "price",
            "resolution": "resolved",
            "quote": _PRICE_QUOTE,
            "response": "El retraso del mes pasado les costó más que la diferencia",
        },
        input_revision="rev-obj",
    ),
}

# The rep spoke again after the objection, but never answered it (no `response` cited).
OBJECTION_OPEN_EXTRACTION = {
    "summary": "Misma llamada, objeción sin trabajar",
    "intelligence": _objection_intelligence(
        "Them: " + _PRICE_QUOTE + ". You: Ajá, ya veo.",
        {"category": "price", "resolution": "open", "quote": _PRICE_QUOTE},
        input_revision="rev-open",
    ),
}

# The transcript just stops after the objection: we cannot tell whether the rep ever got the
# chance to answer, so this must stay unknown, never missed.
OBJECTION_OPEN_NO_SIGNAL_EXTRACTION = {
    "summary": "Misma llamada, se corta justo tras la objeción",
    "intelligence": _objection_intelligence(
        "Them: " + _PRICE_QUOTE + ".",
        {"category": "price", "resolution": "open", "quote": _PRICE_QUOTE},
        input_revision="rev-cut",
    ),
}


def _objection_misses(score: dict) -> list[dict]:
    return [item for item in score.get("missed_items", []) if item.get("kind") == "objection"]


def test_objection_response_is_only_kept_when_the_rep_actually_said_it():
    handled = OBJECTION_HANDLED_EXTRACTION["intelligence"]["objections"][0]
    assert handled["resolution"] == "resolved"
    assert handled["response"] == {"text": "El retraso del mes pasado les costó más que la diferencia"}
    assert handled["response_evidence_refs"]
    assert handled["rep_replied_after"] is True
    open_obj = OBJECTION_OPEN_EXTRACTION["intelligence"]["objections"][0]
    assert open_obj["response"] is None
    assert open_obj["response_evidence_refs"] == []
    assert open_obj["rep_replied_after"] is True
    cut_obj = OBJECTION_OPEN_NO_SIGNAL_EXTRACTION["intelligence"]["objections"][0]
    assert cut_obj["rep_replied_after"] is False


def test_missed_items_key_only_appears_when_a_t10_flag_is_on():
    off = build_score_from_extraction(extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy")
    assert "missed_items" not in off
    on_credit = build_score_from_extraction(
        extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", objection_credit_enabled=True,
    )
    assert "missed_items" in on_credit
    on_debrief = build_score_from_extraction(
        extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", debrief_v2_enabled=True,
    )
    assert "missed_items" in on_debrief
    # Flag-off is byte-identical to pre-T10 output: same score dict either way.
    baseline = build_score_from_extraction(extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy")
    assert off == baseline


def test_objection_credit_off_by_default_ignores_objections():
    with_objection = build_score_from_extraction(extraction=OBJECTION_HANDLED_EXTRACTION, memo=MEMO, input_revision="rev-obj")
    without_objection = build_score_from_extraction(extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy")
    assert with_objection["value"] == without_objection["value"]
    assert "missed_items" not in with_objection


def test_easy_call_does_not_outscore_a_well_handled_objection():
    easy = build_score_from_extraction(
        extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", objection_credit_enabled=True,
    )
    handled = build_score_from_extraction(
        extraction=OBJECTION_HANDLED_EXTRACTION, memo=MEMO, input_revision="rev-obj", objection_credit_enabled=True,
    )
    assert handled["value"] > easy["value"]
    assert _objection_misses(handled) == []


def test_objection_left_open_with_a_rep_turn_after_is_missed():
    easy = build_score_from_extraction(
        extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", objection_credit_enabled=True,
    )
    open_objection = build_score_from_extraction(
        extraction=OBJECTION_OPEN_EXTRACTION, memo=MEMO, input_revision="rev-open", objection_credit_enabled=True,
    )
    assert open_objection["value"] <= easy["value"]
    misses = _objection_misses(open_objection)
    assert len(misses) == 1
    assert misses[0]["category"] == "price"


def test_objection_left_open_with_no_further_signal_is_unknown_not_missed():
    """Never missed on missing data: the transcript just stops after the objection."""
    scored = build_score_from_extraction(
        extraction=OBJECTION_OPEN_NO_SIGNAL_EXTRACTION, memo=MEMO, input_revision="rev-cut", objection_credit_enabled=True,
    )
    assert _objection_misses(scored) == []


def test_objection_without_objections_is_not_scored_or_penalized():
    """No objections at all: the criterion never appears, so a friction-free call is untouched."""
    on = build_score_from_extraction(extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", objection_credit_enabled=True)
    off = build_score_from_extraction(extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", objection_credit_enabled=False)
    assert on["value"] == off["value"]
    assert on["applicable_steps"] == off.get("applicable_steps")


# Coherence with the playbook: a mark needs enough steps judged, and objections only count
# against the playbook when the playbook says how to answer them.

def _steps_extraction(statuses: list[str], *, revision: str = "rev-cov") -> dict:
    observations = [
        {
            "step_id": f"s{index}",
            "label": f"Paso {index}",
            "criterion": f"Hace el paso {index}",
            "status": status,
            "quote": "Quedamos el jueves" if status in {"met", "missed"} else None,
            "evidence_refs": ["ev-1"] if status in {"met", "missed"} else [],
        }
        for index, status in enumerate(statuses, start=1)
    ]
    return {
        "summary": "Llamada",
        "intelligence": {
            "version": 1,
            "input_revision": revision,
            "objections": [],
            "playbook_observations": observations,
            "evidence": _EVIDENCE,
        },
    }


def test_one_step_judged_out_of_five_is_not_a_ten():
    score = build_score_from_extraction(
        extraction=_steps_extraction(["met", "unknown", "unknown", "unknown", "unknown"]),
        memo=MEMO,
        input_revision="rev-cov",
    )
    assert score["value"] is None
    assert score["status"] == "partial"
    assert score["reason"] == "insufficient_evidence"
    assert score["coverage"] == 0.2
    # The cited line is still there for the debrief.
    assert score["strengths"] == ["Paso 1: «Quedamos el jueves»"]


def test_half_the_steps_judged_publishes_a_mark():
    score = build_score_from_extraction(
        extraction=_steps_extraction(["met", "missed", "unknown", "unknown"]),
        memo=MEMO,
        input_revision="rev-cov",
    )
    assert score["status"] == "ready"
    assert score["value"] == 5


def test_steps_that_did_not_apply_do_not_lower_coverage():
    score = build_score_from_extraction(
        extraction=_steps_extraction(["met", "met", "not_applicable", "not_applicable", "unknown"]),
        memo=MEMO,
        input_revision="rev-cov",
    )
    assert score["value"] == 10


def test_objection_the_playbook_has_no_answer_for_does_not_count():
    open_objection = build_score_from_extraction(
        extraction=OBJECTION_OPEN_EXTRACTION,
        memo=MEMO,
        input_revision="rev-open",
        objection_credit_enabled=True,
        answered_categories=frozenset({"timing"}),
    )
    easy = build_score_from_extraction(
        extraction=EASY_EXTRACTION, memo=MEMO, input_revision="rev-easy", objection_credit_enabled=True,
    )
    assert _objection_misses(open_objection) == []
    assert open_objection["value"] == easy["value"]


def test_objection_the_playbook_answers_still_counts():
    open_objection = build_score_from_extraction(
        extraction=OBJECTION_OPEN_EXTRACTION,
        memo=MEMO,
        input_revision="rev-open",
        objection_credit_enabled=True,
        answered_categories=frozenset({"price"}),
    )
    assert len(_objection_misses(open_objection)) == 1


def test_improvements_from_cited_steps_are_marked_cited():
    score = build_score_from_extraction(
        extraction=_steps_extraction(["met", "missed"]), memo=MEMO, input_revision="rev-cov",
    )
    assert score["improvements"] == ["Paso 2: Hace el paso 2"]
    assert score["improvements_cited"] is True


def test_answered_categories_come_from_the_pinned_version_entries_with_an_answer():
    from types import SimpleNamespace

    from app.services.intelligence.extract import pinned_playbook_answer_categories

    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def limit(self, *_a):
            return self

        def execute(self):
            return SimpleNamespace(data=self._rows)

    entries = [
        {"category": "Price", "guidance": "¿Comparado con qué?"},
        {"category": "timing", "guidance": "  "},
    ]
    fake = SimpleNamespace(table=lambda _name: _Query([{"entries": entries}]))
    assert pinned_playbook_answer_categories(fake, {"playbook_version_id": "pv-1"}) == frozenset({"price"})
    assert pinned_playbook_answer_categories(fake, {}) is None
