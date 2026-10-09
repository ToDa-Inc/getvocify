"""Run the C04 intelligence prompt against evals/C04/cases.json with the configured model.

Usage (from backend/): .venv/bin/python -u scripts/eval_intelligence.py [--v4 | --v7] [--out runs/<file>.jsonl]
--v4 runs the v6 prompt (steps + competitors) on cases.json + cases_v4.json; --v7 runs the v7 prompt
(qualification + the company's own objections) on all three files.
The run is JSONL: a "run" record (id, start time, prompt, model), one "case" record per case with the
tokens its call used, and a "summary" record. It goes to --out, or to stdout without it; with --out,
stdout gets the summary. The provider reports tokens, not cost. A model error is retried once, then
counted as a failed case. Exit code 1 when any case fails.

Per-field accuracy: every expectation that names a field (objection category and kind, custom
objection id, qualification status and value, step status, competitors) is tallied per field and the
summary reports {correct, total, pct} for each, so a regression in one field is not hidden by the
case pass rate. Category accuracy is checked whenever a case specifies `objections[].category`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.intelligence.extract import (  # noqa: E402
    OBSERVATIONS_PROMPT_VERSION,
    PROMPT_VERSION,
    QUALIFICATION_PROMPT_VERSION,
    extract_intelligence,
)
from app.services.llm import LLMClient  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "evals" / "C04" / "cases.json"
# v4 (PLAYBOOK_OBSERVATIONS_ENABLED): step observations and named competitors. With --v4 the
# v3 cases also run on the v4 prompt, so the added sections cannot regress the old facts.
CASES_V4 = Path(__file__).resolve().parents[1] / "evals" / "C04" / "cases_v4.json"
# v7 (PLAYBOOK_QUALIFICATION_ENABLED): qualification observations and the company's own objections.
# With --v7 the older cases also run on the v7 prompt, so the added sections cannot regress them.
CASES_V7 = Path(__file__).resolve().parents[1] / "evals" / "C04" / "cases_v7.json"
CAPTURED_AT = "2026-09-22T10:00:00+02:00"
ATTEMPTS = 2
RETRY_DELAY_S = 10.0
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def check(expect: dict, shaped: dict) -> list[str]:
    meeting = shaped["meeting"]
    got = {
        "pain_confirmed": shaped["pain_confirmed"],
        "meeting_agreed": meeting["agreed"],
        "meeting_starts_at": meeting["starts_at"],
        "meeting_precision": meeting["precision"],
    }
    failures = [f"{key}: expected {value!r}, got {got[key]!r}" for key, value in expect.items() if key in got and got[key] != value]
    if expect.get("pain_confirmed_not") and shaped["pain_confirmed"] is True:
        failures.append("pain_confirmed: must not be true")
    if len(shaped["objections"]) < expect.get("min_objections", 0):
        failures.append(f"objections: expected at least {expect['min_objections']}, got {len(shaped['objections'])}")
    if len(shaped["commitments"]) < expect.get("min_commitments", 0):
        failures.append(f"commitments: expected at least {expect['min_commitments']}, got {len(shaped['commitments'])}")
    failures += check_objections(expect, shaped)
    if "commitment_due_date" in expect:
        days = [item["due_at"][:10] for item in shaped["commitments"] if item.get("due_at")]
        if expect["commitment_due_date"] not in days:
            failures.append(f"commitment_due_date: expected {expect['commitment_due_date']!r}, got {days!r}")
    if "commitment_due_at" in expect:
        timed = [item["due_at"] for item in shaped["commitments"] if item.get("temporal_precision") == "time"]
        if expect["commitment_due_at"] not in timed:
            failures.append(f"commitment_due_at: expected {expect['commitment_due_at']!r}, got {timed!r}")
    if expect.get("commitment_undated") and not any(item.get("due_at") is None for item in shaped["commitments"]):
        failures.append("commitment_undated: expected a commitment without a day")
    if "commitment_not_kind" in expect:
        kinds = [item.get("kind") for item in shaped["commitments"]]
        if expect["commitment_not_kind"] in kinds:
            failures.append(f"commitment_not_kind: {expect['commitment_not_kind']!r} must not be a commitment, got {kinds!r}")
    return failures


def _tally(tally: dict | None, field: str, ok: bool) -> None:
    if tally is None:
        return
    entry = tally.setdefault(field, [0, 0])
    entry[0] += bool(ok)
    entry[1] += 1


def accuracy(tally: dict) -> dict:
    """{field: {correct, total, pct}} from the per-field counts."""
    return {
        field: {"correct": correct, "total": total, "pct": round(100 * correct / total, 1)}
        for field, (correct, total) in sorted(tally.items())
        if total
    }


def check_objections(expect: dict, shaped: dict, tally: dict | None = None) -> list[str]:
    """expect.objections: each {category?, kind?, objection_id?} must be matched by one objection the
    model read (every key it names must be equal; `objection_id: null` means "not a custom one").
    expect.no_objections_of_category: none of these categories may appear on a kind "objection".
    Each named key is tallied on its own, so category accuracy is reported apart from kind."""
    failures: list[str] = []
    read = shaped.get("objections") or []
    for wanted in expect.get("objections") or []:
        keys = [key for key in ("category", "kind", "objection_id") if key in wanted]
        best = max(
            read,
            key=lambda item: sum(item.get(key) == wanted[key] for key in keys),
            default=None,
        )
        for key in keys:
            ok = best is not None and best.get(key) == wanted[key]
            _tally(tally, {"category": "category", "kind": "kind", "objection_id": "objection_id"}[key], ok)
            if not ok:
                got = None if best is None else best.get(key)
                failures.append(f"objection {key}: expected {wanted[key]!r}, got {got!r} (read {[o.get(key) for o in read]!r})")
    banned = expect.get("no_objections_of_category") or []
    if banned:
        seen = [item.get("category") for item in read if item.get("kind", "objection") == "objection"]
        ok = not any(category in seen for category in banned)
        _tally(tally, "category", ok)
        if not ok:
            failures.append(f"objection categories {banned!r} must not be read, got {seen!r}")
    return failures


def check_v4(expect: dict, shaped: dict, tally: dict | None = None) -> list[str]:
    failures: list[str] = []
    statuses = {obs["step_id"]: obs["status"] for obs in shaped.get("playbook_observations") or []}
    for step_id, wanted in (expect.get("steps") or {}).items():
        allowed = wanted if isinstance(wanted, list) else [wanted]
        ok = statuses.get(step_id) in allowed
        _tally(tally, "step_status", ok)
        if not ok:
            failures.append(f"step {step_id}: expected {allowed!r}, got {statuses.get(step_id)!r}")
    names = [item["name"].lower() for item in shaped.get("competitor_mentions") or []]
    for name in expect.get("competitors") or []:
        ok = name.lower() in names
        _tally(tally, "competitor", ok)
        if not ok:
            failures.append(f"competitor {name!r} missing, got {names!r}")
    if expect.get("no_competitors") and names:
        _tally(tally, "competitor", False)
        failures.append(f"competitors: expected none, got {names!r}")
    elif expect.get("no_competitors"):
        _tally(tally, "competitor", True)
    return failures


def check_v7(expect: dict, shaped: dict, tally: dict | None = None) -> list[str]:
    """expect.qualification: {criterion_id: status | [statuses]}; expect.qualification_values:
    {criterion_id: [substrings]} where one of them must appear (lowercase) in what the prospect said."""
    failures: list[str] = []
    observed = {obs["criterion_id"]: obs for obs in shaped.get("qualification_observations") or []}
    for criterion_id, wanted in (expect.get("qualification") or {}).items():
        allowed = wanted if isinstance(wanted, list) else [wanted]
        got = (observed.get(criterion_id) or {}).get("status")
        ok = got in allowed
        _tally(tally, "qualification_status", ok)
        if not ok:
            failures.append(f"qualification {criterion_id}: expected {allowed!r}, got {got!r}")
    for criterion_id, needles in (expect.get("qualification_values") or {}).items():
        value = str((observed.get(criterion_id) or {}).get("value") or "").lower()
        ok = any(needle.lower() in value for needle in needles)
        _tally(tally, "qualification_value", ok)
        if not ok:
            failures.append(f"qualification {criterion_id} value: expected one of {needles!r}, got {value!r}")
    return failures


async def run_case(
    llm: LLMClient,
    memo: dict,
    *,
    delay: float = RETRY_DELAY_S,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
    playbook_qualification: list[dict] | None = None,
    playbook_objections: list[dict] | None = None,
) -> tuple[dict | None, list[str], dict]:
    errors = []
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(delay)
        try:
            shaped, meta = await extract_intelligence(
                memo, llm, prompt_version=prompt_version, playbook_steps=playbook_steps,
                playbook_qualification=playbook_qualification, playbook_objections=playbook_objections,
            )
            return shaped, errors, meta
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}"[:200])
    return None, errors, {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--v4", action="store_true", help="run the v6 prompt: v3 cases + cases_v4.json")
    parser.add_argument("--v7", action="store_true", help="run the v7 prompt: v3 + v4 + cases_v7.json")
    args = parser.parse_args(argv)
    if args.v7:
        version = QUALIFICATION_PROMPT_VERSION
    else:
        version = OBSERVATIONS_PROMPT_VERSION if args.v4 else PROMPT_VERSION
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    files = [CASES.name]
    if args.v4 or args.v7:
        cases += json.loads(CASES_V4.read_text(encoding="utf-8"))
        files.append(CASES_V4.name)
    if args.v7:
        cases += json.loads(CASES_V7.read_text(encoding="utf-8"))
        files.append(CASES_V7.name)
    llm = LLMClient()
    out = args.out.open("w", encoding="utf-8") if args.out else sys.stdout

    def emit(record: dict) -> None:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()

    run_id = uuid.uuid4().hex
    emit({
        "type": "run", "run_id": run_id, "started_at": _now(),
        "prompt": version, "model": settings.INTELLIGENCE_MODEL,
        "cases_file": "+".join(files),
    })
    failed = errored = retried = 0
    tokens = dict.fromkeys(TOKEN_KEYS, 0)
    tally: dict[str, list[int]] = {}
    for case in cases:
        memo = {
            "id": case["id"],
            "transcript": case["transcript"],
            "capture_started_at": CAPTURED_AT,
            "timezone": "Europe/Madrid",
            "extraction": {},
        }
        shaped, errors, meta = await run_case(
            llm, memo, prompt_version=version, playbook_steps=case.get("playbook_steps"),
            playbook_qualification=case.get("playbook_qualification"),
            playbook_objections=case.get("playbook_objections"),
        )
        if shaped is None:
            failures = ["model error on every attempt"]
        else:
            failures = (
                check(case["expect"], shaped)  # includes the objection checks
                + check_v4(case["expect"], shaped, tally)
                + check_v7(case["expect"], shaped, tally)
            )
            check_objections(case["expect"], shaped, tally)  # same checks again, only to tally accuracy
        failed += bool(failures)
        errored += shaped is None
        retried += bool(errors) and shaped is not None
        for key in TOKEN_KEYS:
            tokens[key] += meta.get(key) or 0
        emit({
            "type": "case", "id": case["id"], "pass": not failures, "failures": failures, "errors": errors,
            "model": meta.get("model"), **{key: meta.get(key) for key in TOKEN_KEYS},
        })
    summary = {
        "type": "summary", "run_id": run_id, "finished_at": _now(), "prompt": version,
        "model": settings.INTELLIGENCE_MODEL, "cases": len(cases), "failed": failed,
        "model_errors": errored, "passed_after_retry": retried, **tokens,
        "accuracy": accuracy(tally),
    }
    emit(summary)
    if args.out:
        out.close()
        print(json.dumps(summary))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
