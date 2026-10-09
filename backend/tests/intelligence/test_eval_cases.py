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
    "commitment_due_at", "commitment_undated", "commitment_not_kind",
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

    shaped, errors, _meta = asyncio.run(runner.run_case(Flaky(1), memo, delay=0))
    assert shaped["interest"] == "low"
    assert errors == ["ValueError: Empty model response"]
    shaped, errors, _meta = asyncio.run(runner.run_case(Flaky(5), memo, delay=0))
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


def _shaped(*commitments):
    return {
        "pain_confirmed": None, "objections": [], "meeting": {"agreed": None, "starts_at": None, "precision": "unknown"},
        "commitments": list(commitments),
    }


def test_an_undated_commitment_does_not_break_the_date_checks():
    check = _runner().check
    shaped = _shaped({"kind": "send", "due_at": None, "temporal_precision": "unknown"})
    assert check({"commitment_due_date": "2026-09-24"}, shaped)
    assert check({"commitment_due_at": "2026-09-24T11:00:00+02:00"}, shaped)


def test_undated_and_excluded_kind_expectations():
    check = _runner().check
    undated = _shaped({"kind": "send", "due_at": None, "temporal_precision": "unknown"})
    dated = _shaped({"kind": "call", "due_at": "2026-09-24T00:00:00+02:00", "temporal_precision": "date"})
    assert check({"commitment_undated": True}, undated) == []
    assert check({"commitment_undated": True}, dated)
    assert check({"commitment_not_kind": "call"}, undated) == []
    assert check({"commitment_not_kind": "call"}, dated)


def test_a_run_is_valid_jsonl_with_its_id_time_model_and_tokens(tmp_path, monkeypatch, capsys):
    runner = _runner()
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([
        {"id": "a", "transcript": "Them: Hola.", "expect": {"min_commitments": 0}},
        {"id": "b", "transcript": "Them: Adiós.", "expect": {"min_commitments": 1}},
    ]), encoding="utf-8")

    class Model:
        last_call_meta = {"model": "m-1", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

        async def chat_json(self, *_args, **_kwargs):
            return {"commitments": []}

    monkeypatch.setattr(runner, "CASES", cases)
    monkeypatch.setattr(runner, "LLMClient", Model)
    out = tmp_path / "run.jsonl"
    assert asyncio.run(runner.main(["--out", str(out)])) == 1
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    head, *rows, summary = records
    assert head["type"] == "run" and head["run_id"] and head["started_at"] and head["prompt"] == runner.PROMPT_VERSION
    assert [(r["id"], r["pass"], r["total_tokens"], r["model"]) for r in rows] == [("a", True, 15, "m-1"), ("b", False, 15, "m-1")]
    assert summary["type"] == "summary" and summary["run_id"] == head["run_id"]
    assert (summary["cases"], summary["failed"], summary["total_tokens"]) == (2, 1, 30)
    assert summary["finished_at"]
    assert "failed" in capsys.readouterr().out


# ------------------------------------------------------------------ v7 cases and the accuracy report

CASES_V7 = BACKEND / "evals" / "C04" / "cases_v7.json"
KNOWN_V7 = {"objections", "no_objections_of_category", "competitors", "qualification", "qualification_values"}
CATEGORIES = {"price", "timing", "authority", "competitor", "status_quo", "trust", "other"}
OBSTACLES = {"bad_moment", "gatekeeper", "wrong_person", "needs_to_consult", "other"}


def _v7_cases():
    return json.loads(CASES_V7.read_text(encoding="utf-8"))


def test_v7_cases_are_well_formed_and_cover_what_the_release_needs():
    cases = _v7_cases()
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["transcript"].strip() and case["expect"], case["id"]
        assert set(case["expect"]) <= KNOWN_V7, case["id"]
        criteria = {c["criterion_id"] for c in case.get("playbook_qualification") or []}
        assert set(case["expect"].get("qualification") or {}) <= criteria, case["id"]
        assert set(case["expect"].get("qualification_values") or {}) <= criteria, case["id"]
        custom = {o["id"] for o in case.get("playbook_objections") or []}
        for wanted in case["expect"].get("objections") or []:
            assert wanted.get("category") is None or wanted["category"] in CATEGORIES | OBSTACLES, case["id"]
            if wanted.get("objection_id"):
                assert wanted["objection_id"] in custom, case["id"]
    categories = [w["category"] for c in cases for w in c["expect"].get("objections") or [] if w.get("category")]
    assert len(categories) >= 10
    assert {"price", "timing", "authority", "status_quo", "competitor", "trust"} <= set(categories)
    assert {"bad_moment", "gatekeeper", "needs_to_consult"} & set(categories)  # obstacle vs objection
    assert any(w.get("kind") == "obstacle" for c in cases for w in c["expect"].get("objections") or [])
    assert sum(1 for c in cases if any("objection_id" in w for w in c["expect"].get("objections") or [])) >= 3
    statuses = {
        s for c in cases for want in (c["expect"].get("qualification") or {}).values()
        for s in (want if isinstance(want, list) else [want])
    }
    assert {"found", "missing", "not_applicable", "unknown"} <= statuses
    assert any(c["expect"].get("qualification_values") for c in cases)


def test_v7_transcripts_are_conversations_with_speaker_markers():
    for case in _v7_cases():
        assert "You:" in case["transcript"] and "Them:" in case["transcript"], case["id"]


def _shaped_v7(objections=(), qualification=()):
    return {
        "pain_confirmed": None, "meeting": {"agreed": None, "starts_at": None, "precision": "unknown"},
        "commitments": [], "objections": list(objections), "qualification_observations": list(qualification),
        "competitor_mentions": [], "playbook_observations": [],
    }


def test_the_base_runner_checks_the_category_when_a_case_names_one():
    runner = _runner()
    price = {"kind": "objection", "category": "price"}
    assert runner.check({"objections": [{"category": "price"}]}, _shaped_v7([price])) == []
    failures = runner.check({"objections": [{"category": "timing"}]}, _shaped_v7([price]))
    assert failures and "category" in failures[0]
    assert runner.check({"objections": [{"category": "price"}]}, _shaped_v7())  # nothing read is a miss
    # kind is checked too, and a v6 object without objection_id counts as "not a custom one"
    assert runner.check({"objections": [{"category": "price", "kind": "obstacle"}]}, _shaped_v7([price]))
    assert runner.check({"objections": [{"category": "price", "objection_id": None}]}, _shaped_v7([price])) == []
    assert runner.check({"objections": [{"objection_id": "erp"}]}, _shaped_v7([price]))
    # a case that names no category keeps passing exactly as before
    assert runner.check({"min_objections": 1}, _shaped_v7([price])) == []


def test_an_obstacle_is_not_allowed_to_read_as_a_price_or_timing_objection():
    runner = _runner()
    expect = {"objections": [{"category": "bad_moment", "kind": "obstacle"}], "no_objections_of_category": ["price", "timing"]}
    good = _shaped_v7([{"kind": "obstacle", "category": "bad_moment"}])
    assert runner.check(expect, good) == []
    bad = _shaped_v7([{"kind": "obstacle", "category": "bad_moment"}, {"kind": "objection", "category": "timing"}])
    assert any("must not be read" in f for f in runner.check(expect, bad))
    # an obstacle whose category happens to be "other" does not trip the ban
    assert runner.check({"no_objections_of_category": ["other"]}, _shaped_v7([{"kind": "obstacle", "category": "other"}])) == []


def test_custom_objection_matching_is_checked_by_id():
    runner = _runner()
    read = _shaped_v7([{"kind": "objection", "category": "other", "objection_id": "integracion-erp"}])
    assert runner.check({"objections": [{"objection_id": "integracion-erp"}]}, read) == []
    assert runner.check({"objections": [{"objection_id": "rgpd-datos"}]}, read)
    assert runner.check({"objections": [{"objection_id": None}]}, read)


def test_qualification_status_and_value_are_checked():
    runner = _runner()
    read = _shaped_v7(qualification=[
        {"criterion_id": "presupuesto", "status": "found", "value": "20.000 € aprobados"},
        {"criterion_id": "plazo", "status": "missing", "value": None},
    ])
    expect = {"qualification": {"presupuesto": "found", "plazo": ["missing", "unknown"]},
              "qualification_values": {"presupuesto": ["20.000", "veinte mil"]}}
    assert runner.check_v7(expect, read) == []
    assert runner.check_v7({"qualification": {"plazo": "found"}}, read)
    assert runner.check_v7({"qualification": {"otro": "found"}}, read)  # a criterion the model skipped
    assert runner.check_v7({"qualification_values": {"presupuesto": ["50.000"]}}, read)
    assert runner.check_v7({"qualification_values": {"plazo": ["x"]}}, read)


def test_per_field_accuracy_counts_each_named_field_on_its_own():
    runner = _runner()
    tally = {}
    read = _shaped_v7([{"kind": "objection", "category": "price"}, {"kind": "obstacle", "category": "gatekeeper"}])
    runner.check_objections({"objections": [{"category": "price", "kind": "objection"}]}, read, tally)
    runner.check_objections({"objections": [{"category": "timing", "kind": "objection"}]}, read, tally)
    runner.check_objections({"objections": [{"category": "gatekeeper", "kind": "objection"}]}, read, tally)
    runner.check_objections({"no_objections_of_category": ["price"]}, read, tally)
    runner.check_v7(
        {"qualification": {"a": "found"}}, _shaped_v7(qualification=[{"criterion_id": "a", "status": "missing"}]), tally,
    )
    report = runner.accuracy(tally)
    # category: price ok; timing, gatekeeper-as-objection and the banned price are misses
    assert report["category"] == {"correct": 1, "total": 4, "pct": 25.0}
    assert report["kind"] == {"correct": 3, "total": 3, "pct": 100.0}
    assert report["qualification_status"] == {"correct": 0, "total": 1, "pct": 0.0}
    assert runner.accuracy({}) == {}


def test_a_v7_run_uses_the_v7_prompt_the_case_inputs_and_reports_accuracy(tmp_path, monkeypatch):
    runner = _runner()
    base, v4, v7 = tmp_path / "c.json", tmp_path / "c4.json", tmp_path / "c7.json"
    base.write_text(json.dumps([{"id": "old", "transcript": "Them: Hola.", "expect": {"min_objections": 0}}]), encoding="utf-8")
    v4.write_text("[]", encoding="utf-8")
    v7.write_text(json.dumps([{
        "id": "new", "transcript": "You: ¿Presupuesto? Them: Veinte mil euros. Them: Es muy caro.",
        "playbook_qualification": [{"criterion_id": "presupuesto", "label": "Presupuesto"}],
        "playbook_objections": [{"id": "erp", "label": "ERP", "trigger": "t"}],
        "expect": {"objections": [{"category": "price", "objection_id": None}],
                   "qualification": {"presupuesto": "found"}, "qualification_values": {"presupuesto": ["veinte"]}},
    }]), encoding="utf-8")
    sent = {}

    class Model:
        last_call_meta = {"model": "m", "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        async def chat_json(self, messages, **_kwargs):
            sent["system"], sent["user"] = messages[0]["content"], json.loads(messages[1]["content"])
            return {
                "objections": [{"kind": "objection", "category": "price", "resolution": "open", "quote": "Es muy caro"}],
                "qualification_observations": [
                    {"criterion_id": "presupuesto", "status": "found", "value": "veinte mil euros", "quote": "Veinte mil euros"},
                ],
            }

    monkeypatch.setattr(runner, "CASES", base)
    monkeypatch.setattr(runner, "CASES_V4", v4)
    monkeypatch.setattr(runner, "CASES_V7", v7)
    monkeypatch.setattr(runner, "LLMClient", Model)
    out = tmp_path / "run.jsonl"
    assert asyncio.run(runner.main(["--v7", "--out", str(out)])) == 0
    head, *rows, summary = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert head["prompt"] == "intelligence_v7" and head["cases_file"] == "c.json+c4.json+c7.json"
    assert [(r["id"], r["pass"]) for r in rows] == [("old", True), ("new", True)]
    assert sent["user"]["playbook_qualification"][0]["criterion_id"] == "presupuesto"
    assert sent["user"]["playbook_objections"][0]["id"] == "erp"
    assert "qualification_observations" in sent["system"]
    assert summary["accuracy"]["category"] == {"correct": 1, "total": 1, "pct": 100.0}
    assert summary["accuracy"]["qualification_value"]["pct"] == 100.0
