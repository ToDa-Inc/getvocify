"""evals/F07 stays runnable: every case names advertised tools and only known checks."""

import json
import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

from app.services.crm_copilot.prompts import DATA_PROMPT, build_system_prompt
from app.services.crm_copilot.tools import ASK_DATA_TOOLS, build_openai_tools

CASES = Path(__file__).resolve().parents[2] / "evals" / "F07" / "cases.json"
ROUTE_KEYS = {"id", "kind", "question", "expect_first_any", "forbid"}
ANSWER_KEYS = {
    "id", "kind", "question", "tool_name", "tool_args", "tool_result",
    "must_not_contain", "must_contain_any", "must_contain_all",
}


def _cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_every_case_is_well_formed_and_names_advertised_tools():
    cases = _cases()
    advertised = {tool["function"]["name"] for tool in build_openai_tools(data_tools=True)}
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["question"].strip(), case["id"]
        if case["kind"] == "route":
            assert set(case) <= ROUTE_KEYS, case["id"]
            assert case["expect_first_any"], case["id"]
            assert set(case["expect_first_any"]) <= advertised, case["id"]
            assert set(case.get("forbid") or []) <= advertised, case["id"]
            assert not set(case["expect_first_any"]) & set(case.get("forbid") or []), case["id"]
        else:
            assert case["kind"] == "answer", case["id"]
            assert set(case) <= ANSWER_KEYS, case["id"]
            assert case["tool_name"] in advertised, case["id"]
            assert case.get("must_contain_any") or case.get("must_contain_all"), case["id"]


def test_each_data_tool_has_a_routing_case_and_coverage_cases_exist():
    cases = _cases()
    routed = {name for case in cases if case["kind"] == "route" for name in case["expect_first_any"]}
    assert ASK_DATA_TOOLS <= routed
    coverages = {case["tool_result"].get("coverage") for case in cases if case["kind"] == "answer"}
    assert {"unavailable", "forbidden", "complete"} <= coverages


def _eval_script():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "eval_ask_tools.py"
    spec = importlib.util.spec_from_file_location("eval_ask_tools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_cases_answer_a_skill_load_like_the_loop_does():
    script = _eval_script()
    call = {"id": "c1", "name": "load_skill", "arguments": {"name": "lookup"}}
    assistant, tool = script.skill_turn(call, 0)
    assert assistant["tool_calls"][0]["function"]["name"] == "load_skill"
    assert tool["tool_call_id"] == "c1"
    assert json.loads(tool["content"])["content"] == script.SKILL_BODIES["lookup"]
    unknown = script.skill_turn({"name": "load_skill", "arguments": {"name": "nope"}}, 1)[1]
    assert json.loads(unknown["content"])["ok"] is False
    assert script.check_route({"expect_first_any": ["search_contacts"]}, ["load_skill"])


def test_the_data_prompt_is_only_added_with_the_flag():
    assert DATA_PROMPT.strip() in build_system_prompt({}, data_tools=True)
    assert DATA_PROMPT.strip() not in build_system_prompt({}, data_tools=False)
    for name in ASK_DATA_TOOLS:
        assert name in DATA_PROMPT
