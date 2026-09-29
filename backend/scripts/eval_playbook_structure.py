"""Run "structure with AI" (playbook_structure_v1) against evals/P01/cases.json with the configured model.

Usage (from backend/): .venv/bin/python -u scripts/eval_playbook_structure.py [--runs 3] [--out runs/<file>.jsonl]
The plan runs it 3 times before the flag is switched on (--runs 3): a case passes the run only if every
run passes it. The output is JSONL: a "run" record (id, start time, prompt, model), one "case" record per
case and run with its tokens and the checks that failed, and a "summary" record. It goes to --out, or to
stdout without it; with --out, stdout gets the summary. A case whose answer came from the line parser
(`fallback`) is retried once, then counted as a failed case: the parser is a safety net, not a pass.
Exit code 1 when any case fails.

Case expectations (`expect`):
  min_steps / max_steps      bounds on the number of steps
  reason                     null | "no_process" | "too_short" | "grouped"
  categories                 objection categories that must be present ("a|b" = either)
  min_examples               steps carrying a literal example
  must_contain_any           at least one of these terms appears in the steps or answers (case-insensitive)
  must_not_contain           none of these appears (case-insensitive)
  language                   "es" | "en": the language the steps come out in
Always checked: no fallback, labels of 1 to 5 words, no attitude criterion (an empty one is allowed: it
is what the flow leaves for a person to write), objection categories among the seven, steps <= 7.
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
from app.services.llm import LLMClient  # noqa: E402
from app.services.playbooks.structure import (  # noqa: E402
    MAX_AI_STEPS,
    PROMPT_VERSION,
    detect_language,
    structure_source,
)
from app.services.playbooks.structured import OBJECTION_CATEGORIES, normalize_objections, normalize_steps  # noqa: E402
from app.services.text_guard import generic_criterion  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "evals" / "P01" / "cases.json"
ATTEMPTS = 2
RETRY_DELAY_S = 10.0
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


class Recording:
    """Wraps the real client: counts calls and adds up the tokens the provider reports."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.calls = 0
        self.tokens = dict.fromkeys(TOKEN_KEYS, 0)
        self.model = None

    async def chat_json(self, messages, **kwargs):
        self.calls += 1
        try:
            return await self.llm.chat_json(messages, **kwargs)
        finally:
            meta = self.llm.last_call_meta
            self.model = meta.get("model") or self.model
            for key in TOKEN_KEYS:
                self.tokens[key] += meta.get(key) or 0


def _text_of(result: dict) -> str:
    parts = []
    for step in result["steps"]:
        parts += [step["label"], step["criterion"], step.get("example", "")]
    parts += [item["guidance"] for item in result["objections"]]
    return "\n".join(parts)


def check(expect: dict, result: dict) -> list[str]:
    failures: list[str] = []
    steps = result["steps"]
    if result["fallback"]:
        failures.append("fallback: the model failed or returned nothing usable")
    if "min_steps" in expect and len(steps) < expect["min_steps"]:
        failures.append(f"steps: expected at least {expect['min_steps']}, got {len(steps)}")
    if "max_steps" in expect and len(steps) > expect["max_steps"]:
        failures.append(f"steps: expected at most {expect['max_steps']}, got {len(steps)}")
    if len(steps) > MAX_AI_STEPS:
        failures.append(f"steps: never more than {MAX_AI_STEPS}, got {len(steps)}")
    if "reason" in expect and result["reason"] != expect["reason"]:
        failures.append(f"reason: expected {expect['reason']!r}, got {result['reason']!r}")

    found = {item["category"] for item in result["objections"]}
    for wanted in expect.get("categories", []):
        if not found & set(wanted.split("|")):
            failures.append(f"objection {wanted!r} missing, got {sorted(found)!r}")
    if found - set(OBJECTION_CATEGORIES):
        failures.append(f"objection categories outside the seven: {sorted(found - set(OBJECTION_CATEGORIES))!r}")

    examples = sum(1 for step in steps if step.get("example"))
    if examples < expect.get("min_examples", 0):
        failures.append(f"examples: expected at least {expect['min_examples']}, got {examples}")

    for index, step in enumerate(steps, start=1):
        words = len(step["label"].split())
        if not 1 <= words <= 5:
            failures.append(f"step {index}: label {step['label']!r} has {words} words (2 to 4 asked)")
        if step["criterion"] and generic_criterion(step["criterion"]):
            failures.append(f"step {index}: attitude criterion {step['criterion']!r}")

    text = _text_of(result).lower()
    for term in expect.get("must_not_contain", []):
        if term.lower() in text:
            failures.append(f"must_not_contain: {term!r} appears")
    wanted_any = expect.get("must_contain_any")
    if wanted_any and not any(term.lower() in text for term in wanted_any):
        failures.append(f"must_contain_any: none of {wanted_any!r} appears")
    if expect.get("language") and steps and detect_language(text, default="") != expect["language"]:
        failures.append(f"language: expected {expect['language']!r} output")

    try:
        if steps:
            normalize_steps(steps)
        normalize_objections(result["objections"])
    except Exception as exc:  # the output must always save
        failures.append(f"normalize: {exc}")
    return failures


async def run_case(llm: Recording, case: dict, *, delay: float = RETRY_DELAY_S) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    result = None
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(delay)
        result = await structure_source(case["source"], case["motion_key"], case.get("lang", "es"), llm=llm)
        if not result["fallback"]:
            return result, errors
        errors.append("fallback (model error, timeout or unusable JSON)")
    return result, errors


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--runs", type=int, default=1, help="repeat every case (the plan asks for 3)")
    parser.add_argument("--case", action="append", help="only these case ids")
    args = parser.parse_args(argv)
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
    llm = Recording(LLMClient())
    out = args.out.open("w", encoding="utf-8") if args.out else sys.stdout

    def emit(record: dict) -> None:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()

    run_id = uuid.uuid4().hex
    emit({
        "type": "run", "run_id": run_id, "started_at": _now(), "prompt": PROMPT_VERSION,
        "provider": settings.LLM_PROVIDER, "cases_file": CASES.name, "runs": args.runs,
    })
    failed_cases: set[str] = set()
    failed_runs = retried = 0
    for run_number in range(1, args.runs + 1):
        for case in cases:
            before_calls, before_tokens = llm.calls, dict(llm.tokens)
            result, errors = await run_case(llm, case)
            failures = check(case["expect"], result) if result else ["no result"]
            if failures:
                failed_cases.add(case["id"])
                failed_runs += 1
            retried += bool(errors) and not (result or {}).get("fallback")
            emit({
                "type": "case", "id": case["id"], "run": run_number, "pass": not failures,
                "failures": failures, "errors": errors, "model": llm.model,
                "steps": [step["label"] for step in (result or {}).get("steps", [])],
                "objections": [item["category"] for item in (result or {}).get("objections", [])],
                "reason": (result or {}).get("reason"), "calls": llm.calls - before_calls,
                **{key: llm.tokens[key] - before_tokens[key] for key in TOKEN_KEYS},
            })
    summary = {
        "type": "summary", "run_id": run_id, "finished_at": _now(), "prompt": PROMPT_VERSION,
        "provider": settings.LLM_PROVIDER, "model": llm.model, "cases": len(cases), "runs": args.runs,
        "failed_cases": len(failed_cases), "failed_case_ids": sorted(failed_cases), "failed_runs": failed_runs,
        "passed_after_retry": retried, "calls": llm.calls, **llm.tokens,
    }
    emit(summary)
    if args.out:
        out.close()
        print(json.dumps(summary))
    return 1 if failed_cases else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
