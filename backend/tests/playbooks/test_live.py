"""services/playbooks/live.py: the one place that says what applies to a call (plan section 17.3).

A playbook applies when it has a published version, is switched on and is not deleted. Pausing keeps the version
(`state = 'paused'`) and deleting sets `archived_at`; neither touches `active_version_id`, so every reader goes through
the view `playbooks_live` and none of them knows about either. The readers are exercised here against a fake database
whose `playbooks_live` is the Python double of the view (tests/playbooks/live_double.py); one test runs the double
against the real view on PostgreSQL so the two cannot drift.
"""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest

from app.api.briefs import _closing_playbook_steps, _playbook_for_memo
from app.config import settings
from app.services import feature_flags
from app.services.captures import playbook_fields_for_capture
from app.services.coaching.rep_coaching_reads import load_published_playbook
from app.services.copilot.load_grounding import load_company_suggest_grounding
from app.services.playbooks import live
from tests.playbooks.live_double import live_view_rows
from tests.reporting.fake_db import FakeDB

CO = "co-1"
STEPS = [{"step_id": "open", "label": "Apertura", "criterion": "Se presenta"}]
ENTRIES = [{"entry_id": "p1", "category": "price", "guidance": "Habla de valor", "source_ref": "pb:1"}]


def _db(*playbooks: dict) -> FakeDB:
    """A fake database with one playbook per dict: {key, state?, archived?, published?}; each has a published version
    `v-<key>` (and, with published=False, a draft one that nothing points at)."""
    rows, versions = [], []
    for spec in playbooks:
        key = spec["key"]
        published = spec.get("published", True)
        rows.append({
            "id": f"pb-{key}", "company_id": CO, "sales_motion_key": key,
            "active_version_id": f"v-{key}" if published else None,
            "state": spec.get("state", "active"),
            "archived_at": "2026-09-30T08:00:00Z" if spec.get("archived") else None,
        })
        versions.append({
            "id": f"v-{key}", "playbook_id": f"pb-{key}", "status": "published" if published else "draft",
            "steps": STEPS, "entries": ENTRIES, "qualification": [],
        })
    return FakeDB({"playbooks": rows, "playbook_versions": versions, "memos": [], "company_feature_flags": []})


@pytest.fixture
def roles_on(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", False)
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


# --- the definition ---------------------------------------------------------------------------


def test_only_an_active_published_undeleted_playbook_is_live():
    db = _db(
        {"key": "discovery"},
        {"key": "closing", "state": "paused"},
        {"key": "inbound", "archived": True},
        {"key": "negotiation", "published": False},
        {"key": "renewal", "state": "paused", "archived": True},
    )
    assert [row["sales_motion_key"] for row in live.live_versions(db, CO)] == ["discovery"]
    assert live.live_version_id(db, CO, "discovery") == "v-discovery"
    for gone in ("closing", "inbound", "negotiation", "renewal", "ghost", None, ""):
        assert live.live_version_id(db, CO, gone) is None
    assert [s["sales_motion_key"] for s in live.live_snapshots(db, CO)] == ["discovery"]
    snapshot = live.live_snapshot(db, CO, "discovery")
    assert snapshot == {
        "playbook_id": "pb-discovery", "version_id": "v-discovery", "sales_motion_key": "discovery",
        "steps": STEPS, "entries": ENTRIES, "qualification": [],
    }
    assert live.live_snapshot(db, CO, "closing") is None


def test_another_company_never_shows_up():
    db = _db({"key": "discovery"})
    assert live.live_versions(db, "co-2") == []
    assert live.live_version_id(db, "co-2", "discovery") is None
    assert live.live_snapshots(db, "co-2") == []


def test_live_snapshots_are_ordered_and_read_versions_once():
    db = _db({"key": "closing"}, {"key": "discovery"}, {"key": "inbound"})
    assert [s["sales_motion_key"] for s in live.live_snapshots(db, CO)] == ["closing", "discovery", "inbound"]
    db.calls.clear()
    live.live_snapshots(db, CO)
    assert db.calls == [("playbooks_live", "select"), ("playbook_versions", "select")]


def test_a_version_that_is_not_published_is_not_a_snapshot():
    db = _db({"key": "discovery"})
    db.tables["playbook_versions"][0]["status"] = "draft"
    assert live.live_snapshots(db, CO) == []


def test_a_failed_read_never_blocks_a_call_but_is_not_hidden_from_the_others():
    db = _db({"key": "discovery"})
    db.fail_tables = {"playbooks_live"}
    assert live.live_version_id(db, CO, "discovery") is None  # a call is never blocked by it
    with pytest.raises(RuntimeError):
        live.live_versions(db, CO)
    with pytest.raises(RuntimeError):
        live.live_snapshots(db, CO)


def test_has_published_playbook_counts_paused_but_not_deleted_or_unpublished():
    assert live.has_published_playbook(_db({"key": "discovery"}), CO) is True
    assert live.has_published_playbook(_db({"key": "discovery", "state": "paused"}), CO) is True
    assert live.has_published_playbook(_db({"key": "discovery", "archived": True}), CO) is False
    assert live.has_published_playbook(_db({"key": "discovery", "published": False}), CO) is False
    assert live.has_published_playbook(_db(), CO) is False


def test_a_call_keeps_the_version_it_started_with_whatever_the_switch_says():
    db = _db({"key": "discovery", "state": "paused"})
    assert live.live_snapshots(db, CO) == []
    pinned = live.pinned_snapshot(db, CO, "discovery", "v-discovery")
    assert pinned["version_id"] == "v-discovery" and pinned["steps"] == STEPS
    assert live.pinned_snapshot(db, CO, "discovery", "v-other") is None
    assert live.pinned_snapshot(db, CO, "ghost", "v-discovery") is None
    db.tables["playbook_versions"][0]["status"] = "draft"
    assert live.pinned_snapshot(db, CO, "discovery", "v-discovery") is None


# --- the readers ------------------------------------------------------------------------------


def _pin(db, **kwargs):
    kwargs.setdefault("interaction_kind", "call")
    kwargs.setdefault("sales_role", "sdr")
    return playbook_fields_for_capture(db, CO, **kwargs)


def test_a_paused_or_deleted_type_is_never_pinned(roles_on):
    db = _db({"key": "discovery"})
    row = db.tables["playbooks"][0]
    assert _pin(db) == {"sales_motion_key": "discovery", "playbook_version_id": "v-discovery"}

    row["state"] = "paused"
    assert _pin(db) == {}
    # Asking for it by name pins the type but no version: there is nothing live to snapshot.
    assert _pin(db, sales_motion_key="discovery") == {"sales_motion_key": "discovery"}
    assert _pin(db, default_when_unspecified=True, interaction_kind=None, sales_role=None) == {}

    row["state"] = "active"
    assert _pin(db) == {"sales_motion_key": "discovery", "playbook_version_id": "v-discovery"}

    row["archived_at"] = "2026-09-30T08:00:00Z"
    assert _pin(db) == {}
    row["archived_at"] = None
    assert _pin(db)["playbook_version_id"] == "v-discovery"


def test_copilot_briefs_and_coaching_reads_ignore_a_paused_playbook():
    db = _db({"key": "closing"})
    row = db.tables["playbooks"][0]
    assert [s["sales_motion_key"] for s in live.live_snapshots(db, CO)] == ["closing"]
    assert load_company_suggest_grounding(db, company_id=CO).playbook_version_id == "v-closing"
    assert _closing_playbook_steps(db, CO) == STEPS
    assert load_published_playbook(db, CO, "closing")["published"] is True

    row["state"] = "paused"
    assert load_company_suggest_grounding(db, company_id=CO) is None
    assert _closing_playbook_steps(db, CO) == []
    assert load_published_playbook(db, CO, "closing") == {"published": False, "steps": [], "entries": []}

    row["state"] = "active"
    assert load_company_suggest_grounding(db, company_id=CO).playbook_version_id == "v-closing"
    assert load_published_playbook(db, CO, "closing")["published"] is True


def test_a_brief_reads_the_version_the_call_was_evaluated_with_even_when_the_playbook_is_paused():
    db = _db({"key": "closing", "state": "paused"})
    memo = {"created_at": "2026-09-30T08:00:00Z", "sales_motion_key": "closing", "playbook_version_id": "v-closing", "extraction": {}}
    steps, entries = _playbook_for_memo(db, CO, [memo])
    assert steps == STEPS and entries == ENTRIES
    # a call with no version of its own reads what applies now: nothing while paused
    assert _playbook_for_memo(db, CO, [{**memo, "playbook_version_id": None}]) == ([], [])


# --- the double is the view -------------------------------------------------------------------


def test_the_python_double_answers_like_the_sql_view(pg):
    company = "11111111-1111-1111-1111-111111111111"
    cases = [
        ("live", "active", False, True), ("paused", "paused", False, True), ("deleted", "active", True, True),
        ("deleted_paused", "paused", True, True), ("draft_only", "active", False, False),
    ]
    rows = []
    for index, (key, state, archived, published) in enumerate(cases):
        pb = f"a0000000-0000-0000-0000-00000000000{index}"
        version = f"b0000000-0000-0000-0000-00000000000{index}"
        pg.sql(
            f"INSERT INTO playbooks (id, company_id, sales_motion_key, state, archived_at) VALUES "
            f"('{pb}', '{company}', '{key}', '{state}', {'now()' if archived else 'NULL'});"
        )
        pg.sql(f"INSERT INTO playbook_versions (id, playbook_id, status) VALUES ('{version}', '{pb}', '{'published' if published else 'draft'}');")
        if published:
            pg.sql(f"UPDATE playbooks SET active_version_id = '{version}' WHERE id = '{pb}';")
        rows.append({
            "id": pb, "company_id": company, "sales_motion_key": key, "state": state,
            "archived_at": "x" if archived else None, "active_version_id": version if published else None,
        })
    sql_rows = pg.sql(
        "SELECT COALESCE(string_agg(playbook_id || ',' || sales_motion_key || ',' || version_id, ';' ORDER BY sales_motion_key), '') FROM playbooks_live"
    )
    double = ";".join(
        f"{r['playbook_id']},{r['sales_motion_key']},{r['version_id']}"
        for r in sorted(live_view_rows(rows), key=lambda r: r["sales_motion_key"])
    )
    assert sql_rows == double == "a0000000-0000-0000-0000-000000000000,live,b0000000-0000-0000-0000-000000000000"
