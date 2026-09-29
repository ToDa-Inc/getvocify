"""Run the Ask eval against a real model.

    cd backend && python -m evals.ask.run --model google/gemini-3.8-flash --out /tmp/ask_eval.md
    python -m evals.ask.run --only ae01,mg04         # a few cases
    python -m evals.ask.run --persona mgr            # one persona

Real: the Ask loop, the tools, grounding, prompt, and the model call (uses OPENROUTER_API_KEY).
Stubbed on purpose: Supabase and HubSpot are in-memory fixtures with known totals, so nothing here
reads or writes a real database or CRM. Run it before changing the model, the prompt or a tool.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

CASES = Path(__file__).with_name("cases.json")
# Lookups and session plumbing, not data reads: they do not count toward a case's tool budget.
META_TOOLS = {"search_contacts", "get_contact", "inspect_record", "load_skill", "remember", "reset_session"}
ISO_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
INTERNALS = re.compile(
    r"\b(deal_story|find_interactions|objection_breakdown|next_actions|my_coaching|competitor_mentions|meetings_agreed|playbook_lookup|"
    r"crm_call_stats|crm_lost_reasons|hubspot_query|hubspot_describe|team_health|search_contacts|contact_id|memo_id|user_id|ev-[0-9a-f]{4,}|"
    r"u-[a-z]+|c-[a-z]+|hs_\w+|tool_call|pb-[\w-]+|bad_moment|status_quo|wrong_person|needs_to_consult)\b|\{\"|\bm\d{2}\b"
)
RANKING = re.compile(r"(?i)(mejor vendedor|el mejor comercial|la mejor comercial|peor vendedor|ranking|top vendedor|best (rep|seller|salesperson|performer)|worst (rep|seller|salesperson|performer)|leaderboard)")
ES_WORDS = set("que qué el la los las de del un una es en y con para por mi tu tus mis cómo cuál cuántas cuántos quién este esta hola hay se".split())
EN_WORDS = set("the a is of and to in for with my how what which who this that did you your are have has".split())


def lang(text: str) -> str:
    words = re.findall(r"[a-záéíóúñ¿]+", text.lower())
    es = sum(w in ES_WORDS for w in words) + sum(ch in text for ch in "¿ñáéíóú")
    en = sum(w in EN_WORDS for w in words)
    return "es" if es >= en else "en"


def number_variants(value) -> list[str]:
    forms = {str(value)}
    if isinstance(value, int) and value >= 1000:
        forms |= {f"{value:,}", f"{value:,}".replace(",", "."), f"{value:,}".replace(",", " "), f"{value // 1000}k", f"{value // 1000}K"}
    if isinstance(value, (int, float)) and value < 0:  # "81,8% menos" says the sign in words
        return sorted({str(value), *number_variants(-value)})
    if isinstance(value, float):
        forms |= {f"{value:.1f}", f"{value:.1f}".replace(".", ",")}
        if value == int(value):
            forms.add(str(int(value)))
    return sorted(forms)


def check(case: dict, run: dict, truth: dict) -> list[str]:
    """Empty list = pass. Each string is one reason it did not."""
    fails: list[str] = []
    text = run["text"] or ""
    tools = run["tools"]
    counted = [t for t in tools if t not in META_TOOLS]
    if run["error"]:
        return [f"error: {run['error']}"]
    if case.get("expect_tools_any") and not set(case["expect_tools_any"]) & set(tools):
        fails.append(f"expected one of {case['expect_tools_any']}, used {tools or 'none'}")
    for tool in case.get("forbid_tools", []):
        if tool in tools:
            fails.append(f"used forbidden tool {tool}")
    if "max_tools" in case and len(counted) > case["max_tools"]:
        fails.append(f"used {len(counted)} tools (max {case['max_tools']}): {counted}")
    if case.get("expect_tools_all") and not set(case["expect_tools_all"]) <= set(tools):
        fails.append(f"expected all of {case['expect_tools_all']}, used {tools or 'none'}")
    for rule in case.get("max_matches", []):
        found = len(re.findall(rule["pattern"], text))
        if found > rule["max"]:
            fails.append(f"/{rule['pattern']}/ appears {found}x (max {rule['max']}): off-topic padding")
    if text.rstrip().endswith("?") and not case.get("allow_question"):
        fails.append("ends with a question offering more")
    if case.get("expect_confirm") and not run["confirm"]:
        fails.append("expected a confirmation card, got none")
    if not case.get("expect_confirm") and run["confirm"]:
        fails.append("a write was proposed but not asked for")
    for pattern in case.get("must", []):
        if not re.search(pattern, text):
            fails.append(f"missing /{pattern}/")
    for group in case.get("must_any", []):
        if not any(re.search(p, text) for p in group):
            fails.append(f"none of {group} present")
    for pattern in case.get("must_not", []):
        if re.search(pattern, text):
            fails.append(f"contains forbidden /{pattern}/")
    if case.get("expect_period_note") and not (run["coverage_note"] or {}).get("period_days"):
        fails.append("the tool chose the period but the app was not told to say it")
    for key in case.get("numbers", []):
        if not any(re.search(rf"(?<![\d.,]){re.escape(v)}(?![\d])", text) for v in number_variants(truth[key])):
            fails.append(f"number {key}={truth[key]} not in the answer")
    if INTERNALS.search(text):
        fails.append(f"leaks an internal: {INTERNALS.search(text).group(0)!r}")
    if not case.get("allow_ranking_words") and RANKING.search(text):
        fails.append(f"ranking language: {RANKING.search(text).group(0)!r}")
    words = len(text.split())
    if words > case.get("max_words", 110):
        fails.append(f"{words} words (max {case.get('max_words', 110)})")
    if not text.strip() and not run["confirm"]:
        fails.append("empty answer")
    want = case.get("lang") or lang(case["q"])
    if len(case["q"].split()) >= 3 and text and lang(text) != want:
        fails.append(f"answered in {lang(text)}, asked in {want}")
    if ISO_DATE.search(text):
        fails.append(f"raw ISO date in the answer: {ISO_DATE.search(text).group(0)}")
    return fails


def warnings(run: dict) -> list[str]:
    """Not failures: the safety net worked, but it costs a second model call."""
    return [f"first draft stated a number no tool returned; rewritten ({run['resets']}x)"] if run["resets"] else []


def patch_world():
    """Point every dependency at fixtures. Nothing below can reach a real database or CRM."""
    import app.deps as deps
    from app.services.crm_copilot import intel_tools, tools
    from evals.ask import fixtures

    db, bundle, company = fixtures.build_db(), fixtures.build_bundle(), fixtures.build_company()
    deps.get_supabase = lambda: db
    intel_tools._company = lambda ctx, actor: company
    tools._crm = lambda ctx: bundle
    real = tools.execute_tool

    async def execute(name, args, ctx):
        if name == "search_contacts":
            q = str(args.get("query") or "").lower()
            hits = [c for c in fixtures.CONTACTS.values() if q and (q in c["name"].lower() or q in c["company"].lower() or any(part in c["name"].lower() or part in c["company"].lower() for part in q.split() if len(part) > 3))]
            return {"contacts": hits[:5]}
        if name in ("get_contact", "inspect_record"):
            c = fixtures.CONTACTS.get(str(args.get("contact_id")))
            return c or {"ok": False, "error": "not found"}
        return await real(name, args, ctx)

    tools.execute_tool = execute

    # The coaching and team screens' own producers are tested upstream; here they return the fixture's fixed answer.
    from fastapi.responses import JSONResponse

    from app.api import coaching as coaching_api, team_insights as team_api

    async def my_coaching(flow, membership, supabase):
        return fixtures.COACHING_ANA

    async def team_health(**kwargs):
        return JSONResponse(fixtures.TEAM_BODY)

    coaching_api.get_my_coaching_summary = my_coaching
    team_api.get_team_adherence = team_health
    return fixtures


async def run_case(case: dict, fixtures) -> dict:
    from app.services.crm_copilot import web_sessions as ws

    user = "u-ana" if case["persona"] == "ae" else "u-dev"
    role = case.get("role", "member")
    ws._sessions.clear()
    ws.bind_ask_actor(user, fixtures.COMPANY, role, f"eval-{case['id']}")
    tools_used: list[str] = []
    resets = 0

    async def sink(event: dict) -> None:
        nonlocal resets
        if event["type"] == "tool_start":
            tools_used.append(event["tool"])
        elif event["type"] == "content_reset":
            resets += 1

    started = time.perf_counter()
    try:
        for earlier in case.get("earlier", []):  # a conversation: only the last question is judged
            await ws.live_ask_loop(earlier, on_event=None)
        payload = await ws.live_ask_loop(case["q"], on_event=sink)
        error = None if payload else "the loop returned nothing"
    except Exception as exc:  # noqa: BLE001
        payload, error = None, f"{type(exc).__name__}: {exc}"
    payload = payload or {}
    return {
        "id": case["id"], "text": payload.get("text", ""), "tools": tools_used, "confirm": bool(payload.get("confirmation")),
        "evidence": len(payload.get("evidence") or []), "coverage_note": payload.get("coverage_note"),
        "seconds": round(time.perf_counter() - started, 1), "error": error, "resets": resets,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--only")
    parser.add_argument("--persona", choices=["ae", "mgr"])
    parser.add_argument("--out")
    args = parser.parse_args()

    from app.config import settings

    if not settings.OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY is not set: the eval needs a real model.", file=sys.stderr)
        return 2
    if args.model:
        settings.ASK_MODEL = args.model
    from app.services.crm_copilot import model_profile

    fixtures = patch_world()
    cases = json.loads(CASES.read_text())
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.persona:
        cases = [c for c in cases if c["persona"] == args.persona]

    model = model_profile.ask_model()
    lines = [f"# Ask eval: {model}", f"{len(cases)} cases, today {fixtures.NOW.date()}", ""]
    passed = 0
    rewrites = 0
    results = []
    for case in cases:
        run = await run_case(case, fixtures)
        fails = check(case, run, fixtures.TRUTH)
        warns = warnings(run)
        passed += not fails
        rewrites += bool(warns)
        results.append({**run, "fails": fails, "warns": warns})
        mark = "PASS" if not fails else "FAIL"
        print(f"{mark} {case['id']:5} {run['seconds']:>5}s  tools={run['tools'] or '-'}  {case['q'][:60]}", flush=True)
        lines += [
            f"## {case['id']} [{mark}] ({case['persona']})",
            f"**Q:** {case['q']}",
            f"**Tools:** {', '.join(run['tools']) or 'none'} · {run['seconds']}s · evidence {run['evidence']}"
            + (f" · coverage {run['coverage_note']}" if run["coverage_note"] else ""),
            "", "> " + (run["text"] or "(empty)").replace("\n", "\n> "), "",
        ]
        if case.get("note"):
            lines.append(f"_Intent: {case['note']}_")
        lines += [f"- ✗ {f}" for f in fails] + [f"- ⚠ {w}" for w in warns] + [""]
    lines.insert(2, f"**{passed}/{len(cases)} passed** · {rewrites} answer(s) needed the number safety net")
    report = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(report)
        Path(args.out).with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n{passed}/{len(cases)} passed on {model} ({rewrites} needed the number safety net)")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
