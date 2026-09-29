"""Suggested questions come from what the account actually has, never from a fixed list."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.crm_copilot import suggestions
from tests.crm_copilot.fakes import FakeCompanyService, FakeSupabase

NOW = datetime.now(timezone.utc)


def _memo(mid, user="u1", objection=False, days=2, intelligence=True):
    block = {"interest": "high", "objections": [{"kind": "objection", "category": "price", "resolution": "open", "quote": "caro"}] if objection else []}
    return {
        "id": mid, "user_id": user, "company_id": "co", "status": "approved", "created_at": (NOW - timedelta(days=days)).isoformat(),
        "extraction": {"summary": "x", **({"intelligence": block} if intelligence else {})},
    }


def _ids(db, role="member", crm=False, members=("u1", "u2")):
    return suggestions.compute(
        db, company_id="co", user_id="u1", role=role,
        member_ids=list(members) if role in ("owner", "admin") else ["u1"],
        has_crm=crm,
    )


def test_a_brand_new_account_gets_no_suggestions_at_all():
    assert _ids(FakeSupabase(memos=[])) == []


def test_open_loops_appear_once_there_are_recent_conversations():
    assert "open_loops" in _ids(FakeSupabase(memos=[_memo("a")]))
    assert "open_loops" not in _ids(FakeSupabase(memos=[_memo("a", days=200)]))


def test_the_objection_question_needs_an_analysed_objection():
    assert "objections" not in _ids(FakeSupabase(memos=[_memo("a", objection=False)]))
    assert "objections" not in _ids(FakeSupabase(memos=[_memo("a", objection=True, intelligence=False)]))
    assert "objections" in _ids(FakeSupabase(memos=[_memo("a", objection=True)]))


def test_crm_questions_need_a_crm_even_with_no_conversations():
    assert _ids(FakeSupabase(memos=[]), crm=True) == ["connection_rate", "lost_reasons"]


def test_a_member_never_gets_a_team_question():
    playbook = dict(
        playbooks=[{"id": "p", "company_id": "co", "sales_motion_key": "d", "active_version_id": "v"}],
        playbook_versions=[{"id": "v", "playbook_id": "p", "status": "published", "steps": [], "entries": [{"category": "price", "approved_answer": "x"}]}],
    )
    db = FakeSupabase(memos=[_memo("a", objection=True)], **playbook)
    assert "team_adherence" not in _ids(db, role="member")
    assert "team_adherence" in _ids(db, role="admin")


def test_the_playbook_question_needs_a_published_playbook_with_entries():
    assert "playbook" not in _ids(FakeSupabase(memos=[_memo("a")]))


def test_at_most_four_and_in_priority_order():
    db = FakeSupabase(memos=[_memo("a", objection=True)])
    out = _ids(db, crm=True)
    assert len(out) <= 4 and out[0] == "open_loops"
