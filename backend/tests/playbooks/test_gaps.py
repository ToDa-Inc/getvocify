"""What Vocify still has to ask the Head of Sales: typical questions the material does not answer, questions real
prospects asked that have no approved answer, and facts two documents disagree about. No form: a list that shrinks
as the playbook fills up."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.playbooks.gaps import (
    Gap,
    build_gaps,
    detect_conflicts,
    gap_from_dict,
    recent_suggest_events,
)
from tests.reporting.fake_db import FakeDB

COMPANY = "co-1"


def event(turn, *, source_id=None, is_objection=True, motion="discovery", n=0):
    return {
        "id": f"e-{turn[:6]}-{n}", "created_at": "2026-10-10T10:00:00+00:00", "sales_motion_key": motion,
        "latest_turn": turn, "is_objection": is_objection, "source_id": source_id, "kind": "suggest",
    }


def test_an_empty_company_gets_the_typical_topics_in_a_stable_order():
    gaps = build_gaps(entries=[], knowledge={}, events=[], lang="es")
    assert 1 <= len(gaps) <= 10
    assert all(g.kind == "topic" and g.seen == 0 for g in gaps)
    assert gaps[0].key == "topic:pricing" and "¿Cuánto cuesta?" in gaps[0].question
    assert [g.key for g in gaps] == [g.key for g in build_gaps(entries=[], knowledge={}, events=[], lang="es")]


def test_an_own_question_that_mentions_a_topic_covers_it():
    entries = [{"category": "custom", "label": "Integración con Salesforce", "trigger": "¿Se integra con Salesforce?", "guidance": "Sí."}]
    keys = [g.key for g in build_gaps(entries=entries, knowledge={}, events=[], lang="es")]
    assert "topic:integrations" not in keys and "topic:pricing" in keys


def test_the_questions_come_in_english_for_an_english_company():
    gaps = build_gaps(entries=[], knowledge={}, events=[], lang="en")
    assert "How much does it cost?" in gaps[0].question


def test_a_question_prospects_really_asked_comes_first_with_how_often():
    turn = "Y si no nos gusta, ¿cómo cancelamos el servicio?"
    events = [event(turn, n=i) for i in range(3)] + [event("¿Tenéis app para el móvil de los comerciales?")]
    gaps = build_gaps(entries=[], knowledge={}, events=events, lang="es")
    assert gaps[0].kind == "real" and gaps[0].seen == 3 and gaps[0].example == turn
    assert gaps[0].motion_key == "discovery" and turn in gaps[0].question
    assert gaps[1].kind == "real" and gaps[1].seen == 1


def test_cards_that_followed_an_approved_answer_or_were_not_objections_are_not_gaps():
    events = [
        event("Es muy caro para nosotros, la verdad", source_id="objection:price"),
        event("Sí, claro, perfecto, me parece bien todo", is_objection=False),
        event("Hola"),
    ]
    gaps = build_gaps(entries=[], knowledge={}, events=events, lang="es")
    assert all(g.kind == "topic" for g in gaps)


def test_conflicts_go_after_real_questions_and_before_topics():
    conflict = Gap("conflict:pricing", "conflict", "Dos precios", "req", 0, None, None)
    events = [event("¿Tenéis app para el móvil de los comerciales?")]
    kinds = [g.kind for g in build_gaps(entries=[], knowledge={}, events=events, lang="es", conflicts=[conflict])]
    assert kinds[:2] == ["real", "conflict"] and set(kinds[2:]) == {"topic"}


def test_the_list_is_cut_at_the_limit():
    assert len(build_gaps(entries=[], knowledge={}, events=[], lang="es")) == 9
    assert len(build_gaps(entries=[], knowledge={}, events=[], lang="es", limit=4)) == 4


def test_two_documents_with_different_figures_for_the_same_fact_are_a_conflict():
    found = detect_conflicts({"pricing": "Desde 39 € al mes por usuario."}, {"pricing": "Desde 49 € al mes por usuario."}, "es")
    assert [g.key for g in found] == ["conflict:pricing"]
    assert "39" in found[0].question and "49" in found[0].question


def test_same_figures_missing_values_or_no_figures_are_not_a_conflict():
    assert detect_conflicts({"pricing": "Desde 39 € al mes."}, {"pricing": "39 € al mes por usuario."}, "es") == []
    assert detect_conflicts({}, {"pricing": "Desde 39 € al mes."}, "es") == []
    assert detect_conflicts({"icp": "Gestorías pequeñas."}, {"icp": "Gestorías medianas."}, "es") == []


def test_a_gap_survives_being_stored():
    gap = build_gaps(entries=[], knowledge={}, events=[event("¿Tenéis app para el móvil de los comerciales?")], lang="es")[0]
    assert gap_from_dict(gap.as_dict()) == gap


def test_recent_events_are_this_companys_cards_from_the_last_weeks():
    now = datetime.now(timezone.utc)
    rows = [
        {"id": "a", "company_id": COMPANY, "kind": "suggest", "created_at": (now - timedelta(days=2)).isoformat(), "latest_turn": "x"},
        {"id": "old", "company_id": COMPANY, "kind": "suggest", "created_at": (now - timedelta(days=60)).isoformat(), "latest_turn": "x"},
        {"id": "turn", "company_id": COMPANY, "kind": "turn", "created_at": (now - timedelta(days=1)).isoformat(), "latest_turn": "x"},
        {"id": "other", "company_id": "co-2", "kind": "suggest", "created_at": (now - timedelta(days=1)).isoformat(), "latest_turn": "x"},
    ]
    db = FakeDB({"live_assist_events": rows})
    assert [r["id"] for r in recent_suggest_events(db, COMPANY, days=28)] == ["a"]


def test_a_failing_read_gives_no_events():
    assert recent_suggest_events(FakeDB(fail_tables=["live_assist_events"]), COMPANY) == []
