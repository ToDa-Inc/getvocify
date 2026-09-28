"""F12 eval cases: finalize_suggest_result playbook grounding from latest turn."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from app.services.copilot.grounding import SuggestGrounding, finalize_suggest_result

CASES = Path(__file__).resolve().parents[2] / "evals" / "F12" / "cases.json"


def _load() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))


def _grounding(raw: dict | None) -> SuggestGrounding | None:
    if raw is None:
        return None
    return SuggestGrounding(
        interaction_kind=str(raw.get("interaction_kind") or "meeting"),
        playbook_version_id=str(raw.get("playbook_version_id") or "").strip() or None,
        evidence_ids=frozenset(raw.get("evidence_ids") or []),
        playbook_snapshot=raw.get("playbook_snapshot"),
    )


def test_f12_eval_cases_cover_finalize_contract():
    cases = _load()
    assert len(cases) >= 4
    finalize_cases = [case for case in cases if case.get("kind") == "finalize"]
    assert len(finalize_cases) >= 3
    assert any(case["id"] == "f12_two_motions_not_finalize" for case in cases)


def test_f12_finalize_cases_match_expectations():
    for case in _load():
        if case.get("kind") != "finalize":
            continue
        result = finalize_suggest_result(
            call_mode=case["call_mode"],
            suggestion=dict(case["suggestion"]),
            grounding=_grounding(case.get("grounding")),
            latest_turn=case.get("latest_turn") or "",
        )
        assert result["playbook_ready"] is case["expect_playbook_ready"]
        assert result["evidence_refs"] == case.get("expect_evidence_refs", [])
        if not case["expect_playbook_ready"]:
            assert result["suggestion"]["say_this"] == ""


def test_f12_null_grounding_stays_silent():
    case = next(c for c in _load() if c["id"] == "f12_two_motions_not_finalize")
    result = finalize_suggest_result(
        call_mode=case["call_mode"],
        suggestion=dict(case["suggestion"]),
        grounding=None,
        latest_turn=case.get("latest_turn") or "",
    )
    assert result["playbook_ready"] is False
    assert result["evidence_refs"] == []
