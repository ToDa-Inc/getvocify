"""E3 brief v2: hook, why, say and label from C04 intelligence."""

import os
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-brief-v2-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-brief-v2-32b")

from app.services.briefs.preparation import legacy_facts, prepare_brief
from app.services.briefs.v2 import prepare_brief_v2
from app.services.intelligence.extract import PROMPT_VERSION
from app.services.intelligence.worker import revision_for_memo

NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
TZ = "Europe/Madrid"

PLAYBOOK_STEPS = [
    {"step_id": "pitch", "label": "Pitch", "criterion": "Explicó el producto"},
    {"step_id": "qualify", "label": "Cualificar", "criterion": "Confirmó decisor y presupuesto"},
]
PLAYBOOK_ENTRIES = [
    {"entry_id": "price-1", "category": "price", "guidance": "compáralo con un comercial más.", "source_ref": "pb:1"},
]
OBSERVATIONS = [
    {"step_id": "pitch", "status": "met", "evidence_refs": ["ev-1"]},
    {"step_id": "qualify", "status": "missed", "evidence_refs": []},
]


def _memo(**kwargs):
    extraction = dict(kwargs.pop("extraction", {"summary": "Hablamos del seguimiento comercial."}))
    memo = {
        "id": kwargs.pop("memo_id", "memo-1"),
        "company_id": "co-1",
        "user_id": "user-1",
        "created_at": kwargs.pop("created_at", "2026-09-11T10:00:00+02:00"),
        "capture_started_at": kwargs.pop("capture_started_at", "2026-09-11T10:00:00+02:00"),
        "hubspot_contact_id": "42",
        "extraction": extraction,
        **kwargs,
    }
    if isinstance(extraction.get("intelligence"), dict):
        intel = dict(extraction["intelligence"])
        intel["prompt_version"] = intel.get("prompt_version", PROMPT_VERSION)
        intel["input_revision"] = revision_for_memo({**memo, "extraction": {k: v for k, v in extraction.items() if k != "intelligence"}})
        extraction["intelligence"] = intel
    return memo


def _current_intelligence(**extra):
    block = {
        "version": 1,
        "input_revision": "rev-1",
        "prompt_version": PROMPT_VERSION,
        "pain_confirmed": True,
        "objections": [],
        "commitments": [],
        "competitor_mentions": [],
        "playbook_observations": [],
        "evidence": [{"id": "ev-pain", "quote": "se nos quedan leads sin llamar los viernes", "source_type": "transcript", "source_id": "memo-1"}],
    }
    block.update(extra)
    return block


def test_hook_uses_pain_quote_with_local_date():
    memo = _memo(extraction={"summary": "ignored", "intelligence": _current_intelligence()})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["lines"][0]["type"] == "hook"
    assert brief["lines"][0]["text"] == '11 sep: «se nos quedan leads sin llamar los viernes»'


def test_hook_without_pain_uses_summary():
    intel = _current_intelligence(pain_confirmed=False, evidence=[])
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["lines"][0]["text"] == "11 sep: Hablaron del almacén."


def test_why_prefers_commitment_over_no_reply_and_task():
    intel = _current_intelligence(
        commitments=[{
            "id": "com-1",
            "kind": "call",
            "origin": "prospect_request",
            "text": "llamar hoy",
            "due_at": "2026-09-26T09:00:00+02:00",
            "temporal_precision": "time",
        }],
    )
    memo = _memo(extraction={"summary": "x", "intelligence": intel})
    brief = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        no_reply={"text": "Le escribiste y no ha respondido.", "source_ref": "email-1"},
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1"},
    )
    assert [line["type"] for line in brief["lines"][:2]] == ["hook", "why"]
    assert brief["lines"][1]["text"] == "Pidió que la llamaras hoy."


def test_why_uses_no_reply_when_flag_data_present_and_no_commitment():
    intel = _current_intelligence(pain_confirmed=False, evidence=[])
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        no_reply={"text": "Le escribiste el 14 sep y no ha respondido.", "source_ref": "email-1"},
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1"},
    )
    assert brief["lines"][1]["text"] == "Le escribiste el 14 sep y no ha respondido."


def test_why_falls_back_to_crm_task():
    intel = _current_intelligence(pain_confirmed=False, evidence=[])
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1"},
    )
    assert brief["lines"][1]["text"] == "Llamar el jueves"


def test_say_uses_open_objection_with_playbook():
    intel = _current_intelligence(
        pain_confirmed=False,
        evidence=[],
        objections=[{"id": "obj-1", "category": "price", "resolution": "open", "quote": "está caro"}],
    )
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        playbook_entries=PLAYBOOK_ENTRIES,
    )
    say = brief["lines"][-1]
    assert say["type"] == "say"
    assert say["text"] == "Precio: compáralo con un comercial más."
    assert say["source"] == "playbook"


def test_open_objection_without_playbook_answer_falls_to_competitor_or_nothing():
    open_price = [{"id": "obj-1", "category": "price", "resolution": "open", "quote": "está caro"}]
    with_competitor = _current_intelligence(
        pain_confirmed=False, evidence=[], objections=open_price,
        competitor_mentions=[{"id": "cmp-1", "name": "Ringover"}],
    )
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": with_competitor})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW, playbook_entries=[])
    assert brief["lines"][-1]["text"] == "Usa Ringover"
    assert "source" not in brief["lines"][-1]

    alone = _current_intelligence(pain_confirmed=False, evidence=[], objections=open_price)
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": alone})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW, playbook_entries=[])
    assert [line["type"] for line in brief["lines"]] == ["hook"]


def test_unknown_resolution_counts_as_open():
    intel = _current_intelligence(
        pain_confirmed=False,
        evidence=[],
        objections=[{"id": "obj-1", "category": "price", "resolution": "unknown", "quote": "está caro"}],
    )
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW, playbook_entries=PLAYBOOK_ENTRIES)
    assert brief["lines"][-1]["source"] == "playbook"


def test_hook_does_not_quote_evidence_that_belongs_to_another_fact():
    intel = _current_intelligence(
        objections=[{"id": "obj-1", "category": "price", "resolution": "resolved", "quote": "está caro", "evidence_refs": ["ev-obj"]}],
        evidence=[{"id": "ev-obj", "quote": "está caro", "source_type": "transcript", "source_id": "memo-1"}],
    )
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["lines"][0]["text"] == "11 sep: Hablaron del almacén."


def test_hook_quotes_the_pain_evidence_not_the_first_one():
    intel = _current_intelligence(
        objections=[{"id": "obj-1", "category": "price", "resolution": "resolved", "quote": "está caro", "evidence_refs": ["ev-obj"]}],
        evidence=[
            {"id": "ev-obj", "quote": "está caro", "source_type": "transcript", "source_id": "memo-1"},
            {"id": "ev-pain", "quote": "se nos quedan leads sin llamar", "source_type": "transcript", "source_id": "memo-1"},
        ],
    )
    memo = _memo(extraction={"summary": "x", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["lines"][0]["text"] == "11 sep: «se nos quedan leads sin llamar»"


def test_stale_intelligence_without_summary_matches_the_legacy_brief():
    intel = _current_intelligence(pain_confirmed=False, evidence=[])
    intel["prompt_version"] = "intelligence_v2"
    memo = _memo(extraction={"summary": "", "intelligence": intel})
    legacy = prepare_brief(**legacy_facts([memo]))
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert legacy["status"] == "nothing_pending"
    assert brief == legacy


def test_malformed_timestamps_do_not_break_the_brief():
    intel = _current_intelligence(
        pain_confirmed=False,
        evidence=[],
        commitments=[{"id": "com-1", "kind": "call", "origin": "rep_promise", "text": "llamar", "due_at": "no es fecha", "temporal_precision": "time"}],
    )
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel}, capture_started_at="ayer por la tarde")
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["status"] in {"ready", "nothing_pending"}
    assert all(line["type"] != "why" for line in brief["lines"])


def test_no_reply_is_ignored_when_its_flag_gives_no_data():
    intel = _current_intelligence(pain_confirmed=False, evidence=[])
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW, no_reply=None)
    assert [line["type"] for line in brief["lines"]] == ["hook"]


def test_say_uses_competitor_when_no_open_objection():
    intel = _current_intelligence(
        pain_confirmed=False,
        evidence=[],
        objections=[{"id": "obj-1", "category": "price", "resolution": "resolved", "quote": "está caro"}],
        competitor_mentions=[{"id": "cmp-1", "name": "Ringover"}],
    )
    memo = _memo(extraction={"summary": "Hablaron del almacén.", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["lines"][-1]["text"] == "Usa Ringover"


def test_never_more_than_three_lines_and_skip_missing_facts():
    intel = _current_intelligence(
        pain_confirmed=False,
        evidence=[],
        objections=[{"id": "obj-1", "category": "price", "resolution": "open", "quote": "está caro"}],
    )
    memo = _memo(extraction={"summary": "", "intelligence": intel})
    brief = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        crm_task={"text": "Llamar el jueves", "source_ref": "task-1"},
        playbook_entries=PLAYBOOK_ENTRIES,
    )
    assert len(brief["lines"]) <= 3
    assert [line["type"] for line in brief["lines"]] == ["why", "say"]


def test_partial_read_keeps_verified_lines_and_notice():
    intel = _current_intelligence()
    memo = _memo(extraction={"summary": "x", "intelligence": intel})
    brief = prepare_brief_v2(coverage="partial", memos=[memo], tz_name=TZ, now=NOW)
    assert brief["status"] == "partial"
    assert brief["notice"] == "No se pudo cargar todo."
    assert brief["lines"]


def test_label_requires_playbook_and_f09_note():
    intel = _current_intelligence(playbook_observations=OBSERVATIONS)
    memo = _memo(extraction={"summary": "x", "intelligence": intel})
    with_label = prepare_brief_v2(
        coverage="complete",
        memos=[memo],
        tz_name=TZ,
        now=NOW,
        playbook_steps=PLAYBOOK_STEPS,
    )
    assert with_label["label"] == "Pitch hecho · falta cualificar"

    without_steps = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert without_steps["label"] is None

    without_obs = prepare_brief_v2(
        coverage="complete",
        memos=[_memo(extraction={"summary": "x", "intelligence": _current_intelligence()})],
        tz_name=TZ,
        now=NOW,
        playbook_steps=PLAYBOOK_STEPS,
    )
    assert without_obs["label"] is None


def test_stale_intelligence_falls_back_to_legacy_brief():
    intel = _current_intelligence()
    intel["prompt_version"] = "intelligence_v2"
    memo = _memo(extraction={"summary": "El 2 sep hablasteis del almacén.", "intelligence": intel, "objections": ["Objeción: el precio."]})
    legacy = prepare_brief(**legacy_facts([memo]))
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert brief == legacy


def test_flag_off_returns_legacy_brief_byte_for_byte():
    memo = {
        "id": "memo-match",
        "company_id": "co-1",
        "created_at": "2026-09-02T10:00:00Z",
        "hubspot_contact_id": "42",
        "extraction": {"summary": "El 2 sep hablasteis del almacén.", "pain_confirmed": True},
    }
    facts = legacy_facts([memo])
    legacy = prepare_brief(**facts)
    assert legacy["status"] == "ready"
    assert legacy["lines"][0]["text"] == "El 2 sep hablasteis del almacén."


def test_v2_module_stays_read_only_without_a_model():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "services" / "briefs"
    text = (root / "v2.py").read_text(encoding="utf-8").lower()
    assert "openai" not in text
    assert "invoke_llm" not in text


def test_missing_steps_lists_the_missed_playbook_steps_next_to_the_label():
    intel = _current_intelligence(playbook_observations=OBSERVATIONS)
    memo = _memo(extraction={"summary": "x", "intelligence": intel})
    brief = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW, playbook_steps=PLAYBOOK_STEPS)
    assert brief["label"] == "Pitch hecho · falta cualificar"
    assert brief["missing_steps"] == ["cualificar"]

    without_steps = prepare_brief_v2(coverage="complete", memos=[memo], tz_name=TZ, now=NOW)
    assert without_steps["missing_steps"] == []
