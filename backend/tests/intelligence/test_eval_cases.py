"""evals/C04 cases stay runnable: every expectation names a field the eval script checks."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")

BACKEND = Path(__file__).resolve().parents[2]
CASES = BACKEND / "evals" / "C04" / "cases.json"
KNOWN = {
    "pain_confirmed", "pain_confirmed_not", "meeting_agreed", "meeting_starts_at",
    "meeting_precision", "min_objections", "min_commitments", "commitment_due_date",
    "commitment_due_at",
}


def _runner():
    spec = importlib.util.spec_from_file_location("eval_intelligence", BACKEND / "scripts" / "eval_intelligence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_case_has_a_transcript_and_only_known_expectations():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["transcript"].strip()
        assert case["expect"]
        assert set(case["expect"]) <= KNOWN, case["id"]


def test_a_model_error_is_retried_once_then_reported_not_raised():
    runner = _runner()
    memo = {"id": "m", "transcript": "Them: Hola.", "capture_started_at": runner.CAPTURED_AT, "extraction": {}}

    class Flaky:
        def __init__(self, fails):
            self.fails = fails

        async def chat_json(self, *_args, **_kwargs):
            if self.fails:
                self.fails -= 1
                raise ValueError("Empty model response")
            return {"interest": "low"}

    shaped, errors = asyncio.run(runner.run_case(Flaky(1), memo, delay=0))
    assert shaped["interest"] == "low"
    assert errors == ["ValueError: Empty model response"]
    shaped, errors = asyncio.run(runner.run_case(Flaky(5), memo, delay=0))
    assert shaped is None
    assert len(errors) == 2


def test_commitment_due_date_is_checked_by_day():
    check = _runner().check
    shaped = {
        "pain_confirmed": None, "objections": [], "meeting": {"agreed": None, "starts_at": None, "precision": "unknown"},
        "commitments": [{"due_at": "2026-09-24T00:00:00+02:00"}],
    }
    assert check({"commitment_due_date": "2026-09-24"}, shaped) == []
    assert check({"commitment_due_date": "2026-09-25"}, shaped)
