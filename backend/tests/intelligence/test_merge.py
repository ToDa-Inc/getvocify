"""Two producers write one intelligence block. Neither may erase what the other found."""

from app.services.intelligence.interpret import extraction_with_intelligence, merge_intelligence

LLM = {
    "version": 1, "input_revision": "r1", "status": "ready", "interest": "high", "pain_confirmed": None,
    "objections": [{"id": "obj-1", "category": "price"}], "commitments": [{"id": "com-1"}],
    "meeting": {"agreed": None, "evidence_refs": []}, "competitor_mentions": [{"name": "Gong"}],
    "playbook_observations": [], "evidence": [{"id": "ev-1", "quote": "caro"}], "prompt_version": "intelligence_v2",
}
JEV = {
    "version": 1, "input_revision": "r1", "status": "partial", "interest": None, "pain_confirmed": True,
    "objections": [], "commitments": [], "meeting": {"agreed": True, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": ["ev-2"]},
    "competitor_mentions": [], "playbook_observations": [], "evidence": [{"id": "ev-2", "quote": "quedamos"}],
}


def test_the_classifier_does_not_erase_what_the_extractor_found():
    merged = merge_intelligence(LLM, JEV)
    assert merged["objections"] == LLM["objections"] and merged["commitments"] == LLM["commitments"]
    assert merged["interest"] == "high" and merged["competitor_mentions"] == [{"name": "Gong"}]
    assert merged["pain_confirmed"] is True and merged["meeting"]["agreed"] is True


def test_the_extractor_does_not_erase_what_the_classifier_found():
    merged = merge_intelligence(JEV, LLM)
    assert merged["pain_confirmed"] is True and merged["meeting"]["agreed"] is True
    assert merged["objections"] == LLM["objections"] and merged["interest"] == "high"


def test_evidence_is_the_union_by_id_and_the_extractor_prompt_version_survives():
    merged = merge_intelligence(LLM, JEV)
    assert {e["id"] for e in merged["evidence"]} == {"ev-1", "ev-2"}
    assert merged["prompt_version"] == "intelligence_v2"
    assert merge_intelligence(JEV, LLM)["prompt_version"] == "intelligence_v2"


def test_the_better_status_wins():
    assert merge_intelligence(LLM, JEV)["status"] == "ready"
    assert merge_intelligence({**LLM, "status": "unavailable"}, JEV)["status"] == "partial"


def test_a_block_for_an_older_revision_is_not_merged_into_a_newer_one():
    stale = {**LLM, "input_revision": "r0"}
    merged = merge_intelligence(stale, JEV)
    assert merged["objections"] == [] and merged["input_revision"] == "r1"


def test_nothing_to_merge_returns_the_incoming_block():
    assert merge_intelligence(None, JEV) == JEV
    assert merge_intelligence({}, JEV) == JEV


def test_attaching_intelligence_merges_into_the_stored_block_and_keeps_the_extraction():
    extraction = {"summary": "Llamada", "intelligence": LLM}
    out = extraction_with_intelligence(extraction, JEV)
    assert out["summary"] == "Llamada"
    assert out["intelligence"]["objections"] == LLM["objections"] and out["intelligence"]["pain_confirmed"] is True


def test_a_newer_extractor_version_replaces_the_older_block_instead_of_inheriting_it():
    old = {**LLM, "prompt_version": "intelligence_v1", "objections": [{"id": "old", "category": "timing", "kind": "objection"}]}
    fresh = {**LLM, "objections": [], "prompt_version": "intelligence_v2"}
    merged = merge_intelligence(old, fresh)
    assert merged["objections"] == [] and merged["prompt_version"] == "intelligence_v2"
