"""Run the Ask copilot prompt and tools against evals/F07/cases.json with CRM_COPILOT_MODEL.

route cases check the first tool the model calls. answer cases feed one tool result and check the reply.
Usage (from backend/): .venv/bin/python scripts/eval_ask_tools.py
Exit code 1 when any case fails.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.crm_copilot.prompts import SKILL_BODIES, DATA_PROMPT_VERSION, build_system_prompt  # noqa: E402
from app.services.crm_copilot.tools import build_openai_tools  # noqa: E402
from app.services.llm import LLMClient  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "evals" / "F07" / "cases.json"
TOOLS = build_openai_tools(data_tools=True)
SYSTEM = build_system_prompt({}, data_tools=True)
MAX_SKILL_LOADS = 2


async def _ask(llm: LLMClient, messages: list[dict]):
    return await llm.chat_tools(
        [{"role": "system", "content": SYSTEM}, *messages],
        tools=TOOLS,
        model=settings.CRM_COPILOT_MODEL,
        provider="openrouter",
        extra={"reasoning": {"effort": "low"}, "max_tokens": 4000},
        timeout=60.0,
    )


def skill_turn(call: dict, index: int) -> list[dict]:
    """The soul tells the model to load a skill before using it; answer it the way the loop does."""
    args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
    skill = str(args.get("name") or "")
    body = SKILL_BODIES.get(skill)
    payload = {"name": skill, "content": body} if body else {"ok": False, "error": f"unknown skill {skill}"}
    call_id = call.get("id") or f"skill-{index}"
    return [
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": "load_skill", "arguments": json.dumps(args)},
        }]},
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload, ensure_ascii=False)},
    ]


def check_route(case: dict, names: list[str]) -> list[str]:
    failures = []
    first = names[0] if names else None
    if first not in case["expect_first_any"]:
        failures.append(f"first tool: expected one of {case['expect_first_any']}, got {first!r}")
    bad = sorted(set(names) & set(case.get("forbid") or []))
    if bad:
        failures.append(f"forbidden tools called: {bad}")
    return failures


def check_answer(case: dict, text: str) -> list[str]:
    low = (text or "").lower()
    failures = [f"contains {phrase!r}" for phrase in case.get("must_not_contain") or [] if phrase.lower() in low]
    anyof = case.get("must_contain_any") or []
    if anyof and not any(phrase.lower() in low for phrase in anyof):
        failures.append(f"none of {anyof}")
    failures += [f"missing {phrase!r}" for phrase in case.get("must_contain_all") or [] if phrase.lower() not in low]
    return failures


async def run_case(llm: LLMClient, case: dict) -> tuple[list[str], str]:
    user = {"role": "user", "content": case["question"]}
    if case["kind"] == "route":
        messages = [user]
        loaded: list[str] = []
        for _ in range(MAX_SKILL_LOADS + 1):
            result = await _ask(llm, messages)
            calls = getattr(result, "tool_calls", None) or []
            names = [tc.get("name") for tc in calls]
            if not names or names[0] != "load_skill" or len(loaded) == MAX_SKILL_LOADS:
                break
            messages += skill_turn(calls[0], len(loaded))
            args = calls[0].get("arguments") if isinstance(calls[0].get("arguments"), dict) else {}
            loaded.append(str(args.get("name") or "?"))
        trail = [f"load_skill:{name}" for name in loaded] + names
        return check_route(case, names), ",".join(trail) or (getattr(result, "content", "") or "")[:120]
    call = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "eval-1",
            "type": "function",
            "function": {"name": case["tool_name"], "arguments": json.dumps(case["tool_args"])},
        }],
    }
    tool = {"role": "tool", "tool_call_id": "eval-1", "content": json.dumps(case["tool_result"], ensure_ascii=False)}
    result = await _ask(llm, [user, call, tool])
    if getattr(result, "tool_calls", None):
        names = [tc.get("name") for tc in result.tool_calls]
        return [f"expected an answer, got more tool calls {names}"], ",".join(names)
    text = (getattr(result, "content", None) or "").strip()
    return check_answer(case, text), text[:200]


async def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    llm = LLMClient()
    failed = 0
    for case in cases:
        try:
            failures, got = await run_case(llm, case)
        except Exception as exc:
            failures, got = [f"error: {exc}"], ""
        failed += bool(failures)
        print(json.dumps({"id": case["id"], "pass": not failures, "failures": failures, "got": got}, ensure_ascii=False))
    print(json.dumps({"prompt": DATA_PROMPT_VERSION, "model": settings.CRM_COPILOT_MODEL, "cases": len(cases), "failed": failed}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
