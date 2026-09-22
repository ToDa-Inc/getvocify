"""Development conversations for scoring. They are not a company's playbook."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-evals-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-evals-32b")

from app.services.coaching.scoring import assemble_score

CASES = Path(__file__).resolve().parents[2] / "evals" / "F09" / "cases.json"
PLAYBOOK = {"id": "pb", "ambiguous": False}


def _load():
    return json.loads(CASES.read_text())


def _score(case, crm_outcome=None):
    return assemble_score(
        playbook=PLAYBOOK,
        criteria_statuses=case["criteria"],
        evidence_refs=case["cited_quotes"],
        cited_refs=case["cited_quotes"],
        proposed_value=case["proposed_value"],
        crm_outcome=case["crm_outcome"] if crm_outcome is None else crm_outcome,
        input_revision=case["id"],
        playbook_version_id="pb-1",
    )


def test_the_practice_set_has_calls_meetings_and_the_traps():
    cases = _load()
    assert len(cases) >= 20
    assert {"call", "meeting"} <= {case["channel"] for case in cases}
    assert {"call_easy_meeting", "meeting_objection", "ambiguous", "transcript_error", "no_evidence"} <= {
        case["kind"] for case in cases
    }


def test_a_quote_that_is_not_in_the_transcript_cannot_be_used():
    for case in _load():
        missing = [quote for quote in case["cited_quotes"] if quote not in case["transcript"]]
        if case["kind"] == "transcript_error":
            assert missing
        else:
            assert missing == []


def test_an_easy_meeting_does_not_outrank_a_handled_objection():
    cases = _load()
    easy = next(case for case in cases if case["id"] == "c01")
    hard = next(case for case in cases if case["id"] == "c05")
    easy_score = _score(easy, crm_outcome="won")
    hard_score = _score(hard, crm_outcome="open")
    assert easy_score["value"] == easy["proposed_value"]
    assert easy_score["value"] < hard_score["value"]
    assert _score(easy, crm_outcome="lost")["value"] == easy_score["value"]


def test_ambiguity_and_silence_do_not_invent_a_mark():
    cases = {case["id"]: case for case in _load()}
    ambiguous = _score(cases["c09"])
    assert ambiguous["value"] is None
    assert ambiguous["adherence"] is None
    silence = _score(cases["c17"])
    assert silence["value"] is None
    assert silence["status"] == "partial"
