"""Run "structure with AI" against the eval cases with the configured model.

Three suites: P01 (default) is one call type at a time (playbook_structure_v2, `structure_source`);
P02 (`--suite P02`) is the whole company's mixed document (playbook_split_v2, `split_source`);
P03 (`--suite P03`) is PARTIAL documents through the same split flow: only a script, only a product
deck, a MEDDIC or BANT doc, a competitor battlecard, custom objections, a full foundation document.
It checks that each thing lands in its layer (call type / qualification / company) and that what the
source does not say stays empty.

Usage (from backend/): .venv/bin/python -u scripts/eval_playbook_structure.py [--suite P01|P02|P03] [--runs 3] [--out runs/<file>.jsonl]
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
  min_qualification / max_qualification   bounds on the number of "what has to come out" criteria
  criterion_ids              criterion_id values that must all be present (a template was used)
  min_custom / max_custom    bounds on the company's own (`custom`) objections
  min_objection_extras       objections carrying a meaning, a question or a proof
P02 cases (`routing`: bool, the candidate types offered; `expect`):
  types                      {call type key: the expectations above for that type}
  only_types                 the exact set of call types that must come out ([] = none)
  reason                     "no_process" when nothing is covered
  categories_in_each         objection categories every returned type must carry ("a|b" = either)
  language                   "es" | "en"
P03 cases add (`expect.company`, checked on the `company` block of the answer):
  empty                      nothing at all about the company
  sections_include / sections_exclude   company sections that must / must not hold something
  competitor_names           exactly these competitors (case-insensitive)
  competitor_empty_fields    {name: [fields]} that must stay empty for that competitor
  must_contain_any / must_not_contain   terms in the company text
A P02 case also fails on: a key that is not a candidate, a fallback, or any per-type check below.
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
from app.services.playbooks.intake import candidate_types  # noqa: E402
from app.services.playbooks.knowledge import sections as company_sections  # noqa: E402
from app.services.playbooks.structure import (  # noqa: E402
    MAX_AI_STEPS,
    PROMPT_VERSION,
    SPLIT_PROMPT_VERSION,
    detect_language,
    split_source,
    structure_source,
)
from app.services.playbooks.structured import (  # noqa: E402
    CUSTOM_CATEGORY,
    ENTRY_CATEGORIES,
    normalize_objections,
    normalize_qualification,
    normalize_steps,
)
from app.services.text_guard import generic_criterion  # noqa: E402

EVALS = Path(__file__).resolve().parents[1] / "evals"
SUITES = {name: EVALS / name / "cases.json" for name in ("P01", "P02", "P03")}
SPLIT_SUITES = frozenset({"P02", "P03"})
CASES = SUITES["P01"]
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
    for item in result["objections"]:
        parts += [item.get(name, "") for name in ("guidance", "label", "trigger", "meaning", "question", "proof")]
    for item in result.get("qualification", []):
        parts += [item.get(name, "") for name in ("label", "why", "good", "bad")]
    return "\n".join(parts)


def _count(expect: dict, name: str, got: int, failures: list[str]) -> None:
    if f"min_{name}" in expect and got < expect[f"min_{name}"]:
        failures.append(f"{name}: expected at least {expect[f'min_{name}']}, got {got}")
    if f"max_{name}" in expect and got > expect[f"max_{name}"]:
        failures.append(f"{name}: expected at most {expect[f'max_{name}']}, got {got}")


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
    if found - set(ENTRY_CATEGORIES):
        failures.append(f"objection categories outside the eight: {sorted(found - set(ENTRY_CATEGORIES))!r}")

    criteria = result.get("qualification", [])
    _count(expect, "qualification", len(criteria), failures)
    _count(expect, "custom", sum(1 for item in result["objections"] if item["category"] == CUSTOM_CATEGORY), failures)
    _count(
        expect, "objection_extras",
        sum(1 for item in result["objections"] if item.get("meaning") or item.get("question") or item.get("proof")),
        failures,
    )
    ids = {item.get("criterion_id") for item in criteria}
    for wanted in expect.get("criterion_ids", []):
        if wanted not in ids:
            failures.append(f"criterion_ids: {wanted!r} missing, got {sorted(i for i in ids if i)!r}")

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
        normalize_qualification(criteria)
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


def check_split(case: dict, result: dict) -> list[str]:
    """P02/P03: the call types a mixed document came out as, each held to the per-type checks (and,
    when the case expects it, its company block)."""
    expect = case["expect"]
    failures: list[str] = []
    if result["fallback"]:
        failures.append("fallback: the model failed or returned nothing usable")
    offered = {c["key"] for c in candidate_types(bool(case.get("routing")), {}, {}, case.get("lang", "es"))}
    got = {item["key"]: item for item in result["types"]}
    if set(got) - offered:
        failures.append(f"types outside the candidates: {sorted(set(got) - offered)!r}")
    if "only_types" in expect and set(got) != set(expect["only_types"]):
        failures.append(f"types: expected {sorted(expect['only_types'])!r}, got {sorted(got)!r}")
    if "reason" in expect and result["reason"] != expect["reason"]:
        failures.append(f"reason: expected {expect['reason']!r}, got {result['reason']!r}")
    for key, per_type in expect.get("types", {}).items():
        if key not in got:
            failures.append(f"{key}: type missing")
            continue
        item = got[key]
        failures += [
            f"{key}: {failure}"
            for failure in check(
                {**{k: v for k, v in per_type.items() if k != "reason"}, "language": expect.get("language")},
                {**item, "fallback": False},
            )
        ]
    for key, item in got.items():
        found = {entry["category"] for entry in item["objections"]}
        for wanted in expect.get("categories_in_each", []):
            if not found & set(wanted.split("|")):
                failures.append(f"{key}: objection {wanted!r} missing, got {sorted(found)!r}")
    if "company" in expect:
        failures += check_company(expect["company"], result.get("company") or {})
    return failures


def check_company(expect: dict, company: dict) -> list[str]:
    """P03: the company block of a whole-company answer."""
    failures: list[str] = []
    held = set(company_sections(company))
    if expect.get("empty") and held:
        failures.append(f"company: expected nothing, got {sorted(held)!r}")
    for key in expect.get("sections_include", []):
        if key not in held:
            failures.append(f"company: {key!r} is empty, got {sorted(held)!r}")
    for key in expect.get("sections_exclude", []):
        if key in held:
            failures.append(f"company: {key!r} should be empty")
    competitors = {item["name"].casefold(): item for item in company.get("competitors", [])}
    if "competitor_names" in expect and set(competitors) != {n.casefold() for n in expect["competitor_names"]}:
        failures.append(f"competitors: expected {expect['competitor_names']!r}, got {[c['name'] for c in competitors.values()]!r}")
    for name, fields in expect.get("competitor_empty_fields", {}).items():
        item = competitors.get(name.casefold())
        for field in fields if item else []:
            if item.get(field):
                failures.append(f"competitor {name}: {field!r} should be empty, got {item[field]!r}")
    text = json.dumps(company, ensure_ascii=False).lower()
    for term in expect.get("must_not_contain", []):
        if term.lower() in text:
            failures.append(f"company must_not_contain: {term!r} appears")
    wanted_any = expect.get("must_contain_any")
    if wanted_any and not any(term.lower() in text for term in wanted_any):
        failures.append(f"company must_contain_any: none of {wanted_any!r} appears")
    return failures


async def run_split_case(llm: Recording, case: dict, *, delay: float = RETRY_DELAY_S) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    result = None
    lang = case.get("lang", "es")
    candidates = candidate_types(bool(case.get("routing")), {}, {}, lang)
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(delay)
        result = await split_source(case["source"], candidates, lang, llm=llm)
        if not result["fallback"]:
            return result, errors
        errors.append("fallback (model error, timeout or unusable JSON)")
    return result, errors


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _labels(result: dict | None, split: bool) -> dict:
    """What the JSONL "case" record shows of the answer."""
    result = result or {}
    if split:
        return {
            "types": {item["key"]: [step["label"] for step in item["steps"]] for item in result.get("types", [])},
            "qualification": {
                item["key"]: [c["label"] for c in item.get("qualification", [])] for item in result.get("types", [])
            },
            "company_sections": company_sections(result.get("company") or {}),
        }
    return {
        "steps": [step["label"] for step in result.get("steps", [])],
        "objections": [item["category"] for item in result.get("objections", [])],
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite", choices=sorted(SUITES), default="P01",
        help="P01: one call type; P02: the whole company's document; P03: partial documents (script only, deck only, MEDDIC, battlecard...)",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--runs", type=int, default=1, help="repeat every case (the plan asks for 3)")
    parser.add_argument("--case", action="append", help="only these case ids")
    args = parser.parse_args(argv)
    split = args.suite in SPLIT_SUITES
    cases_file = SUITES[args.suite]
    prompt = SPLIT_PROMPT_VERSION if split else PROMPT_VERSION
    cases = json.loads(cases_file.read_text(encoding="utf-8"))
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
    llm = Recording(LLMClient())
    out = args.out.open("w", encoding="utf-8") if args.out else sys.stdout

    def emit(record: dict) -> None:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()

    run_id = uuid.uuid4().hex
    emit({
        "type": "run", "run_id": run_id, "started_at": _now(), "prompt": prompt,
        "provider": settings.LLM_PROVIDER, "cases_file": f"{args.suite}/{cases_file.name}", "runs": args.runs,
    })
    failed_cases: set[str] = set()
    failed_runs = retried = 0
    for run_number in range(1, args.runs + 1):
        for case in cases:
            before_calls, before_tokens = llm.calls, dict(llm.tokens)
            if split:
                result, errors = await run_split_case(llm, case)
                failures = check_split(case, result) if result else ["no result"]
            else:
                result, errors = await run_case(llm, case)
                failures = check(case["expect"], result) if result else ["no result"]
            if failures:
                failed_cases.add(case["id"])
                failed_runs += 1
            retried += bool(errors) and not (result or {}).get("fallback")
            emit({
                "type": "case", "id": case["id"], "run": run_number, "pass": not failures,
                "failures": failures, "errors": errors, "model": llm.model,
                **_labels(result, split),
                "reason": (result or {}).get("reason"), "calls": llm.calls - before_calls,
                **{key: llm.tokens[key] - before_tokens[key] for key in TOKEN_KEYS},
            })
    summary = {
        "type": "summary", "run_id": run_id, "finished_at": _now(), "prompt": prompt,
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
