"""The improvement queue and the numbers behind it. Verdicts are computed later and in batches from stored data; an answer
reaches the Head of Sales' queue only after three or more failing cases in thirty days."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.services.playbooks.assistant_store import InMemoryAssistantStore
from app.services.playbooks.review_queue import (
    case_mark,
    coverage_stats,
    failing_by_answer,
    moments_by_answer,
    refresh_moments,
    refresh_outcomes,
)
from tests.playbooks.test_structure import FakeLLM
from tests.reporting.fake_db import FakeDB

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
COMPANY = "co-1"


def day(n):
    return (NOW - timedelta(days=n)).isoformat()


def row(event_id, used, resolved, *, source="objection:price", days=3, **extra):
    return {
        "event_id": event_id, "used": used, "resolved": resolved, "source_id": source, "observed_at": day(days),
        "client_text": "Es caro", "suggestion_text": "Pregunta cuánto pierden.", "rep_text": "Entiendo.", "sales_motion_key": "discovery",
        "objection_type": "price", "entry_id": None, **extra,
    }


def test_a_case_is_a_success_a_failure_a_suggestion_not_used_or_unknown():
    assert case_mark(row("a", "used", "resolved")) == "success"
    assert case_mark(row("a", "adapted", "resolved")) == "success"
    assert case_mark(row("a", "used", "not_resolved")) == "failed"
    assert case_mark(row("a", "not_used", "unknown")) == "unused"
    assert case_mark(row("a", "unknown", "unknown")) == "unknown"
    assert case_mark(row("a", "used", "unknown")) == "unknown"


def test_an_answer_needs_three_failing_cases_in_thirty_days_to_reach_the_queue():
    rows = [row("1", "not_used", "unknown"), row("2", "used", "not_resolved"), row("3", "not_used", "unknown"), row("4", "used", "resolved")]
    [group] = failing_by_answer(rows, now=NOW)
    assert group["answer_key"] == "objection:price" and group["failing"] == 3 and group["total"] == 4
    assert [c["event_id"] for c in group["cases"]] == ["1", "2", "3"] and group["marks"] == ["unused", "failed", "unused", "success"]
    assert failing_by_answer(rows[:2], now=NOW) == []


def test_old_cases_and_general_help_do_not_count_and_the_worst_answer_comes_first():
    rows = [row(str(i), "not_used", "unknown", days=40) for i in range(5)]  # too old
    rows += [row(str(10 + i), "not_used", "unknown", source=None) for i in range(5)]  # no approved answer: a gap, not a failing answer
    rows += [row(str(20 + i), "not_used", "unknown", source="objection:timing") for i in range(3)]
    rows += [row(str(30 + i), "not_used", "unknown", source="objection:price") for i in range(4)]
    assert [g["answer_key"] for g in failing_by_answer(rows, now=NOW)] == ["objection:price", "objection:timing"]


def test_the_same_kind_of_answer_in_two_call_types_is_counted_apart():
    rows = [row(str(i), "not_used", "unknown", sales_motion_key="discovery") for i in range(2)]
    rows += [row(str(10 + i), "not_used", "unknown", sales_motion_key="closing") for i in range(2)]
    assert failing_by_answer(rows, now=NOW) == []  # two and two are not three of one answer
    rows.append(row("20", "not_used", "unknown", sales_motion_key="closing"))
    [group] = failing_by_answer(rows, now=NOW)
    assert group["sales_motion_key"] == "closing" and group["failing"] == 3 and group["total"] == 3


def test_coverage_is_the_share_of_what_customers_raised_that_had_an_approved_answer():
    events = [
        {"created_at": day(2), "is_objection": True, "source_id": "objection:price"},
        {"created_at": day(3), "is_objection": True, "source_id": "objection:timing"},
        {"created_at": day(4), "is_objection": True, "source_id": "objection:custom:x"},
        {"created_at": day(5), "is_objection": True, "source_id": None},
        {"created_at": day(6), "is_objection": False, "source_id": None},
        {"created_at": day(40), "is_objection": True, "source_id": None},
    ]
    assert coverage_stats(events, now=NOW) == {"detected": 4, "answered": 3, "rate": 0.75}
    few = coverage_stats(events[:2], now=NOW)
    assert few == {"detected": 2, "answered": 2, "rate": None}
    assert coverage_stats([], now=NOW) == {"detected": 0, "answered": 0, "rate": None}


# --- refreshing in batches, later and apart ------------------------------------------------------------------


def make_db(count=3, *, young=0, no_reading=0):
    events, memos = [], []
    for i in range(count + young + no_reading):
        hours = 1 if i >= count and i < count + young else 30
        has_reading = not (i >= count + young)
        events.append({
            "id": f"e{i}", "company_id": COMPANY, "kind": "suggest", "is_objection": True, "created_at": (NOW - timedelta(hours=hours)).isoformat(),
            "capture_id": f"m{i}", "latest_turn": f"Es muy caro para nosotros caso {i}", "objection_type": "price", "source_id": "objection:price",
            "say_this": "Pregunta cuánto pierden.", "sales_motion_key": "discovery",
        })
        extraction = {"intelligence": {"objections": [{"kind": "objection", "category": "price", "quote": f"Es muy caro para nosotros caso {i}", "response": "¿Cuánto pierden hoy?", "resolution": "resolved"}]}} if has_reading else None
        memos.append({"id": f"m{i}", "company_id": COMPANY, "transcript": "x", "extraction": extraction})
    return FakeDB({"live_assist_events": events, "memos": memos})


def refresh(db, store, **kwargs):
    return asyncio.run(refresh_outcomes(store, db, COMPANY, llm=FakeLLM({"used": "used"}), now=NOW, **kwargs))


def test_only_cards_whose_call_is_closed_and_read_are_judged_and_never_twice():
    db, store = make_db(3, young=2, no_reading=1), InMemoryAssistantStore()
    assert refresh(db, store) == 3
    assert sorted(r["event_id"] for r in store.list_outcomes(COMPANY, since=day(30))) == ["e0", "e1", "e2"]
    assert refresh(db, store) == 0


def test_a_batch_is_bounded_and_the_next_one_goes_on_where_it_stopped():
    db, store = make_db(5), InMemoryAssistantStore()
    assert refresh(db, store, limit=2) == 2
    assert refresh(db, store, limit=2) == 2
    assert refresh(db, store, limit=2) == 1
    assert len(store.list_outcomes(COMPANY, since=day(30))) == 5


def test_a_failing_model_still_stores_unknown_verdicts_instead_of_losing_the_batch():
    db, store = make_db(2), InMemoryAssistantStore()
    assert asyncio.run(refresh_outcomes(store, db, COMPANY, llm=FakeLLM(RuntimeError("boom")), now=NOW)) == 2
    assert {r["used"] for r in store.list_outcomes(COMPANY, since=day(30))} == {"unknown"}


def test_nothing_is_judged_for_another_company_or_without_events():
    store = InMemoryAssistantStore()
    assert asyncio.run(refresh_outcomes(store, FakeDB(), COMPANY, llm=FakeLLM({}), now=NOW)) == 0
    assert asyncio.run(refresh_outcomes(store, make_db(2), "co-2", llm=FakeLLM({}), now=NOW)) == 0


# --- the queue ------------------------------------------------------------------------------------------------


def test_the_failing_cases_become_moments_once():
    store = InMemoryAssistantStore()
    group = failing_by_answer([row(str(i), "not_used", "unknown") for i in range(3)], now=NOW)
    assert refresh_moments(store, COMPANY, group) == 3
    assert refresh_moments(store, COMPANY, group) == 0
    moments = store.list_moments(COMPANY, status="open")
    assert len(moments) == 3 and all(m["entry_id"] == "objection:price" and m["source"] == "real" for m in moments)
    assert {m["outcome"]["event_id"] for m in moments} == {"0", "1", "2"}


def test_moments_are_shown_by_answer_with_the_numbers_of_that_answer():
    store = InMemoryAssistantStore()
    rows = [row("1", "not_used", "unknown"), row("2", "used", "not_resolved"), row("3", "not_used", "unknown"), row("4", "used", "resolved")]
    refresh_moments(store, COMPANY, failing_by_answer(rows, now=NOW))
    [group] = moments_by_answer(store.list_moments(COMPANY, status="open"), rows, now=NOW)
    assert group["answer_key"] == "objection:price" and group["failing"] == 3 and len(group["moments"]) == 3
    assert group["marks"] == ["unused", "failed", "unused", "success"]
    assert group["stats"]["resolved"] == 1 and group["stats"]["rate"] is None  # one clear case: no percentage
