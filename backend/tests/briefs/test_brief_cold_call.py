"""E4 cold-call brief: who, why and open for contacts without memos."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-brief-cold-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-brief-cold-32b")

from app.services.briefs.cold_call import prepare_cold_brief_v2
from app.services.briefs.v2 import prepare_brief_v2
from app.services.hoy.reasons import priority_reason_text

TZ = "Europe/Madrid"
NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)

OPENING_STEPS = [
    {
        "step_id": "opening",
        "label": "Apertura",
        "criterion": "Saluda y pide permiso",
        "reference_phrase": "Hola, soy Toni de Vocify. ¿Te pillo en mal momento?",
    },
    {"step_id": "pitch", "label": "Pitch", "criterion": "Explicó el producto"},
]


def test_who_line_with_role_company_source_and_created_date():
    profile = {
        "jobtitle": "Directora comercial",
        "company_name": "Acme",
        "source_label": "lead de formulario web",
        "created_at": "2026-09-03T08:00:00+02:00",
    }
    brief = prepare_cold_brief_v2(
        coverage="complete",
        profile=profile,
        tz_name=TZ,
        crm_task=None,
        hoy_why=None,
        playbook_steps=[],
        sales_motion_key=None,
    )
    assert brief["lines"][0] == {
        "type": "who",
        "text": "Directora comercial en Acme · lead de formulario web, 3 sep",
        "source_ref": None,
        "observed_at": "2026-09-03T08:00:00+02:00",
    }


def test_who_line_omits_missing_parts():
    brief = prepare_cold_brief_v2(
        coverage="complete",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task=None,
        hoy_why=None,
        playbook_steps=[],
        sales_motion_key=None,
    )
    assert brief["lines"][0]["text"] == "AE en Acme"

    empty = prepare_cold_brief_v2(
        coverage="complete",
        profile={},
        tz_name=TZ,
        crm_task=None,
        hoy_why=None,
        playbook_steps=[],
        sales_motion_key=None,
    )
    assert empty["status"] == "no_conversation"
    assert empty["text"] == "Sin conversación todavía."


def test_why_prefers_crm_task_over_hoy_priority():
    brief = prepare_cold_brief_v2(
        coverage="complete",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1", "observed_at": None},
        hoy_why={"text": "Nuevo, sin llamar desde el 3 sep", "source_ref": "prio-1", "observed_at": None},
        playbook_steps=[],
        sales_motion_key=None,
    )
    assert brief["lines"][1]["type"] == "why"
    assert brief["lines"][1]["text"] == "Llamar el jueves"


def test_why_uses_hoy_priority_when_no_crm_task():
    brief = prepare_cold_brief_v2(
        coverage="complete",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task=None,
        hoy_why={"text": "Nuevo, sin llamar desde el 3 sep", "source_ref": "prio-1", "observed_at": None},
        playbook_steps=[],
        sales_motion_key=None,
    )
    assert brief["lines"][1]["text"] == "Nuevo, sin llamar desde el 3 sep"


def test_open_line_uses_playbook_opening_reference_phrase():
    brief = prepare_cold_brief_v2(
        coverage="complete",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task=None,
        hoy_why={"text": "Nuevo, sin llamar desde el 3 sep", "source_ref": "prio-1", "observed_at": None},
        playbook_steps=OPENING_STEPS,
        sales_motion_key="outbound",
    )
    opening = brief["lines"][-1]
    assert opening["type"] == "open"
    assert opening["text"] == "Hola, soy Toni de Vocify. ¿Te pillo en mal momento?"
    assert opening["source"] == "playbook"


def test_no_open_line_without_opening_step_or_motion():
    brief = prepare_cold_brief_v2(
        coverage="complete",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task=None,
        hoy_why={"text": "Nuevo, sin llamar desde el 3 sep", "source_ref": "prio-1", "observed_at": None},
        playbook_steps=[{"step_id": "pitch", "label": "Pitch", "criterion": "Explicó el producto"}],
        sales_motion_key="outbound",
    )
    assert [line["type"] for line in brief["lines"]] == ["who", "why"]

    no_motion = prepare_cold_brief_v2(
        coverage="complete",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task=None,
        hoy_why={"text": "Nuevo, sin llamar desde el 3 sep", "source_ref": "prio-1", "observed_at": None},
        playbook_steps=OPENING_STEPS,
        sales_motion_key=None,
    )
    assert [line["type"] for line in no_motion["lines"]] == ["who", "why"]


def test_partial_read_keeps_verified_lines_and_notice():
    brief = prepare_cold_brief_v2(
        coverage="partial",
        profile={"jobtitle": "AE", "company_name": "Acme"},
        tz_name=TZ,
        crm_task=None,
        hoy_why=None,
        playbook_steps=[],
        sales_motion_key=None,
    )
    assert brief["status"] == "partial"
    assert brief["notice"] == "No se pudo cargar todo."
    assert brief["lines"]


def test_priority_reason_text_for_uncalled_contact():
    text = priority_reason_text(
        "no_calls_logged",
        created_at="2026-09-03T08:00:00+02:00",
        tz_name=TZ,
    )
    assert text == "Nuevo, sin llamar desde el 3 sep"


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
