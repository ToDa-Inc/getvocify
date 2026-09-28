"""T6: prepare_meeting_brief - deterministic, no model call."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.briefs.meeting import company_summary, prepare_meeting_brief

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


def test_company_summary_is_none_when_the_crm_has_nothing():
    assert company_summary(None) is None
    assert company_summary({"company_name": "", "industry": None}) is None


def test_company_summary_keeps_only_what_the_crm_has():
    out = company_summary({"company_name": "Acme", "industry": "SaaS"})
    assert out == {"name": "Acme", "sector": "SaaS", "size": None}


def test_interactions_include_the_handoff_sdr_and_the_ae_newest_first():
    memos = [
        {
            "id": "m1", "user_id": "sdr-1", "created_at": "2026-09-20T10:00:00Z",
            "extraction": {"summary": "Primera llamada, interesado", "intelligence": {}},
        },
        {
            "id": "m2", "user_id": "ae-1", "created_at": "2026-09-25T10:00:00Z",
            "extraction": {"intelligence": {"pain_quote": "Nos preocupa el precio"}},
        },
    ]
    brief = prepare_meeting_brief(
        memos=memos,
        author_names={"sdr-1": "Marina (SDR)", "ae-1": "Diego (AE)"},
        now=NOW,
    )
    assert [line["author"] for line in brief["interactions"]] == ["Diego (AE)", "Marina (SDR)"]
    assert brief["interactions"][0]["text"] == "Nos preocupa el precio"


def test_open_items_collect_open_objections_pending_commitments_and_missing_steps():
    memos = [{
        "id": "m1", "user_id": "ae-1", "created_at": "2026-09-20T10:00:00Z",
        "extraction": {"intelligence": {
            "objections": [{"quote": "Es caro", "resolution": "open"}],
            "commitments": [{"text": "Enviar propuesta", "due_at": "2026-09-21T10:00:00Z"}],
            "playbook_observations": [{"step_id": "s1", "status": "missed"}],
        }},
    }]
    steps = [{"step_id": "s1", "label": "Presentar precio"}, {"step_id": "s2", "label": "Cerrar"}]
    brief = prepare_meeting_brief(memos=memos, playbook_steps=steps, now=NOW)
    items = brief["open_items"]
    assert items["objections"] == [{"text": "Es caro", "source_ref": None}]
    assert items["commitments"][0]["text"] == "Enviar propuesta"
    assert items["missing_playbook_steps"] == ["presentar precio"]


def test_a_fulfilled_commitment_and_a_future_one_are_not_pending():
    memos = [{
        "id": "m1", "user_id": "ae-1", "created_at": "2026-09-20T10:00:00Z",
        "extraction": {"intelligence": {"commitments": [
            {"text": "Hecho", "status": "done"},
            {"text": "Mañana no cuenta", "due_at": "2026-09-30T10:00:00Z"},
        ]}},
    }]
    brief = prepare_meeting_brief(memos=memos, now=NOW)
    assert brief["open_items"]["commitments"] == []


def test_no_memos_at_all_gives_empty_but_well_formed_sections():
    brief = prepare_meeting_brief(now=NOW)
    assert brief == {
        "company": None,
        "interactions": [],
        "open_items": {"objections": [], "commitments": [], "missing_playbook_steps": []},
    }
