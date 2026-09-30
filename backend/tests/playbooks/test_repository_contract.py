"""The playbooks repository contract (plan section 17.5).

Every scenario runs against InMemoryPlaybookRepository (the test fake the API tests use) AND SqlPlaybookRepository over a
real PostgreSQL (the SQL functions of migration 066_playbooks_v2), so the fake cannot drift from what production does.
The SQL variants are skipped only when no PostgreSQL is available (tests/playbooks/pg_support.py: VOCIFY_TEST_PG_DSN or a
throwaway cluster). The last section is SQL-only: what only a database can show (rows, races, rollbacks).
"""

from __future__ import annotations

import copy
import os
import threading
import time
import uuid

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest

from app.services.playbooks.knowledge import StaleKnowledgeError
from app.services.playbooks.repository import (
    UNSET,
    InMemoryPlaybookRepository,
    PlaybookRepository,
    PlaybookRepositoryError,
    SqlPlaybookRepository,
)
from app.services.playbooks.versions import (
    LifecycleError,
    PublishError,
    StaleDraftError,
    is_newer,
    parse_ts,
)
from tests.playbooks import pg_support

CO = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"

STEPS = [{"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta"}]
ENTRIES = [{"entry_id": "objection:price", "category": "price", "guidance": "ROI", "source_ref": "editor"}]
CRITERIA = [{"criterion_id": "presupuesto", "label": "Presupuesto", "why": "Sin presupuesto no hay compra."}]
RULE = {"role": "any", "channels": [], "contact": "any", "deal_stages": []}


def steps(label: str = "Apertura", criterion: str = "Se presenta") -> list[dict]:
    return [{"step_id": "apertura", "label": label, "criterion": criterion}]


def js_iso(value: str) -> str:
    """What a browser sends back after a round trip through a JS Date: milliseconds, `Z`."""
    parsed = parse_ts(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"


@pytest.fixture(params=["memory", "sql"])
def repo(request) -> PlaybookRepository:
    if request.param == "memory":
        return InMemoryPlaybookRepository()
    return SqlPlaybookRepository(request.getfixturevalue("pg"))


def editor(repo, key="discovery", *, draft=True):
    return repo.editor_snapshot(CO, key, include_draft=draft)


def status(repo, key="discovery", **kwargs):
    return (repo.list_types(CO, **kwargs).get(key) or {}).get("status")


def live(repo, key="discovery", label="Apertura", **extra):
    repo.save_draft(CO, key, steps(label), ENTRIES, **extra)
    return repo.publish(CO, key)


# --- drafts -------------------------------------------------------------------------------------


def test_ten_saves_are_one_version_and_the_editor_shows_the_last(repo):
    versions = [repo.save_draft(CO, "discovery", steps(criterion=f"Se presenta {i}"), ENTRIES) for i in range(10)]
    assert len({v["id"] for v in versions}) == 1
    stamps = [v["updated_at"] for v in versions]
    assert all(is_newer(b, a) for a, b in zip(stamps, stamps[1:]))
    snapshot = editor(repo)
    assert snapshot["state"] == "draft" and snapshot["has_live"] is False and snapshot["paused"] is False
    assert snapshot["version"]["id"] == versions[0]["id"]
    assert snapshot["version"]["steps"][0]["criterion"] == "Se presenta 9"
    assert snapshot["version"]["updated_at"] == stamps[-1]
    assert snapshot["version"]["status"] == "draft"


def test_the_saved_version_carries_what_was_saved(repo):
    saved = repo.save_draft(CO, "discovery", STEPS, ENTRIES, qualification=CRITERIA)
    assert set(saved) >= {"id", "status", "steps", "entries", "qualification", "created_at", "updated_at"}
    assert saved["steps"] == STEPS and saved["entries"] == ENTRIES and saved["qualification"] == CRITERIA
    assert saved["status"] == "draft"


def test_the_editor_of_a_type_with_nothing_is_empty(repo):
    assert editor(repo) == {"state": "empty", "version": None, "has_live": False, "source": None, "paused": False}
    assert repo.discard_draft(CO, "discovery") is False
    repo.add_type(CO, "renewal", "Renovación")
    assert editor(repo, "renewal")["state"] == "empty"


def test_publish_then_edit_creates_a_new_draft_and_leaves_the_published_one(repo):
    first = repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    assert repo.publish(CO, "discovery") == first["id"]
    published = editor(repo)
    assert published["state"] == "published" and published["has_live"] is True
    assert published["version"]["id"] == first["id"] and published["version"]["status"] == "published"

    edited = repo.save_draft(CO, "discovery", steps("Otra"), [], base_updated_at=published["version"]["updated_at"])
    assert edited["id"] != first["id"]
    snapshot = editor(repo)
    assert snapshot["state"] == "draft" and snapshot["version"]["id"] == edited["id"] and snapshot["has_live"] is True
    assert editor(repo, draft=False)["state"] == "published"
    assert editor(repo, draft=False)["version"]["steps"][0]["label"] == "Apertura"
    assert repo.save_draft(CO, "discovery", STEPS, ENTRIES)["id"] == edited["id"]  # more edits stay on that draft


def test_a_stale_base_is_refused_and_changes_nothing(repo):
    one = repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    two = repo.save_draft(CO, "discovery", steps("Dos"), ENTRIES, base_updated_at=one["updated_at"])
    with pytest.raises(StaleDraftError):
        repo.save_draft(CO, "discovery", steps("Tres"), ENTRIES, base_updated_at=one["updated_at"])
    assert editor(repo)["version"]["steps"][0]["label"] == "Dos"
    # A base that went through a JS Date (milliseconds, Z) still matches.
    repo.save_draft(CO, "discovery", steps("Cuatro"), ENTRIES, base_updated_at=js_iso(two["updated_at"]))
    assert editor(repo)["version"]["steps"][0]["label"] == "Cuatro"


def test_an_unreadable_or_foreign_base_is_stale(repo):
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    for base in ("not a date", "2020-01-01T00:00:00Z"):
        with pytest.raises(StaleDraftError):
            repo.save_draft(CO, "discovery", steps("X"), ENTRIES, base_updated_at=base)
    assert editor(repo)["version"]["steps"][0]["label"] == "Apertura"


def test_a_draft_published_meanwhile_is_stale_and_not_overwritten(repo):
    one = repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    repo.publish(CO, "discovery")  # another manager activated it
    with pytest.raises(StaleDraftError):
        repo.save_draft(CO, "discovery", steps("Tarde"), ENTRIES, base_updated_at=one["updated_at"])
    assert editor(repo)["version"]["steps"][0]["label"] == "Apertura"
    assert editor(repo)["state"] == "published"


def test_a_first_save_over_a_published_version_needs_that_versions_updated_at(repo):
    live(repo)
    published = editor(repo)["version"]
    with pytest.raises(StaleDraftError):
        repo.save_draft(CO, "discovery", STEPS, ENTRIES, base_updated_at="2020-01-01T00:00:00Z")
    repo.save_draft(CO, "discovery", STEPS, ENTRIES, base_updated_at=published["updated_at"])
    # with no draft and no published version there is nothing a base could match
    with pytest.raises(StaleDraftError):
        repo.save_draft(CO, "closing", STEPS, ENTRIES, base_updated_at=published["updated_at"])


def test_discard_deletes_the_pending_draft_only(repo):
    published = live(repo)
    draft = repo.save_draft(CO, "discovery", steps("Otra"), ENTRIES)
    assert draft["id"] != published
    assert repo.discard_draft(CO, "discovery") is True
    snapshot = editor(repo)
    assert snapshot["state"] == "published" and snapshot["version"]["id"] == published
    assert repo.discard_draft(CO, "discovery") is False  # nothing pending: the published one stays
    assert status(repo) == "published"


def test_discarding_without_a_published_version_leaves_the_type_empty(repo):
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    assert status(repo) == "draft"
    assert repo.discard_draft(CO, "discovery") is True
    assert editor(repo)["state"] == "empty"
    assert status(repo) == "missing"


def test_a_draft_after_a_publish_is_the_pending_one_and_a_rep_never_sees_it(repo):
    published = live(repo)
    repo.save_draft(CO, "discovery", steps("Cambio a medias"), ENTRIES)
    manager = repo.list_types(CO, include_draft=True)["discovery"]
    rep = repo.list_types(CO, include_draft=False)["discovery"]
    assert manager["has_draft"] is True and manager["status"] == "published"
    assert rep["has_draft"] is False and rep["status"] == "published"
    assert editor(repo, draft=False)["version"]["id"] == published
    assert editor(repo, draft=True)["version"]["id"] != published


# --- the qualification round trip ----------------------------------------------------------------


def test_qualification_round_trip(repo):
    saved = repo.save_draft(CO, "discovery", STEPS, ENTRIES, qualification=CRITERIA)
    assert editor(repo)["version"]["qualification"] == CRITERIA
    assert repo.list_types(CO)["discovery"]["criteria_count"] == 1
    # None = "not sent": the draft keeps its criteria. [] = the manager cleared them.
    repo.save_draft(CO, "discovery", steps("Otra"), ENTRIES, qualification=None)
    assert editor(repo)["version"]["qualification"] == CRITERIA
    assert repo.save_draft(CO, "discovery", STEPS, ENTRIES, qualification=[])["qualification"] == []
    assert repo.list_types(CO)["discovery"]["criteria_count"] == 0
    repo.save_draft(CO, "discovery", STEPS, ENTRIES, qualification=CRITERIA)
    repo.publish(CO, "discovery")
    # a new draft over the published version starts from the published version's criteria
    fresh = repo.save_draft(CO, "discovery", steps("Nueva"), ENTRIES)
    assert fresh["id"] != saved["id"] and fresh["qualification"] == CRITERIA
    assert editor(repo, draft=False)["version"]["qualification"] == CRITERIA


# --- the list and its details --------------------------------------------------------------------


def test_the_list_says_status_counts_label_and_rule_per_type(repo):
    live(repo, "closing", qualification=CRITERIA)
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    repo.add_type(CO, "renewal", "Renovación", label="Renovación", applies_to=RULE)
    repo.add_type(CO, "sales", "Sales")
    listed = repo.list_types(CO)
    assert sorted(listed) == ["closing", "discovery", "renewal", "sales"]
    assert listed["closing"] == {
        "status": "published", "label": None, "applies_to": None, "step_count": 1, "answer_count": 1,
        "criteria_count": 1, "has_draft": False, "paused": False,
    }
    assert listed["discovery"]["status"] == "draft" and listed["discovery"]["has_draft"] is True
    assert listed["discovery"]["step_count"] == 1 and listed["discovery"]["answer_count"] == 1
    assert listed["renewal"]["status"] == "missing" and listed["renewal"]["label"] == "Renovación"
    assert listed["renewal"]["applies_to"] == RULE and listed["renewal"]["step_count"] == 0
    assert listed["sales"] == {
        "status": "missing", "label": None, "applies_to": None, "step_count": 0, "answer_count": 0,
        "criteria_count": 0, "has_draft": False, "paused": False,
    }


def test_the_counts_follow_the_version_the_editor_opens(repo):
    live(repo, label="Apertura")
    repo.save_draft(CO, "discovery", steps("Nueva") + [{"step_id": "cierre", "label": "Cierre", "criterion": "Agenda"}], [])
    manager = repo.list_types(CO, include_draft=True)["discovery"]
    rep = repo.list_types(CO, include_draft=False)["discovery"]
    assert (manager["step_count"], manager["answer_count"]) == (2, 0)  # the pending draft
    assert (rep["step_count"], rep["answer_count"]) == (1, 1)  # the published version


def test_everything_is_per_company(repo):
    live(repo)
    assert repo.list_types(OTHER) == {}
    assert repo.editor_snapshot(OTHER, "discovery", include_draft=True)["state"] == "empty"
    with pytest.raises(LifecycleError):
        repo.set_state(OTHER, "discovery", "pause")
    with pytest.raises(PublishError):
        repo.publish(OTHER, "discovery")
    assert repo.get_knowledge(OTHER) is None
    assert status(repo) == "published"


# --- publishing ----------------------------------------------------------------------------------


def test_publishing_turns_the_draft_into_the_published_version(repo):
    draft = repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    assert repo.publish(CO, "discovery") == draft["id"]
    assert status(repo) == "published"
    with pytest.raises(PublishError) as again:
        repo.publish(CO, "discovery")  # nothing pending any more
    assert again.value.code == "not_a_draft"
    for key in ("ghost",):
        with pytest.raises(PublishError) as ghost:
            repo.publish(CO, key)
        assert ghost.value.code == "not_a_draft"


def test_editing_a_published_playbook_and_publishing_again_activates_the_edit(repo):
    first = live(repo, label="Apertura")
    edited = repo.save_draft(CO, "discovery", steps("Apertura nueva"), ENTRIES)
    assert repo.publish(CO, "discovery") == edited["id"] != first
    snapshot = editor(repo)
    assert snapshot["state"] == "published" and snapshot["version"]["steps"][0]["label"] == "Apertura nueva"
    assert repo.list_types(CO)["discovery"]["has_draft"] is False


def test_publishing_only_touches_its_own_type(repo):
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    repo.save_draft(CO, "closing", STEPS, ENTRIES)
    repo.publish(CO, "discovery")
    assert status(repo, "discovery") == "published" and status(repo, "closing") == "draft"


def test_a_contradictory_import_blocks_publishing_until_the_editor_saves(repo):
    repo.add_type(CO, "discovery", "Discovery")
    record = {
        "import_id": "imp-c", "status": "ready", "published": False,
        "draft": {"text": "Nunca descuentes. Siempre cierra.", "contradictions": ["siempre/nunca"]},
    }
    repo.save_import(CO, record, "discovery")
    assert status(repo) == "draft"
    with pytest.raises(PublishError) as blocked:
        repo.publish(CO, "discovery")
    assert blocked.value.code == "contradiction"
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)  # the editor's draft supersedes the import
    repo.publish(CO, "discovery")
    assert status(repo) == "published"


# --- the legacy import -----------------------------------------------------------------------------


def _record(import_id="imp-1", text="Confirmar el problema", contradictions=None):
    return {"import_id": import_id, "status": "ready", "published": False,
            "draft": {"text": text, "contradictions": contradictions or []}}


def test_a_legacy_import_is_a_draft_and_idempotent_per_import_id(repo):
    repo.save_import(CO, _record(), "discovery")
    assert status(repo) == "draft"
    first = editor(repo)["version"]["id"]
    repo.save_import(CO, _record(text="Otro texto"), "discovery")  # same import id: nothing new
    assert editor(repo)["version"]["id"] == first
    got = repo.get_import(CO, "imp-1")
    assert got["import_id"] == "imp-1" and got["status"] == "ready" and got["published"] is False
    assert got["draft"]["text"] == "Confirmar el problema"
    assert repo.get_import(OTHER, "imp-1") is None and repo.get_import(CO, "nope") is None
    repo.save_import(CO, {**_record("imp-2"), "status": "failed"}, "discovery")  # only a ready import is a draft
    repo.save_import(CO, _record("imp-3"), None)  # nor without a type
    assert repo.get_import(CO, "imp-2") is None and repo.get_import(CO, "imp-3") is None
    repo.publish(CO, "discovery")
    assert status(repo) == "published"


def test_the_legacy_import_un_archives_a_deleted_type_empty(repo):
    live(repo, label="Viejo")
    repo.set_state(CO, "discovery", "archive")
    repo.save_import(CO, _record(), "discovery")
    assert status(repo) == "draft"
    snapshot = editor(repo)
    assert snapshot["has_live"] is False and snapshot["paused"] is False  # nothing of the old one


# --- pause, resume ---------------------------------------------------------------------------------


def test_pause_then_resume_round_trip(repo):
    published = live(repo, qualification=CRITERIA)
    repo.set_state(CO, "discovery", "pause")
    row = repo.list_types(CO)["discovery"]
    assert row["status"] == "paused" and row["paused"] is True
    assert row["step_count"] == 1 and row["criteria_count"] == 1 and row["has_draft"] is False  # the content stays
    shown = editor(repo)
    assert shown["state"] == "published" and shown["paused"] is True and shown["has_live"] is True
    assert shown["version"]["id"] == published and shown["version"]["qualification"] == CRITERIA
    repo.set_state(CO, "discovery", "resume")
    assert status(repo) == "published"
    back = editor(repo)
    assert back["paused"] is False and back["version"]["id"] == published  # the very version that was paused


def test_the_editor_says_paused_false_when_it_is_not(repo):
    assert editor(repo)["paused"] is False
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    assert editor(repo)["paused"] is False
    repo.publish(CO, "discovery")
    assert editor(repo)["paused"] is False


@pytest.mark.parametrize(
    "action, code", [("pause", "not_published"), ("resume", "not_paused"), ("archive", "not_found"), ("restore", "not_archived")],
)
def test_an_action_that_does_not_apply_says_why(repo, action, code):
    with pytest.raises(LifecycleError) as raised:
        repo.set_state(CO, "ghost", action)
    assert raised.value.code == code


def test_pausing_something_that_is_not_published_is_refused(repo):
    repo.add_type(CO, "renewal", "Renovación")
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    for key in ("renewal", "discovery", "ghost"):
        with pytest.raises(LifecycleError) as raised:
            repo.set_state(CO, key, "pause")
        assert raised.value.code == "not_published"
    live(repo, "closing")
    repo.set_state(CO, "closing", "pause")
    with pytest.raises(LifecycleError) as again:
        repo.set_state(CO, "closing", "pause")
    assert again.value.code == "not_published"


def test_resuming_something_that_is_not_paused_is_refused(repo):
    live(repo, "closing")
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    for key in ("closing", "discovery", "ghost"):
        with pytest.raises(LifecycleError) as raised:
            repo.set_state(CO, key, "resume")
        assert raised.value.code == "not_paused"


def test_a_paused_playbook_with_a_newer_draft_stays_paused_and_publishing_lifts_the_pause(repo):
    live(repo, label="Apertura")
    repo.set_state(CO, "discovery", "pause")
    repo.save_draft(CO, "discovery", steps("Apertura nueva"), ENTRIES)
    row = repo.list_types(CO)["discovery"]
    assert row["status"] == "paused" and row["paused"] is True and row["has_draft"] is True
    seen = editor(repo)
    assert seen["state"] == "draft" and seen["paused"] is True and seen["has_live"] is True
    rep = editor(repo, draft=False)
    assert rep["state"] == "published" and rep["version"]["steps"][0]["label"] == "Apertura" and rep["paused"] is True
    assert repo.list_types(CO, include_draft=False)["discovery"]["has_draft"] is False
    repo.discard_draft(CO, "discovery")
    assert editor(repo)["paused"] is True and editor(repo)["version"]["steps"][0]["label"] == "Apertura"
    repo.save_draft(CO, "discovery", steps("Apertura nueva"), ENTRIES)
    repo.publish(CO, "discovery")
    assert status(repo) == "published" and editor(repo)["paused"] is False
    assert editor(repo)["version"]["steps"][0]["label"] == "Apertura nueva"
    with pytest.raises(LifecycleError):
        repo.set_state(CO, "discovery", "resume")  # nothing paused any more


def test_publishing_a_paused_playbook_that_has_no_draft_is_refused(repo):
    live(repo)
    repo.set_state(CO, "discovery", "pause")
    with pytest.raises(PublishError) as raised:
        repo.publish(CO, "discovery")
    assert raised.value.code == "not_a_draft"
    assert status(repo) == "paused"


def test_pause_touches_one_type_only(repo):
    live(repo, "discovery")
    live(repo, "closing", label="Cierre")
    repo.set_state(CO, "discovery", "pause")
    assert (status(repo, "discovery"), status(repo, "closing")) == ("paused", "published")
    repo.set_state(CO, "discovery", "resume")
    assert (status(repo, "discovery"), status(repo, "closing")) == ("published", "published")


# --- delete (archive) and restore ------------------------------------------------------------------


def test_delete_removes_the_type_and_restore_brings_a_published_one_back_published(repo):
    published = live(repo, qualification=CRITERIA)
    repo.save_draft(CO, "discovery", steps("Cambio a medias"), ENTRIES)  # a pending draft over the live version
    repo.set_state(CO, "discovery", "archive")
    assert "discovery" not in repo.list_types(CO)
    assert editor(repo) == {"state": "empty", "version": None, "has_live": False, "source": None, "paused": False}
    for action in ("pause", "resume", "archive"):
        with pytest.raises(LifecycleError):
            repo.set_state(CO, "discovery", action)
    with pytest.raises(PublishError):
        repo.publish(CO, "discovery")
    repo.set_state(CO, "discovery", "restore")
    assert status(repo) == "published"
    back = editor(repo)
    assert back["state"] == "published" and back["paused"] is False and back["has_live"] is True
    assert back["version"]["id"] == published and back["version"]["steps"][0]["label"] == "Apertura"  # not the draft


def test_restore_puts_a_paused_playbook_back_paused(repo):
    live(repo)
    repo.set_state(CO, "discovery", "pause")
    repo.set_state(CO, "discovery", "archive")
    repo.set_state(CO, "discovery", "restore")
    assert status(repo) == "paused" and editor(repo)["paused"] is True
    repo.set_state(CO, "discovery", "resume")
    assert status(repo) == "published"


def test_restoring_something_that_is_not_deleted_is_refused(repo):
    live(repo)
    with pytest.raises(LifecycleError) as raised:
        repo.set_state(CO, "discovery", "restore")
    assert raised.value.code == "not_archived"
    repo.set_state(CO, "discovery", "archive")
    repo.set_state(CO, "discovery", "restore")
    with pytest.raises(LifecycleError):
        repo.set_state(CO, "discovery", "restore")  # already back


def test_a_deleted_draft_only_type_comes_back_empty(repo):
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    repo.set_state(CO, "discovery", "archive")
    repo.set_state(CO, "discovery", "restore")
    assert status(repo) == "missing" and editor(repo)["state"] == "empty"


def test_a_type_that_only_lives_as_a_call_type_is_deleted_and_restored(repo):
    repo.add_type(CO, "sales", "Sales")
    assert status(repo, "sales") == "missing"
    repo.set_state(CO, "sales", "archive")
    assert "sales" not in repo.list_types(CO)
    with pytest.raises(LifecycleError) as twice:
        repo.set_state(CO, "sales", "archive")
    assert twice.value.code == "not_found"
    repo.set_state(CO, "sales", "restore")
    assert status(repo, "sales") == "missing"
    with pytest.raises(LifecycleError) as active:
        repo.set_state(CO, "sales", "restore")
    assert active.value.code == "not_archived"


def test_creating_a_deleted_type_again_brings_it_back_empty(repo):
    old = live(repo, label="Viejo")
    repo.set_state(CO, "discovery", "archive")
    repo.add_type(CO, "discovery", "Discovery")
    assert status(repo) == "missing"
    snapshot = editor(repo)
    assert snapshot["state"] == "empty" and snapshot["has_live"] is False and snapshot["paused"] is False
    with pytest.raises(LifecycleError):
        repo.set_state(CO, "discovery", "restore")  # it is not deleted any more
    new = live(repo, label="Nuevo")
    assert new != old and editor(repo)["version"]["steps"][0]["label"] == "Nuevo"


def test_saving_a_draft_over_a_deleted_type_un_archives_it_without_the_old_content(repo):
    old = live(repo, label="Viejo")
    repo.set_state(CO, "discovery", "pause")
    repo.set_state(CO, "discovery", "archive")
    saved = repo.save_draft(CO, "discovery", steps("Nuevo"), [])
    assert saved["id"] != old
    row = repo.list_types(CO)["discovery"]
    assert row["status"] == "draft" and row["paused"] is False and row["step_count"] == 1
    snapshot = editor(repo)
    assert snapshot["state"] == "draft" and snapshot["has_live"] is False and snapshot["paused"] is False
    assert snapshot["version"]["steps"][0]["label"] == "Nuevo"
    assert repo.publish(CO, "discovery") == saved["id"]
    assert status(repo) == "published"  # switched on: the pause of the old one did not come back


def test_creating_a_deleted_call_type_again_reactivates_it(repo):
    repo.add_type(CO, "sales", "Sales")
    repo.set_state(CO, "sales", "archive")
    repo.add_type(CO, "sales", "Sales")
    assert repo.list_types(CO)["sales"]["status"] == "missing"


# --- types, names and rules ------------------------------------------------------------------------


def test_adding_a_type_lists_it_as_missing_and_is_idempotent(repo):
    repo.add_type(CO, "  renewal  ", "Renovación")
    repo.add_type(CO, "renewal", "Otra vez")
    assert sorted(repo.list_types(CO)) == ["renewal"] and status(repo, "renewal") == "missing"
    with pytest.raises(PublishError) as raised:
        repo.publish(CO, "renewal")
    assert raised.value.code == "not_a_draft"  # adding a type publishes nothing


def test_an_empty_type_key_is_refused(repo):
    for key in ("", "   "):
        with pytest.raises(PublishError) as raised:
            repo.add_type(CO, key, "Vacía")
        assert raised.value.code == "empty_type"
    assert repo.list_types(CO) == {}


def test_a_type_is_added_with_its_name_and_rule_in_one_step(repo):
    repo.add_type(CO, "renewal", "Renovación", label="Renovación", applies_to=RULE)
    row = repo.list_types(CO)["renewal"]
    assert row["label"] == "Renovación" and row["applies_to"] == RULE and row["status"] == "missing"


def test_set_meta_sets_only_what_it_is_given(repo):
    repo.set_meta(CO, "closing", label="Cierre")
    assert status(repo, "closing") == "missing"  # it creates the type
    repo.set_meta(CO, "closing", applies_to=RULE)
    row = repo.list_types(CO)["closing"]
    assert row["label"] == "Cierre" and row["applies_to"] == RULE
    repo.set_meta(CO, "closing")  # nothing to set
    repo.set_meta(CO, "closing", label="")  # an empty name clears it
    repo.set_meta(CO, "closing", applies_to=None)
    row = repo.list_types(CO)["closing"]
    assert row["label"] is None and row["applies_to"] is None
    repo.set_meta(CO, "closing", label="Cierre", applies_to=UNSET)
    assert repo.list_types(CO)["closing"]["label"] == "Cierre"


# --- the material a playbook was structured from ------------------------------------------------------


def test_a_source_is_kept_read_back_and_travels_across_publishing(repo):
    source = repo.save_source(CO, "discovery", "audio", "dictado.webm", "Hola, esto es el guion")
    assert source["id"].startswith("source:") and source["kind"] == "audio" and source["name"] == "dictado.webm"
    assert repo.get_source(CO, source["id"]) == source
    assert editor(repo)["state"] == "empty"  # a source is not a version
    v1 = repo.save_draft(CO, "discovery", STEPS, ENTRIES, source_id=source["id"])
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)  # keeps it
    assert editor(repo)["source"] == source
    repo.publish(CO, "discovery")
    assert editor(repo, draft=False)["source"]["id"] == source["id"]
    v2 = repo.save_draft(CO, "discovery", STEPS, ENTRIES)  # the first edit over the published version
    assert v2["id"] != v1["id"] and editor(repo)["source"]["id"] == source["id"]
    other = repo.save_source(CO, "discovery", "text", "n", "t")
    repo.save_draft(CO, "discovery", STEPS, ENTRIES, source_id=other["id"])
    assert editor(repo)["source"]["id"] == other["id"]


def test_a_source_that_is_not_the_companys_or_not_a_source_is_ignored(repo):
    foreign = repo.save_source(OTHER, "discovery", "text", "ajeno", "secreto")
    saved = repo.save_draft(CO, "discovery", STEPS, ENTRIES, source_id=foreign["id"])
    assert editor(repo)["source"] is None
    assert repo.get_source(CO, foreign["id"]) is None and repo.get_source(OTHER, foreign["id"]) == foreign
    for bad in ("source:nope", f"editor:{saved['id']}", "x", "", None):
        repo.save_draft(CO, "discovery", STEPS, ENTRIES, source_id=bad)
        assert editor(repo)["source"] is None
        assert repo.get_source(CO, bad) is None


def test_a_company_source_creates_no_type_but_a_type_source_lists_the_type(repo):
    repo.save_source(CO, None, "pdf", "guion.pdf", "hola")
    assert repo.list_types(CO) == {}
    repo.save_source(CO, "discovery", "pdf", "guion.pdf", "hola")
    assert status(repo) == "missing"


# --- what Vocify knows about the company ------------------------------------------------------------


def test_the_company_knowledge_is_saved_read_back_and_normalized(repo):
    assert repo.get_knowledge(CO) is None
    saved = repo.save_knowledge(CO, {"icp": "  pymes  ", "junk": 1, "differentiators": ["a", "A", "b"]})
    assert saved["data"]["icp"] == "pymes" and saved["data"]["differentiators"] == ["a", "b"] and "junk" not in saved["data"]
    assert saved["updated_at"] and saved["source_id"] is None
    assert repo.get_knowledge(CO)["data"] == saved["data"]
    assert repo.get_knowledge(OTHER) is None
    later = repo.save_knowledge(CO, {"icp": "grandes"})
    assert later["data"]["icp"] == "grandes" and is_newer(later["updated_at"], saved["updated_at"])


def test_a_stale_knowledge_base_is_refused(repo):
    with pytest.raises(StaleKnowledgeError):  # a base with nothing saved is stale, as it always was
        repo.save_knowledge(CO, {"icp": "x"}, base_updated_at="2026-01-01T00:00:00Z")
    one = repo.save_knowledge(CO, {"icp": "uno"})
    two = repo.save_knowledge(CO, {"icp": "dos"}, base_updated_at=one["updated_at"])
    with pytest.raises(StaleKnowledgeError):
        repo.save_knowledge(CO, {"icp": "tres"}, base_updated_at=one["updated_at"])
    with pytest.raises(StaleKnowledgeError):
        repo.save_knowledge(CO, {"icp": "tres"}, base_updated_at="not a date")
    assert repo.get_knowledge(CO)["data"]["icp"] == "dos"
    ok = repo.save_knowledge(CO, {"icp": "cuatro"}, base_updated_at=js_iso(two["updated_at"]))  # a JS Date base
    assert ok["data"]["icp"] == "cuatro"


# --- one input for the whole company ------------------------------------------------------------------


def _item(key, label="Apertura", qualification=None, **extra):
    return {"key": key, "steps": steps(label), "entries": ENTRIES, "qualification": qualification, **extra}


def test_the_intake_saves_every_type_and_the_company_knowledge(repo):
    source = repo.save_source(CO, None, "text", "doc", "texto")
    result = repo.save_intake(
        CO, [_item("discovery", qualification=CRITERIA), _item("closing", "Cierre")], {"icp": "pymes"}, source["id"],
    )
    assert [t["sales_motion_key"] for t in result["types"]] == ["discovery", "closing"]
    assert result["knowledge"]["data"]["icp"] == "pymes" and result["knowledge"]["source_id"] == source["id"]
    assert repo.get_knowledge(CO)["data"]["icp"] == "pymes"
    for entry in result["types"]:
        snapshot = editor(repo, entry["sales_motion_key"])
        assert snapshot["state"] == "draft" and snapshot["version"]["id"] == entry["version_id"]
        assert snapshot["source"]["id"] == source["id"]
    assert editor(repo)["version"]["qualification"] == CRITERIA
    assert editor(repo, "closing")["version"]["qualification"] == []
    assert status(repo, "discovery") == "draft" and status(repo, "closing") == "draft"


def test_the_intake_overwrites_a_pending_draft_and_leaves_a_published_version_live(repo):
    published = live(repo, label="Vigente", qualification=CRITERIA)
    first = repo.save_intake(CO, [_item("discovery", "Del documento")], None, None)
    assert status(repo) == "published"
    assert editor(repo, draft=False)["version"]["id"] == published
    draft = editor(repo)["version"]
    assert draft["id"] == first["types"][0]["version_id"] != published and draft["steps"][0]["label"] == "Del documento"
    assert draft["qualification"] == CRITERIA  # a document without criteria (None) keeps what was there
    second = repo.save_intake(CO, [_item("discovery", "Otro documento", qualification=[])], None, None)
    assert second["types"][0]["version_id"] == draft["id"]  # the pending draft is overwritten in place
    assert editor(repo)["version"]["steps"][0]["label"] == "Otro documento"
    assert editor(repo)["version"]["qualification"] == []


def test_the_intake_creates_a_type_the_company_does_not_have_and_leaves_an_existing_one_alone(repo):
    repo.add_type(CO, "closing", "Mi cierre", label="Mi cierre")
    ensure = {"name": "Llamada", "label": "Catálogo", "applies_to": RULE}
    repo.save_intake(CO, [_item("discovery", ensure=ensure), _item("closing", ensure=ensure)], None, None)
    listed = repo.list_types(CO)
    assert listed["discovery"]["label"] == "Catálogo" and listed["discovery"]["applies_to"] == RULE
    assert listed["closing"]["label"] == "Mi cierre" and listed["closing"]["applies_to"] is None  # untouched
    assert listed["discovery"]["status"] == "draft" and listed["closing"]["status"] == "draft"


def test_the_intake_brings_a_deleted_catalog_type_back_empty(repo):
    live(repo, label="Viejo")
    repo.set_state(CO, "discovery", "archive")
    repo.save_intake(CO, [_item("discovery", "Nuevo", ensure={"name": "Discovery"})], None, None)
    snapshot = editor(repo)
    assert snapshot["state"] == "draft" and snapshot["has_live"] is False and snapshot["version"]["steps"][0]["label"] == "Nuevo"


def test_the_intake_can_save_only_the_knowledge(repo):
    result = repo.save_intake(CO, [], {"icp": "pymes"}, None)
    assert result["types"] == [] and result["knowledge"]["data"]["icp"] == "pymes"
    assert repo.list_types(CO) == {}


def test_a_failing_type_rolls_back_the_whole_intake(repo):
    repo.save_knowledge(CO, {"icp": "antes"})
    good = _item("discovery", ensure={"name": "Discovery", "label": "Cold call", "applies_to": RULE})
    bad = {"key": "closing", "steps": None, "entries": ENTRIES, "qualification": None}
    with pytest.raises(PlaybookRepositoryError) as raised:
        repo.save_intake(CO, [good, bad], {"icp": "despues", "notes": "n"}, None)
    assert raised.value.code == "invalid_type_item"
    assert repo.list_types(CO) == {}  # the first type, and the type created for it, are gone
    assert editor(repo)["state"] == "empty"
    assert repo.get_knowledge(CO)["data"]["icp"] == "antes"  # nor was the knowledge written
    for broken in ({"steps": [], "entries": []}, {"key": " ", "steps": [], "entries": []}, {"key": "x", "steps": [], "entries": "no"}):
        with pytest.raises(PlaybookRepositoryError):
            repo.save_intake(CO, [good, broken], None, None)
        assert repo.list_types(CO) == {}


# --- SQL only: what only a database can show ---------------------------------------------------------------


@pytest.fixture
def sql(pg):
    return SqlPlaybookRepository(pg), pg


def _count(pg, table, where="true"):
    return int(pg.sql(f"SELECT count(*) FROM {table} WHERE {where}"))


def test_sql_ten_saves_are_one_version_row_and_one_editor_import(sql):
    repo, pg = sql
    versions = [repo.save_draft(CO, "discovery", steps(criterion=f"Se presenta {i}"), ENTRIES) for i in range(10)]
    assert _count(pg, "playbook_versions") == 1
    assert _count(pg, "playbook_imports", "kind = 'editor'") == 1
    assert pg.sql("SELECT id FROM playbook_imports WHERE kind = 'editor'") == f"editor:{versions[0]['id']}"
    assert "Se presenta 9" in pg.sql("SELECT draft->>'text' FROM playbook_imports WHERE kind = 'editor'")
    assert pg.sql("SELECT draft->'contradictions' FROM playbook_imports WHERE kind = 'editor'") == "[]"


def test_sql_publish_then_edit_keeps_both_versions_and_their_imports(sql):
    repo, pg = sql
    first = repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    repo.publish(CO, "discovery")
    edited = repo.save_draft(CO, "discovery", steps("Otra"), [])
    assert _count(pg, "playbook_versions") == 2
    assert pg.sql(f"SELECT status FROM playbook_versions WHERE id = '{first['id']}'") == "published"
    assert _count(pg, "playbook_imports", "kind = 'editor'") == 2
    repo.discard_draft(CO, "discovery")
    assert [r for r in pg.sql("SELECT id FROM playbook_versions").split()] == [first["id"]]
    assert pg.sql("SELECT id FROM playbook_imports WHERE kind = 'editor'") == f"editor:{first['id']}"
    assert f"editor:{edited['id']}" not in pg.sql("SELECT id FROM playbook_imports")


def test_sql_an_old_draft_behind_the_published_version_is_not_pending_and_is_never_published(sql):
    repo, pg = sql
    playbook = pg.sql(f"INSERT INTO playbooks (company_id, sales_motion_key) VALUES ('{CO}', 'discovery') RETURNING id")
    pg.sql(f"INSERT INTO playbook_versions (playbook_id, status) VALUES ('{playbook}', 'draft')")  # left by the one-row-per-save era
    saved = repo.save_draft(CO, "discovery", STEPS, ENTRIES)  # updates that only draft
    assert repo.publish(CO, "discovery") == saved["id"]
    stale = pg.sql(
        f"INSERT INTO playbook_versions (playbook_id, status, created_at) VALUES ('{playbook}', 'draft', '2020-01-01') RETURNING id"
    )
    snapshot = editor(repo)
    assert snapshot["state"] == "published" and snapshot["version"]["id"] == saved["id"]
    with pytest.raises(PublishError):
        repo.publish(CO, "discovery")  # an old leftover draft is not something to publish over the live one
    fresh = repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    assert fresh["id"] not in (saved["id"], stale)
    assert repo.discard_draft(CO, "discovery") is True
    assert set(pg.sql("SELECT id FROM playbook_versions").split()) == {saved["id"], stale}


def test_sql_discarding_removes_every_draft_row_when_nothing_is_published(sql):
    repo, pg = sql
    playbook = pg.sql(f"INSERT INTO playbooks (company_id, sales_motion_key) VALUES ('{CO}', 'discovery') RETURNING id")
    for _ in range(3):
        pg.sql(f"INSERT INTO playbook_versions (playbook_id, status) VALUES ('{playbook}', 'draft')")
    repo.save_draft(CO, "discovery", STEPS, ENTRIES)
    assert repo.discard_draft(CO, "discovery") is True
    assert _count(pg, "playbook_versions") == 0 and _count(pg, "playbook_imports") == 0


def test_sql_delete_keeps_the_published_version_and_drops_drafts_and_their_imports(sql):
    repo, pg = sql
    published = live(repo)
    repo.save_draft(CO, "discovery", steps("Cambio"), ENTRIES)
    repo.save_source(CO, "discovery", "text", "n", "t")
    repo.set_state(CO, "discovery", "archive")
    assert pg.sql("SELECT string_agg(id::text, ',') FROM playbook_versions") == published
    assert _count(pg, "playbook_imports", "kind = 'editor'") == 1  # the published version's own
    assert _count(pg, "playbook_imports", "kind = 'text'") == 1  # source documents stay
    row = pg.sql("SELECT (active_version_id IS NOT NULL)::text || ',' || state || ',' || (archived_at IS NOT NULL)::text FROM playbooks")
    assert row == "true,active,true"  # deleting never touches the version or the switch
    repo.set_state(CO, "discovery", "restore")
    assert pg.sql("SELECT active_version_id::text FROM playbooks") == published


def test_sql_pausing_never_moves_the_published_version(sql):
    repo, pg = sql
    published = live(repo)
    repo.set_state(CO, "discovery", "pause")
    assert pg.sql("SELECT active_version_id::text || ',' || state FROM playbooks") == f"{published},paused"
    assert pg.sql("SELECT count(*) FROM playbooks_live") == "0"
    repo.set_state(CO, "discovery", "resume")
    assert pg.sql("SELECT count(*) FROM playbooks_live") == "1"


def test_sql_deleting_a_call_type_turns_its_interaction_type_off_and_restoring_turns_it_on(sql):
    repo, pg = sql
    live(repo)
    repo.add_type(CO, "discovery", "Discovery")
    repo.set_state(CO, "discovery", "archive")
    assert pg.sql("SELECT active::text FROM interaction_types") == "false"
    repo.set_state(CO, "discovery", "restore")
    assert pg.sql("SELECT active::text FROM interaction_types") == "true"


def test_sql_two_saves_with_the_same_base_cannot_both_win(sql):
    """The conflict check is part of the UPDATE (and the playbook row serializes the saves): the second save waits for
    the first one's transaction and then finds that the base is not the draft's updated_at any more."""
    repo, pg = sql
    base = repo.save_draft(CO, "discovery", STEPS, ENTRIES)["updated_at"]
    outcomes: dict[str, str] = {}

    def slow_first():
        done = pg_support.psql(
            pg.dsn,
            "BEGIN; SELECT playbook_save_draft("
            f"'{CO}', 'discovery', '[{{\"step_id\":\"a\",\"label\":\"Primero\",\"criterion\":\"x\"}}]'::jsonb, '[]'::jsonb, NULL, NULL, '{base}'); "
            "SELECT pg_sleep(0.6); COMMIT;",
        )
        outcomes["first"] = "ok" if done.returncode == 0 else done.stderr

    def second():
        time.sleep(0.25)  # after the first one holds the playbook row
        try:
            repo.save_draft(CO, "discovery", steps("Segundo"), ENTRIES, base_updated_at=base)
            outcomes["second"] = "ok"
        except StaleDraftError:
            outcomes["second"] = "stale"

    threads = [threading.Thread(target=slow_first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes == {"first": "ok", "second": "stale"}
    assert editor(repo)["version"]["steps"][0]["label"] == "Primero"
    assert _count(pg, "playbook_versions") == 1


def test_sql_two_knowledge_saves_with_the_same_base_cannot_both_win(sql):
    repo, pg = sql
    base = repo.save_knowledge(CO, {"icp": "uno"})["updated_at"]
    outcomes: dict[str, str] = {}

    def slow_first():
        done = pg_support.psql(
            pg.dsn,
            f"BEGIN; SELECT company_knowledge_save('{CO}', '{{\"icp\":\"primero\"}}'::jsonb, NULL, '{base}'); "
            "SELECT pg_sleep(0.6); COMMIT;",
        )
        outcomes["first"] = "ok" if done.returncode == 0 else done.stderr

    def second():
        time.sleep(0.25)
        try:
            repo.save_knowledge(CO, {"icp": "segundo"}, base_updated_at=base)
            outcomes["second"] = "ok"
        except StaleKnowledgeError:
            outcomes["second"] = "stale"

    threads = [threading.Thread(target=slow_first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes == {"first": "ok", "second": "stale"}
    assert repo.get_knowledge(CO)["data"]["icp"] == "primero"


def test_sql_a_failing_intake_leaves_no_rows_behind(sql):
    repo, pg = sql
    good = _item("discovery", ensure={"name": "Discovery", "label": "Cold call"})
    bad = {"key": "closing", "steps": None, "entries": []}
    with pytest.raises(PlaybookRepositoryError):
        repo.save_intake(CO, [good, bad], {"icp": "x"}, None)
    for table in ("playbooks", "playbook_versions", "playbook_imports", "interaction_types", "company_sales_knowledge"):
        assert _count(pg, table) == 0, table


def test_sql_the_sql_repository_only_calls_functions(sql):
    repo, pg = sql
    live(repo)
    repo.set_state(CO, "discovery", "pause")
    repo.list_types(CO)
    repo.save_intake(CO, [_item("closing")], {"icp": "x"}, None)
    names = {name for name, _ in pg.calls}
    assert names <= {
        "playbook_save_draft", "publish_playbook_motion", "playbook_set_state", "playbook_overview", "playbook_editor",
        "playbook_intake_save", "playbook_discard_draft", "playbook_add_type", "playbook_set_meta", "playbook_source_save",
        "playbook_source_get", "playbook_import_get", "save_playbook_draft", "company_knowledge_get", "company_knowledge_save",
    }


def test_sql_the_fake_answers_like_the_database_for_a_long_journey(sql):
    """One journey through everything, run on both, compared step by step: what the API can observe is the same."""
    real, pg = sql
    fake = InMemoryPlaybookRepository()

    def observe(repository) -> dict:
        types = repository.list_types(CO)
        return {
            "types": {k: {f: v for f, v in row.items()} for k, row in types.items()},
            "editors": {k: {**editor(repository, k), "version": _shape(editor(repository, k)["version"])} for k in types},
        }

    def _shape(version):
        return None if version is None else {k: v for k, v in version.items() if k not in ("id", "created_at", "updated_at")}

    journey = [
        lambda r: r.save_draft(CO, "discovery", STEPS, ENTRIES, qualification=CRITERIA),
        lambda r: r.add_type(CO, "renewal", "Renovación", label="Renovación", applies_to=RULE),
        lambda r: r.publish(CO, "discovery"),
        lambda r: r.save_draft(CO, "discovery", steps("Otra"), []),
        lambda r: r.set_state(CO, "discovery", "pause"),
        lambda r: r.discard_draft(CO, "discovery"),
        lambda r: r.set_state(CO, "discovery", "resume"),
        lambda r: r.set_state(CO, "discovery", "archive"),
        lambda r: r.set_state(CO, "renewal", "archive"),
        lambda r: r.set_state(CO, "renewal", "restore"),
        lambda r: r.save_draft(CO, "discovery", steps("Nueva"), ENTRIES),
        lambda r: r.save_intake(CO, [_item("closing", "Cierre")], None, None),
    ]
    for step in journey:
        step(real)
        step(fake)
        assert observe(real) == observe(fake)
    assert copy.deepcopy(observe(real))["types"]["discovery"]["status"] == "draft"
