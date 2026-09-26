"""E4 cold-call brief: who and why for contacts without memos."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-brief-cold-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-brief-cold-32b")

import pytest

from app.services.briefs import cold_call
from app.services.briefs.cold_call import hubspot_source_label, prepare_cold_brief_v2

TZ = "Europe/Madrid"
NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
UNCALLED = {"reason": "no_calls_logged", "source_ref": "hubspot:42:", "observed_at": "2026-09-26T08:00:00Z"}


def _brief(**kwargs):
    base = {"coverage": "complete", "profile": None, "tz_name": TZ, "crm_task": None, "hoy_priority": None}
    base.update(kwargs)
    return prepare_cold_brief_v2(**base)


def test_who_line_with_role_company_source_and_created_date():
    profile = {
        "jobtitle": "Directora comercial",
        "company_name": "Acme",
        "source_label": "búsqueda orgánica",
        "created_at": "2026-09-03T08:00:00+02:00",
    }
    brief = _brief(profile=profile)
    assert brief["lines"][0] == {
        "type": "who",
        "text": "Directora comercial en Acme · búsqueda orgánica, 3 sep",
        "source_ref": None,
        "observed_at": "2026-09-03T08:00:00+02:00",
    }


def test_who_line_omits_missing_parts():
    assert _brief(profile={"jobtitle": "AE", "company_name": "Acme"})["lines"][0]["text"] == "AE en Acme"

    empty = _brief(profile={})
    assert empty["status"] == "no_conversation"
    assert empty["text"] == "Sin conversación todavía."


def test_why_prefers_crm_task_over_hoy_priority():
    brief = _brief(
        profile={"jobtitle": "AE", "company_name": "Acme"},
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1", "observed_at": None},
        hoy_priority=UNCALLED,
    )
    assert brief["lines"][1] == {"type": "why", "text": "Llamar el jueves", "source_ref": "task-1", "observed_at": None}


def test_why_carries_the_hoy_reason_key_and_created_day_not_a_sentence():
    brief = _brief(
        profile={"jobtitle": "AE", "company_name": "Acme", "created_at": "2026-09-03T08:00:00+02:00"},
        hoy_priority=UNCALLED,
    )
    assert brief["lines"][1] == {
        "type": "why",
        "text": None,
        "reason": "no_calls_logged",
        "since": "3 sep",
        "source_ref": "hubspot:42:",
        "observed_at": "2026-09-26T08:00:00Z",
    }


def test_uncalled_without_created_date_has_no_since():
    brief = _brief(profile={"jobtitle": "AE"}, hoy_priority=UNCALLED)
    assert brief["lines"][1]["reason"] == "no_calls_logged"
    assert brief["lines"][1]["since"] is None


def test_pain_reason_never_carries_a_since_date():
    brief = _brief(
        profile={"created_at": "2026-09-03T08:00:00+02:00"},
        hoy_priority={**UNCALLED, "reason": "pain_agree_next_step"},
    )
    why = brief["lines"][1]
    assert (why["reason"], why["since"]) == ("pain_agree_next_step", None)


@pytest.mark.parametrize("reason", ["followup_pending", "scheduled_no_early_call", "history_partial", ""])
def test_reasons_without_a_hoy_card_label_give_no_why_line(reason):
    brief = _brief(profile={"jobtitle": "AE"}, hoy_priority={**UNCALLED, "reason": reason})
    assert [line["type"] for line in brief["lines"]] == ["who"]


def test_hoy_reason_alone_is_a_brief_not_no_conversation():
    brief = _brief(profile={}, hoy_priority=UNCALLED)
    assert brief["status"] == "ready"
    assert [line["type"] for line in brief["lines"]] == ["why"]


def test_there_is_no_opening_line_until_the_playbook_models_one():
    assert not hasattr(cold_call, "open_line")
    brief = _brief(profile={"jobtitle": "AE"}, hoy_priority=UNCALLED)
    assert "open" not in {line["type"] for line in brief["lines"]}


def test_partial_read_keeps_verified_lines_and_notice():
    brief = _brief(coverage="partial", profile={"jobtitle": "AE", "company_name": "Acme"})
    assert brief["status"] == "partial"
    assert brief["notice"] == "No se pudo cargar todo."
    assert brief["lines"]


@pytest.mark.parametrize(
    ("value", "label"),
    [
        ("ORGANIC_SEARCH", "búsqueda orgánica"),
        ("PAID_SEARCH", "búsqueda de pago"),
        ("EMAIL_MARKETING", "email marketing"),
        ("SOCIAL_MEDIA", "redes sociales"),
        ("REFERRALS", "referido"),
        ("OTHER_CAMPAIGNS", "otra campaña"),
        ("DIRECT_TRAFFIC", "tráfico directo"),
        ("OFFLINE", "fuente offline"),
        ("PAID_SOCIAL", "redes de pago"),
    ],
)
def test_hubspot_analytics_source_documented_values(value, label):
    assert hubspot_source_label(value) == label


@pytest.mark.parametrize("value", ["WEBFORM", "AI_REFERRALS", "something", "", None])
def test_unknown_hubspot_source_is_omitted(value):
    assert hubspot_source_label(value) is None


def test_contacts_with_memos_still_use_e3_brief():
    from app.services.briefs.v2 import prepare_brief_v2 as v2
    from app.services.intelligence.extract import PROMPT_VERSION
    from app.services.intelligence.worker import revision_for_memo

    memo = {
        "id": "memo-1",
        "created_at": "2026-09-11T10:00:00+02:00",
        "capture_started_at": "2026-09-11T10:00:00+02:00",
        "hubspot_contact_id": "42",
        "extraction": {
            "summary": "Hablaron del almacén.",
            "intelligence": {
                "version": 1,
                "pain_confirmed": False,
                "objections": [],
                "commitments": [],
                "competitor_mentions": [],
                "playbook_observations": [],
                "evidence": [],
                "prompt_version": PROMPT_VERSION,
            },
        },
    }
    intel = memo["extraction"]["intelligence"]
    intel["input_revision"] = revision_for_memo(memo)
    brief = v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["lines"][0]["type"] == "hook"
    assert "who" not in {line["type"] for line in brief["lines"]}
