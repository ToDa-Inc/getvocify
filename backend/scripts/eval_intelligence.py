"""Run the C04 intelligence prompt against evals/C04/cases.json with the configured model.

Usage (from backend/): .venv/bin/python -u scripts/eval_intelligence.py [--out runs/<file>.jsonl]
The run is JSONL: a "run" record (id, start time, prompt, model), one "case" record per case with the
tokens its call used, and a "summary" record. It goes to --out, or to stdout without it; with --out,
stdout gets the summary. The provider reports tokens, not cost. A model error is retried once, then
counted as a failed case. Exit code 1 when any case fails.
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
    extract_intelligence,
)
from app.services.llm import LLMClient  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "evals" / "C04" / "cases.json"
# v4 (PLAYBOOK_OBSERVATIONS_ENABLED): step observations and named competitors. With --v4 the
# v3 cases also run on the v4 prompt, so the added sections cannot regress the old facts.
CASES_V4 = Path(__file__).resolve().parents[1] / "evals" / "C04" / "cases_v4.json"
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


def check_v4(expect: dict, shaped: dict) -> list[str]:
    failures: list[str] = []
    statuses = {obs["step_id"]: obs["status"] for obs in shaped.get("playbook_observations") or []}
    for step_id, wanted in (expect.get("steps") or {}).items():
        allowed = wanted if isinstance(wanted, list) else [wanted]
        if statuses.get(step_id) not in allowed:
            failures.append(f"step {step_id}: expected {allowed!r}, got {statuses.get(step_id)!r}")
    names = [item["name"].lower() for item in shaped.get("competitor_mentions") or []]
    for name in expect.get("competitors") or []:
        if name.lower() not in names:
            failures.append(f"competitor {name!r} missing, got {names!r}")
    if expect.get("no_competitors") and names:
        failures.append(f"competitors: expected none, got {names!r}")
    return failures


async def run_case(
    llm: LLMClient,
    memo: dict,
    *,
    delay: float = RETRY_DELAY_S,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
) -> tuple[dict | None, list[str], dict]:
    errors = []
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(delay)
        try:
            shaped, meta = await extract_intelligence(
                memo, llm, prompt_version=prompt_version, playbook_steps=playbook_steps,
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
    parser.add_argument("--v4", action="store_true", help="run the v4 prompt: v3 cases + cases_v4.json")
    args = parser.parse_args(argv)
    version = OBSERVATIONS_PROMPT_VERSION if args.v4 else PROMPT_VERSION
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.v4:
        cases += json.loads(CASES_V4.read_text(encoding="utf-8"))
    llm = LLMClient()
    out = args.out.open("w", encoding="utf-8") if args.out else sys.stdout

    def emit(record: dict) -> None:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()

    run_id = uuid.uuid4().hex
    emit({
        "type": "run", "run_id": run_id, "started_at": _now(),
        "prompt": version, "model": settings.INTELLIGENCE_MODEL,
        "cases_file": CASES.name + (f"+{CASES_V4.name}" if args.v4 else ""),
    })
    failed = errored = retried = 0
    tokens = dict.fromkeys(TOKEN_KEYS, 0)
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
        )
        if shaped is None:
            failures = ["model error on every attempt"]
        else:
            failures = check(case["expect"], shaped) + check_v4(case["expect"], shaped)
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
    }
    emit(summary)
    if args.out:
        out.close()
        print(json.dumps(summary))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
