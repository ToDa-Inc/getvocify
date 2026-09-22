"""Deterministic score from extraction for the intelligence store hook."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.services.coaching.score_assembly import attach_score_to_job_payload, build_score_from_extraction

MEMO = {
    "id": "memo-1",
    "playbook_version_id": "pv-1",
    "screening_outcome": None,
}

EXTRACTION = {
    "summary": "Objeción de precio trabajada",
    "objections": [{"text": "Está caro", "category": "price"}],
    "intelligence": {
        "version": 1,
        "input_revision": "rev-4",
        "objections": [{"id": "obj-1", "category": "price", "evidence_refs": ["ev-1"]}],
        "playbook_observations": [
            {
                "step_id": "handle_price",
                "playbook_version_id": "pv-1",
                "status": "met",
                "evidence_refs": ["ev-1"],
            }
        ],
        "evidence": [
            {
                "id": "ev-1",
                "source_type": "transcript",
                "source_id": "memo-1",
                "quote": "Está caro",
            }
        ],
    },
}


def test_cited_objection_and_playbook_yield_score_without_crm_bonus():
    open_deal = build_score_from_extraction(
        extraction=EXTRACTION,
        memo=MEMO,
        input_revision="rev-4",
        crm_outcome="open",
    )
    won_deal = build_score_from_extraction(
        extraction=EXTRACTION,
        memo=MEMO,
        input_revision="rev-4",
        crm_outcome="closed_won",
    )
    assert open_deal is not None
    assert open_deal["input_revision"] == "rev-4"
    assert open_deal["value"] == won_deal["value"]
    assert open_deal["value"] is not None
    assert open_deal["crm_outcome"] == "open"
    assert won_deal["crm_outcome"] == "closed_won"


def test_empty_extraction_does_not_add_score_key():
    payload = {"version": 1, "status": "partial", "input_revision": "rev-4"}
    enriched = attach_score_to_job_payload(
        MEMO,
        payload,
        extraction={"summary": "", "objections": []},
    )
    assert "score" not in enriched


def test_voicemail_does_not_publish_a_mark():
    score = build_score_from_extraction(
        extraction=EXTRACTION,
        memo={**MEMO, "screening_outcome": "voicemail"},
        input_revision="rev-4",
    )
    assert score is not None
    assert score["value"] is None


def test_missing_playbook_is_unavailable():
    score = build_score_from_extraction(
        extraction=EXTRACTION,
        memo={"id": "memo-1"},
        input_revision="rev-4",
    )
    assert score is not None
    assert score["status"] == "unavailable"
    assert score["value"] is None
    assert score["reason"] == "missing_playbook"


def test_met_without_evidence_does_not_publish_a_mark():
    extraction = {
        **EXTRACTION,
        "intelligence": {
            **EXTRACTION["intelligence"],
            "playbook_observations": [
                {"step_id": "handle_price", "status": "met", "evidence_refs": []},
            ],
        },
    }
    score = build_score_from_extraction(extraction=extraction, memo=MEMO, input_revision="rev-4")
    assert score is not None
    assert score["value"] is None
    assert score["met_steps"] == 0
    assert score["unknown_steps"] == 1
