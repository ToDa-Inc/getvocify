"""The Head of Sales' weekly report can carry the playbook answers that keep failing, with a link to the screen that fixes
them. It is optional and isolated: with the flags off, no store or no failing answer the report is exactly what it was."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import feature_flags
from app.services.playbooks.assistant_store import AssistantUnavailable, InMemoryAssistantStore, set_assistant_store
from app.services.playbooks.repository import InMemoryPlaybookRepository, set_playbook_repository
from app.services.reporting.digest_email import render
from app.services.reporting.periodic import ensure_team_weekly_report
from app.services.reporting.playbook_block import playbook_improvement_block, playbook_improvement_for
from app.services.reporting.presentation import email_html_for_snapshot
from app.services.reporting.weekly import team_snapshot
from tests.reporting.test_weekly_generation import (  # noqa: F401 (fresh_flags is the autouse fixture)
    ADMIN,
    COMPANY,
    FRIDAY_1805,
    MADRID,
    TEAM_INPUTS,
    TEAM_MEMBERS,
    _db,
    _flags,
    _load,
    _reports,
    fresh_flags,
)

NOW = FRIDAY_1805
LINK = "/dashboard/playbook?view=improve"
BOTH = {"PLAYBOOK_ASSISTANT_ENABLED": True, "PLAYBOOK_SUCCESS_RATE_ENABLED": True}


@pytest.fixture(autouse=True)
def _stores():
    yield
    set_assistant_store(None)
    set_playbook_repository(None)


def outcomes(store, answer, failing, *, working=0, motion="discovery"):
    """`failing` cards nobody said and `working` that were said and settled it, for one approved answer."""
    for i in range(failing + working):
        store.upsert_outcome(COMPANY, {
            "event_id": f"{answer}-{motion}-{i}", "observed_at": (NOW - timedelta(days=2)).isoformat(), "sales_motion_key": motion,
            "source_id": answer, "used": "not_used" if i < failing else "used", "resolved": "unknown" if i < failing else "resolved",
            "resolved_by": "extraction", "client_text": "x", "suggestion_text": "y",
        })


def six_failing_answers():
    store = InMemoryAssistantStore()
    for answer, failing, working in (
        ("objection:price", 6, 1), ("objection:timing", 5, 0), ("objection:authority", 4, 0),
        ("objection:competitor", 3, 1), ("objection:status_quo", 3, 0), ("objection:trust", 3, 0),
    ):
        outcomes(store, answer, failing, working=working)
    return store


def test_six_failing_answers_give_the_five_that_failed_most_with_a_link_to_fix_them():
    block = playbook_improvement_block(six_failing_answers(), COMPANY, now=NOW)
    assert [item["label"] for item in block["items"]] == ["Precio", "Plazo", "Autoridad", "Competidor", "Statu quo"]
    assert [(i["failing"], i["total"]) for i in block["items"]] == [(6, 7), (5, 5), (4, 4), (3, 4), (3, 3)]
    assert block["link"] == LINK


def test_without_failing_answers_there_is_no_block():
    store = InMemoryAssistantStore()
    outcomes(store, "objection:price", 2)  # two failing cases are not enough
    outcomes(store, "objection:timing", 0, working=5)
    assert playbook_improvement_block(store, COMPANY, now=NOW) is None
    assert playbook_improvement_block(InMemoryAssistantStore(), COMPANY, now=NOW) is None


def test_the_same_answer_in_two_call_types_says_which_one_each_is():
    store = InMemoryAssistantStore()
    outcomes(store, "objection:price", 3, motion="discovery")
    outcomes(store, "objection:price", 3, motion="closing")
    labels = [item["label"] for item in playbook_improvement_block(store, COMPANY, now=NOW)["items"]]
    assert len(labels) == 2 and all(label.startswith("Precio · ") for label in labels) and labels[0] != labels[1]


def test_a_teams_own_objection_is_named_as_the_team_named_it():
    repository = InMemoryPlaybookRepository()
    repository.save_draft(COMPANY, "discovery", [{"step_id": "a", "label": "A", "criterion": "x"}], [
        {"category": "custom", "label": "Cancelar el servicio", "guidance": "Cuando quieran.", "entry_id": "objection:custom:cancelar-el-servicio", "source_ref": "editor"},
    ])
    store = InMemoryAssistantStore()
    outcomes(store, "objection:custom:cancelar-el-servicio", 3)
    [item] = playbook_improvement_block(store, COMPANY, repository=repository, now=NOW)["items"]
    assert item["label"] == "Cancelar el servicio"
    [bare] = playbook_improvement_block(store, COMPANY, now=NOW)["items"]
    assert bare["label"] == "Cancelar el servicio".capitalize() and bare["failing"] == 3  # from the id when no playbook is at hand


# --- when the report gets it -------------------------------------------------------------------------------


def test_the_block_needs_both_flags_and_a_store_that_exists():
    store = six_failing_answers()
    set_assistant_store(store)
    for flags in ({}, {"PLAYBOOK_ASSISTANT_ENABLED": True}, {"PLAYBOOK_SUCCESS_RATE_ENABLED": True}):
        feature_flags.clear_cache()  # the overrides of a company are cached: each database is a different set of them
        assert playbook_improvement_for(_db(flags=_flags(**flags)), COMPANY, now=NOW) is None
    feature_flags.clear_cache()
    assert playbook_improvement_for(_db(flags=_flags(**BOTH)), COMPANY, now=NOW)["items"][0]["label"] == "Precio"

    class Missing(InMemoryAssistantStore):
        def list_outcomes(self, company_id, *, since):
            raise AssistantUnavailable()

    set_assistant_store(Missing())
    feature_flags.clear_cache()
    assert playbook_improvement_for(_db(flags=_flags(**BOTH)), COMPANY, now=NOW) is None


def snapshot_args():
    return dict(
        team_body={"attempts": 3, "connected": 2, "meetings": 1}, series=[], period_start=NOW - timedelta(days=5), period_end=NOW,
        timezone=MADRID, generated_at=NOW,
    )


def test_the_snapshot_only_gets_the_key_when_there_is_a_block():
    plain = team_snapshot(**snapshot_args())
    assert "playbook_improvement" not in plain
    assert team_snapshot(**snapshot_args(), playbook_improvement=None) == plain
    block = {"items": [{"label": "Precio", "failing": 3, "total": 4}], "link": LINK}
    assert team_snapshot(**snapshot_args(), playbook_improvement=block) == {**plain, "playbook_improvement": block}


def team_report(flags):
    feature_flags.clear_cache()
    db = _db(members=TEAM_MEMBERS, flags=_flags(REPORTING_TEAM_ENABLED=True, **flags))
    report_id = ensure_team_weekly_report(db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=NOW, load_inputs=_load(TEAM_INPUTS))
    return _reports(db, id=report_id)[0]["snapshot"]


def test_the_weekly_team_report_carries_it_and_is_otherwise_the_same():
    set_assistant_store(six_failing_answers())
    without = team_report({})
    with_block = team_report(BOTH)
    assert "playbook_improvement" not in without
    assert len(with_block["playbook_improvement"]["items"]) == 5
    assert {k: v for k, v in with_block.items() if k != "playbook_improvement"} == without


# --- how it reads --------------------------------------------------------------------------------------------


def test_the_email_lists_the_answers_and_links_to_the_screen_that_fixes_them():
    block = playbook_improvement_block(six_failing_answers(), COMPANY, now=NOW)
    snapshot = {**team_snapshot(**snapshot_args(), playbook_improvement=block), "digest": {"activity": {"calls": 3, "conversations": 2}}}
    html = render(snapshot, report_href="https://app.getvocify.com/dashboard/reports/r1", title="Tu equipo esta semana")
    assert "Respuestas que conviene afinar" in html and "Precio" in html and "6 de 7" in html
    assert f"https://app.getvocify.com{LINK}" in html
    old = email_html_for_snapshot(team_snapshot(**snapshot_args(), playbook_improvement=block), report_id="r1")
    assert "Respuestas que conviene afinar" in old and f"https://app.getvocify.com{LINK}" in old


def test_without_the_block_the_emails_have_no_such_section():
    snapshot = {**team_snapshot(**snapshot_args()), "digest": {"activity": {"calls": 3, "conversations": 2}}}
    assert "Respuestas que conviene afinar" not in render(snapshot, report_href="https://app.getvocify.com/dashboard/reports/r1", title="t")
    assert "Respuestas que conviene afinar" not in email_html_for_snapshot(team_snapshot(**snapshot_args()), report_id="r1")
