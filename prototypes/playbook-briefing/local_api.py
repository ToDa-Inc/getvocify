"""Run from the repository root: LOCAL_OWNER_ID=<Vocify owner user id> <backend python> prototypes/playbook-briefing/local_api.py
then open prototypes/playbook-briefing/index.html on the dev server.

Local API for trying «Cómo trabajamos» against Vocify's real playbook (port 8888), with no login and no writes.

- Reads go to the real database (backend/.env): the playbook, the company notes.
- «Cómo trabajamos» (GET/PUT /playbooks/<key>/conduct) is the real one: it is read from and SAVED to the database.
- «Completar» / «Dile a Vocify» on a call type (POST /playbooks/<key>/fill) runs: it writes with the model and saves
  nothing. The company's fill saves at once, so it stays refused.
- POST /prototype/copilot/replay replays a recorded cold call (816ba4f7, exported to backend/evals/copilot/calls/) with the live brain (turns-6b, the eval) and the moments the
  page sends: about a minute and $0.03 of the production model each time.
- POST /prototype/copilot/rule turns a manager's sentence into one rule and tests it on an example the model writes
  (no real call): the live brain's card for that moment without the rule and with it. Three calls, a few seconds.
- POST /prototype/copilot/sample-call invents a buyer from the company's ICP, writes a short cold call with them and
  plays it with the live brain (turns-6b) and the company's rules: the cards and when they came. With "call" it plays
  the same call again (new rules). About 20-40 s and $0.01-0.03.
- POST /prototype/copilot/briefing explains a playbook (or the company notes) back as a sales manager would to a new
  rep, with what it does not say; POST /prototype/copilot/simulate is the live brain's card for one line of a client.
- POST /prototype/copilot/ask answers the manager about a playbook (a judgement, a question) or turns what they ask
  into one change for the editor.
- POST /prototype/copilot/structure turns a call type's playbook into the workspace's four areas (how to act, the
  milestones, key information, answers by theme); /prototype/copilot/edit routes a change asked in words.
- Every other write is refused here, so the editor's autosave cannot touch the database.
- Vocify writes with the production model through OpenRouter (Together is out of credit since 2026-10-27; Dani asked
  for OpenRouter for the prototype). The key stays in this process.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[2] / "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"))
# The production LLM settings (Together, OpenRouter, the model choice) from Railway, into this process only. Prints nothing.
_vars = subprocess.run(["railway", "variables", "--service", "getvocify", "--environment", "production", "--kv"],
                       capture_output=True, text=True, cwd=BACKEND).stdout
for _line in _vars.splitlines():
    _key, _, _value = _line.partition("=")
    if _key.startswith(("TOGETHER_", "LLM_", "OPENROUTER_")):
        os.environ[_key] = _value.strip().strip('"')

# The live brain's own calls (the eval's ask, the turn check) through OpenRouter, the same model as production's fallback.
os.environ["COPILOT_DIRECT_URL"] = "https://openrouter.ai/api/v1/chat/completions"
os.environ["COPILOT_DIRECT_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
os.environ["COPILOT_DIRECT_MODEL"] = "deepseek/deepseek-v4.1-flash"
from evals.strategic import run_v2 as _v2  # noqa: E402

_v2.MODEL = "deepseek/deepseek-v4.1-flash"
_post = _v2.httpx.post


def _on_together(url, *args, json=None, **kwargs):
    """Every model call of the eval as production's fallback sends it: reasoning off, served by Together only (the
    provider of the production path; other providers of the same model answered field names instead of a line)."""
    if json and "openrouter.ai" in str(url):
        effort = json.pop("reasoning_effort", "none")
        json = {**json, "reasoning": {"effort": effort}, "provider": {"only": ["together"], "require_parameters": True}}
    return _post(url, *args, json=json, **kwargs)


_v2.httpx.post = _on_together
# The playbook's own calls (fill, structure) ask for "together/…": in this process only, they go to the same model on
# OpenRouter (Together has no credit left). Production's settings are not touched.
from app.config import settings as _settings  # noqa: E402

_settings.TOGETHER_API_KEY = ""
_settings.TOGETHER_FALLBACKS = {**(_settings.TOGETHER_FALLBACKS or {}), "deepseek-ai/DeepSeek-V4.1-Flash": "deepseek/deepseek-v4.1-flash"}

import re  # noqa: E402

import uvicorn  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app.deps import get_membership, get_user_id  # noqa: E402
from app.main import app  # noqa: E402
from app.services.company import Membership  # noqa: E402

COMPANY = "70b7ffd2-c360-4d4f-a339-4affec769f7a"
USER = os.environ["LOCAL_OWNER_ID"]

app.dependency_overrides[get_user_id] = lambda: USER
app.dependency_overrides[get_membership] = lambda: Membership(id="local", company_id=COMPANY, user_id=USER, role="owner", status="active", sales_role=None)


@app.middleware("http")
async def reads_only(request, call_next):
    path = request.url.path
    fill = request.method == "POST" and re.search(r"/playbooks/(?!company/)[^/]+/fill$", path)
    if request.method in ("GET", "HEAD", "OPTIONS") or "/conduct" in path or fill or path.startswith("/prototype/copilot/") or path.endswith("/playbooks/company/read"):
        return await call_next(request)
    return JSONResponse({"detail": {"code": "local_read_only"}}, status_code=403)


REPLAY_CALL = "816ba4f7"


@app.post("/prototype/copilot/replay")
def replay(body: dict):
    """The call played again with these moments: the cards shown and what moment each reading recognised."""
    import json

    from app.services.copilot.playbook_objections import custom_entries
    from app.services.playbooks.live import live_snapshot
    from evals.copilot.export_calls import supabase
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_turns
    from evals.strategic import turns as semantic
    from evals.strategic.forma_de_trabajar import with_moments
    from evals.strategic.run import CALLS, context_for

    load_production_provider()
    moments = [m for m in body.get("moments", []) if m.get("line", "").strip()]
    call = json.loads((CALLS / f"{REPLAY_CALL}.local.json").read_text(encoding="utf-8"))
    context = context_for({**call, "playbook_version_id": None}).replace(
        "GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
    custom = custom_entries(live_snapshot(supabase(), call["company_id"], call["motion"]))
    semantic.turn_readings(call, custom)
    played = run_turns.play(call, with_moments(context, moments, [l for l in body.get("style", []) if l.strip()]), custom, run_turns.moment_schema([m["id"] for m in moments]))
    return {
        "shown": played["shown"],
        "readings": [{"t": r["start_t"], "moment": (r["output"] or {}).get("moment"), "event": r["event"]} for r in played["readings"]],
        "cost": played["cost"],
    }


# Real cold calls of Vocify to play with the playbook as it is saved (exported to backend/evals/copilot/calls/).
REAL_CALLS = {"272ac057": "Josep", "56ef086b": "Natalia", "5723ae33": "Manel"}


@app.post("/prototype/copilot/real-call")
def real_call(body: dict):
    """{"call", "motion"} → {name, turns, shown, cost}: a real call played with the live brain (turns-6b) reading the
    call type's playbook and «Cómo decide Vocify» exactly as they are saved now. About a minute and $0.01-0.02."""
    import json

    from app.services.copilot.live_brain import goal_for
    from app.services.copilot.playbook_objections import custom_entries
    from app.services.playbooks.conduct import SqlConductStore, brain_text
    from app.services.playbooks.live import live_snapshot
    from evals.copilot.export_calls import supabase
    from evals.strategic import run_turns
    from evals.strategic import turns as semantic
    from evals.strategic.forma_de_trabajar import _GOAL_LINE
    from evals.strategic.run import CALLS, context_for

    key = body.get("call", "")
    if key not in REAL_CALLS:
        return JSONResponse({"detail": {"code": "unknown_call"}}, status_code=404)
    call = json.loads((CALLS / f"{key}.local.json").read_text(encoding="utf-8"))
    motion = body.get("motion") or call["motion"]
    sb = supabase()
    context = context_for({**call, "motion": motion, "playbook_version_id": None}).replace(
        "GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
    company = brain_text(SqlConductStore(sb).get(COMPANY, motion), goal_for(motion))
    if company:
        context = _GOAL_LINE.sub(lambda _: company, context, count=1)
    custom = custom_entries(live_snapshot(sb, COMPANY, motion))
    semantic.turn_readings(call, custom)
    played = run_turns.play(call, context, custom)
    return {"name": REAL_CALLS[key], "turns": call["turns"], "shown": played["shown"], "cost": played["cost"]}


RULE_WRITER = """A sales manager is telling Vocify, the live assistant that shows a salesperson what to say during a
call, how their company does things. Turn what they wrote into ONE rule and an example conversation to test it.

- "rule": one short sentence in Spanish, in the company's voice, that Vocify can follow. A situation and what to do
  ("Si dice que ya tiene CRM, preguntar cuándo lo renueva") or something always true ("Tratar siempre de tú"). Keep
  their meaning and their words; do not add what they did not say.
- "when": the situation, in their words, written to follow «Cuando el cliente …» ("dice que ya tiene CRM", "pide que
  le mandes información"); "" when it is about the whole call (how to talk, something always true).
- "what": what Vocify suggests then, in their words, short, starting with a verb ("preguntar cuándo lo renueva",
  "tratar siempre de usted").
- "conversation": 2 to 4 turns of a cold call of this company (the playbook and the offer below), "you" is the rep and
  "them" the prospect, in Spanish, natural and short. It ends with the prospect saying the thing the rule reacts to
  (its situation), so the rep's NEXT line is where the rule applies. The rep has not done what the rule says yet and no
  one has mentioned it: the conversation stops just before. For a rule about how to talk, any ordinary moment.
- "unclear": "" when the rule is clear; otherwise one short question in Spanish asking what they mean."""
RULE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["rule", "when", "what", "conversation", "unclear"],
    "properties": {
        "rule": {"type": "string"}, "when": {"type": "string"}, "what": {"type": "string"},
        "conversation": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["who", "text"],
                                                    "properties": {"who": {"type": "string", "enum": ["you", "them"]}, "text": {"type": "string"}}}},
        "unclear": {"type": "string"},
    },
}
RULE_JUDGE = """A company gave its sales assistant a RULE. At the end of a call, the assistant suggested CARD WITH THE RULE
and, without it, CARD WITHOUT. "follows": does CARD WITH THE RULE do what the rule asks at this moment (an empty card
follows only a rule that asks to say nothing)? "same_move": do both cards make the same move (the same question,
proposal or step), even in other words? Answer JSON."""
JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["follows", "same_move"],
                "properties": {"follows": {"type": "boolean"}, "same_move": {"type": "boolean"}}}
_CONTEXT: dict[str, str] = {}


def _motion_context(motion: str) -> str:
    """The playbook and sources the live brain reads for a call type (the recorded call only gives the company)."""
    import json

    from evals.strategic.run import CALLS, context_for

    key = f"motion:{motion}"
    if key not in _CONTEXT:
        call = json.loads((CALLS / f"{REPLAY_CALL}.local.json").read_text(encoding="utf-8"))
        _CONTEXT[key] = context_for({**call, "motion": motion, "playbook_version_id": None}).replace(
            "GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
    return _CONTEXT[key]


def _rules_context() -> str:
    """The cold-call playbook and sources the live brain reads (the recorded call only gives the company and the call type)."""
    import json

    from evals.strategic.run import CALLS, context_for

    if REPLAY_CALL not in _CONTEXT:
        call = json.loads((CALLS / f"{REPLAY_CALL}.local.json").read_text(encoding="utf-8"))
        _CONTEXT[REPLAY_CALL] = context_for({**call, "playbook_version_id": None}).replace(
            "GOAL:", "USUAL GOAL FOR THIS TYPE OF CALL (a starting point, not an obligation):", 1)
    return _CONTEXT[REPLAY_CALL]


def _with_rules(context: str, rules: list[str]) -> str:
    if not rules:
        return context
    block = ("RULES OF THIS COMPANY (written by the company; they come before the goal and before your usual way of doing "
             "things; guidance on what to do and how to say it, never a source of facts):\n" + "\n".join(f"- {r}" for r in rules))
    head, sep, rest = context.partition("\n")
    return f"{head}\n{block}{sep}{rest}" if "USUAL GOAL" in head else f"{block}\n\n{context}"


@app.post("/prototype/copilot/rule")
def rule(body: dict):
    """{"text": what the manager wrote, "rules": the company's other rules} → the rule, an example conversation, and the
    card the live brain shows at its end without the rule and with it."""
    from concurrent.futures import ThreadPoolExecutor

    from evals.copilot.run import load_production_provider
    from evals.strategic import run_turns
    from evals.strategic import run_v2 as v2
    from evals.strategic.run_min import calendar

    load_production_provider()
    others = [r for r in body.get("rules", []) if r.strip()]
    context = _rules_context()
    written = v2.ask(RULE_WRITER, f"{context}\n\nWHAT THE MANAGER WROTE: «{body.get('text', '').strip()}»", "none", 600, RULE_SCHEMA,
                     "prototype-rule-writer", temperature=0.7)
    out = written["parsed"] or {}
    if not out.get("rule") or out.get("unclear"):
        return {"rule": out.get("rule", ""), "unclear": out.get("unclear") or "No se pudo escribir la regla.", "cost": written["cost"]}
    log = "\n".join(f"{'You' if t['who'] == 'you' else 'Them'}: {t['text']}" for t in out["conversation"])

    def card(rules: list[str]) -> dict:
        block = run_turns.rules_block(rules)
        user = (f"{context}\n\n{calendar(context)}\n\nLOG (\"You\" is the rep):\n{log}\n\n"
                f"{block + chr(10) * 2 if block else ''}NOW: they have just finished speaking.")
        system = run_turns.SYSTEM + run_turns.RULES_NOTE if rules else run_turns.SYSTEM
        res = v2.ask(system, user, "none", run_turns.TOKENS, run_turns.SCHEMA, "prototype-rule-card", temperature=0.0)
        parsed = res["parsed"] or {}
        say = parsed.get("line", "").strip() if parsed.get("decision") == "card" else ""
        return {"say": say, "cost": res["cost"]}

    text = body.get("text", "").strip()  # the brain reads the rule as the manager wrote it
    with ThreadPoolExecutor(max_workers=2) as pool:
        without, with_rule = pool.map(card, [others, [*others, text]])
    them = next((t["text"] for t in reversed(out["conversation"]) if t["who"] == "them"), "")
    judged = v2.ask(RULE_JUDGE, f"RULE: {text}\nTHEY JUST SAID: «{them}»\nCARD WITH THE RULE: «{with_rule['say']}»\n"
                    f"CARD WITHOUT: «{without['say']}»", "none", 80, JUDGE_SCHEMA, "prototype-rule-judge", temperature=0.0)
    verdict = judged["parsed"] or {"follows": False, "same_move": False}
    return {"rule": text, "when": out.get("when", ""), "what": out.get("what", ""), "unclear": "", "conversation": out["conversation"], "them": them, "without": without["say"], "with": with_rule["say"],
            "follows": verdict["follows"], "same_move": verdict["same_move"],
            "cost": written["cost"] + without["cost"] + with_rule["cost"] + judged["cost"]}


SAMPLE_WRITER = """You write a realistic example of a conversation of this company of the TYPE given (the playbook, offer and
ideal customer below), in Spanish (Spain), so a sales manager can see what Vocify, their live assistant, suggests.

- "buyer": a made-up prospect who fits the company's ideal customer: "name" (first name and surname), "role",
  "company" (a made-up company name and what it does, a few words), "situation" (one sentence: their team and what is
  going on, only what the call will show).
- "turns": 14 to 18 turns, "you" is the rep and "them" the buyer. Natural speech, short turns (at most 40 words),
  including short replies ("Ya.", "Vale, dime."). The rep is a normal SDR, not perfect: sometimes pitches too much or
  misses a cue, so there is room for a suggestion. Never invent product facts that are not in the sources.
- How the buyer behaves: the SCENARIO given, played naturally through the call (it does not have to be said in the
  first turn).
- End the call naturally (a goodbye)."""
SAMPLE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["buyer", "turns"],
    "properties": {
        "buyer": {"type": "object", "additionalProperties": False, "required": ["name", "role", "company", "situation"],
                  "properties": {k: {"type": "string"} for k in ("name", "role", "company", "situation")}},
        "turns": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["who", "text"],
                                             "properties": {"who": {"type": "string", "enum": ["you", "them"]}, "text": {"type": "string"}}}},
    },
}


@app.post("/prototype/copilot/sample-call")
def sample_call(body: dict):
    """{"kind": interesado|esceptico|sin_tiempo, "rules": [...], "call"?: a call this returned} → {call, shown, cost}."""
    import json
    import uuid

    from app.services.copilot.playbook_objections import custom_entries
    from app.services.playbooks.live import live_snapshot
    from evals.copilot.export_calls import supabase
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_turns
    from evals.strategic import run_v2 as v2
    from evals.strategic import turns as semantic
    from evals.strategic.run import CALLS, SECONDS_PER_WORD

    load_production_provider()
    context = _motion_context(body.get("motion") or "discovery")
    cost = 0.0
    call = body.get("call")
    if not call:
        kind = body.get("kind") or "escenario"
        scenario = body.get("scenario") or {
            "interesado": "has a real problem the product solves, asks how it works or what it costs, open to a meeting",
            "esceptico": "says they have it covered or already use a tool, pushes back, may end with a clear no",
            "sin_tiempo": "busy, short answers, asks to be sent information by email, wants to hang up soon",
        }.get(kind, "has a real problem the product solves, open to a meeting")
        written = v2.ask(SAMPLE_WRITER, f"{context}\n\nTYPE: {body.get('title') or 'Llamada en frío'}\nSCENARIO: {scenario}", "none", 2500, SAMPLE_SCHEMA, f"prototype-sample-{uuid.uuid4().hex}",
                         temperature=0.9)
        cost += written["cost"]
        out = written["parsed"] or {}
        if not out.get("turns"):
            return {"error": "no_call", "cost": cost}
        turns, t = [], 0.0
        for i, turn in enumerate(out["turns"]):
            turns.append({"id": f"t{i}", "who": turn["who"], "text": turn["text"].strip(), "t": round(t, 1)})
            t += max(0.8, len(turn["text"].split()) * SECONDS_PER_WORD) + 0.5
        call = {"id": f"sample-{uuid.uuid4().hex[:10]}", "kind": kind, "buyer": out["buyer"], "turns": turns}
    real = json.loads((CALLS / f"{REPLAY_CALL}.local.json").read_text(encoding="utf-8"))
    custom = custom_entries(live_snapshot(supabase(), real["company_id"], real["motion"]))
    semantic.turn_readings(call, custom)
    rules = [r for r in body.get("rules", []) if r.strip()]
    played = run_turns.play(call, context, custom, rules=rules)
    shown = [{"visible_t": c["visible_t"], "after_turn": c["after_turn"], "say": c["say"], "kind": c["kind"]} for c in played["shown"]]
    cost += played["cost"]
    if body.get("judge"):
        shown, judged = _judge_cards(call, shown)
        cost += judged
    return {"call": call, "rules": rules, "shown": shown, "cost": cost}


BRIEF_WRITER = """A sales manager gave Vocify, the live assistant of their reps, the material below. Explain it back the way
that manager would explain it to a new rep in one minute, so the manager sees at a glance whether Vocify understood.

- Spanish (Spain), second person plural about the company ("Vendéis…", "Si dicen que es caro, lo comparáis con…").
- "paragraphs": 3 to 6, the ones that matter most, each one idea: "topic" (2 to 4 words, Spanish sentence case: only
  the first letter capitalised, as in "Qué vendéis", "Cómo empezáis", "Si dicen que es caro") and "text" (one or two
  short sentences, at most 35 words). Only what the material says; concrete words from it; never invent a fact, a number
  or an answer. Group many objections into the two or three that matter most.
- Lines marked [Vocify] were written by Vocify to complete the material, not by the company. "by_vocify": true when
  the paragraph rests mainly on such lines. Mention them like the rest; never say who wrote them.
- When the material is empty, "paragraphs" is []."""
BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["paragraphs"],
    "properties": {
        "paragraphs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["topic", "text", "by_vocify"],
                                                  "properties": {"topic": {"type": "string"}, "text": {"type": "string"}, "by_vocify": {"type": "boolean"}}}},
    },
}


@app.post("/prototype/copilot/briefing")
def briefing(body: dict):
    """{"title": what it is for, "content": the material as text} → {paragraphs, unknown}."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    user = f"FOR: {body.get('title', '')}\n\nMATERIAL:\n{body.get('content', '').strip() or '(empty)'}"
    out = v2.ask(BRIEF_WRITER, user, "none", 1800, BRIEF_SCHEMA, "prototype-briefing", temperature=0.2)
    parsed = out["parsed"] or {"paragraphs": []}
    return {**parsed, "cost": out["cost"]}


COMPLETER = """You complete a company's sales playbook for one type of conversation so their reps are never left without
an answer. Below: what the company wrote for this conversation (MATERIAL) and what it knows about itself (COMPANY).

- "situations": up to 5 things prospects commonly say or do in this kind of conversation that the MATERIAL does not
  cover yet (do not repeat one it covers, even in other words). Each: "label" (2 to 5 words, Spanish sentence case),
  "trigger" (how a prospect says it, in Spanish, natural) and "answer" (what the rep says or does, at most 40 words,
  in the material's tone, built on the COMPANY's real product, offer and goal for this conversation).
- "answers": for each item of what to find out ("Averiguar: …") that has no good answer yet, "label" (exactly as
  written) and "good" (one sentence: what a good answer from the prospect sounds like).
- Never invent facts: no prices, clients, numbers, features or promises that are not in COMPANY or MATERIAL. When an
  answer would need a fact that is missing, the answer asks or moves to the next step instead."""
COMPLETE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["situations", "answers"],
    "properties": {
        "situations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "trigger", "answer"],
                                                  "properties": {k: {"type": "string"} for k in ("label", "trigger", "answer")}}},
        "answers": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "good"],
                                               "properties": {k: {"type": "string"} for k in ("label", "good")}}},
    },
}


@app.post("/prototype/copilot/complete")
def complete(body: dict):
    """{"title", "content": the call type's playbook as text, "company": the company notes} → what Vocify adds."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    user = f"CONVERSATION: {body.get('title', '')}\n\nMATERIAL:\n{body.get('content', '') or '(empty)'}\n\nCOMPANY:\n{body.get('company', '')}"
    out = v2.ask(COMPLETER, user, "none", 2000, COMPLETE_SCHEMA, "prototype-complete", temperature=0.2)
    return {**(out["parsed"] or {"situations": [], "answers": []}), "cost": out["cost"]}


SAMPLE_JUDGE = """A sales manager's live assistant showed these CARDS to a rep during the call below. Judge each card as that
sales manager would: is it what the rep should say or do at that moment, given what the prospect had just said and
the company's goal? "ok": true when it is good enough to use. When it is not: "why" (at most 12 words, Spanish: what
is wrong) and "rule" (one sentence in Spanish, in the company's voice, that would make the assistant get this kind of
moment right next time, general enough for other calls: "Si dicen que no tienen tiempo, proponer otro día con hora, sin
seguir explicando"). For a good card, "why" and "rule" are "". Answer one verdict per card, in order."""
JUDGE_CARDS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdicts"],
    "properties": {"verdicts": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["ok", "why", "rule"],
                                                           "properties": {"ok": {"type": "boolean"}, "why": {"type": "string"}, "rule": {"type": "string"}}}}},
}


def _judge_cards(call: dict, shown: list[dict]) -> tuple[list[dict], float]:
    from evals.strategic import run_v2 as v2

    if not shown:
        return [], 0.0
    lines = []
    cards = sorted(shown, key=lambda c: c["visible_t"])
    k = 0
    for t in call["turns"]:
        while k < len(cards) and cards[k]["visible_t"] < t["t"]:
            lines.append(f"[CARD {k + 1}] «{cards[k]['say']}»")
            k += 1
        lines.append(f"{'Rep' if t['who'] == 'you' else 'Prospect'}: {t['text']}")
    lines += [f"[CARD {i + 1}] «{c['say']}»" for i, c in enumerate(cards[k:], start=k)]
    out = v2.ask(SAMPLE_JUDGE, "\n".join(lines), "none", 900, JUDGE_CARDS_SCHEMA, "prototype-sample-judge", temperature=0.0)
    verdicts = (out["parsed"] or {}).get("verdicts", [])
    by_time = {c["visible_t"]: (verdicts[i] if i < len(verdicts) else {"ok": True, "why": "", "rule": ""}) for i, c in enumerate(cards)}
    return [{**c, **by_time[c["visible_t"]]} for c in shown], out["cost"]


_MOTION_CONTEXT: dict[str, str] = {}


@app.post("/prototype/copilot/simulate")
def simulate(body: dict):
    """{"motion", "text": what a client says} → the card the live brain shows to the rep right after (the published or
    drafted playbook in the database, not edits made on the page)."""
    import json

    from evals.copilot.run import load_production_provider
    from evals.strategic import run_turns
    from evals.strategic import run_v2 as v2
    from evals.strategic.run import CALLS, context_for
    from evals.strategic.run_min import calendar

    load_production_provider()
    motion = body.get("motion") or "discovery"
    context = _motion_context(motion)
    them = body.get("text", "").strip()
    rules = [r for r in body.get("rules", []) if r.strip()]
    block = run_turns.rules_block(rules)
    so_far = body.get("turns") or []
    log = "\n".join(f"{'You' if t.get('who') == 'you' else 'Them'}: {t.get('text', '')}" for t in so_far[-14:]) if so_far else \
        f"You: Hola, soy del equipo comercial, ¿tienes un minuto?\nThem: {them}"
    user = (f"{context}\n\n{calendar(context)}\n\nLOG (\"You\" is the rep):\n{log}\n\n"
            f"{block + chr(10) * 2 if block else ''}NOW: they have just finished speaking.")
    res = v2.ask(run_turns.SYSTEM + run_turns.RULES_NOTE if rules else run_turns.SYSTEM, user, "none", run_turns.TOKENS, run_turns.SCHEMA, f"prototype-simulate-{motion}", temperature=0.0)
    parsed = res["parsed"] or {}
    say = parsed.get("line", "").strip() if parsed.get("decision") == "card" else ""
    return {"say": say, "source": parsed.get("source", ""), "cost": res["cost"]}


ADVISOR = """You are Vocify's playbook advisor. A sales manager is looking at the playbook of one type of conversation
(MATERIAL, with the company's notes in COMPANY and the GOAL of the conversation) and talks to you.

- When they ask a question or for your judgement ("¿está bien la respuesta al precio?", "¿qué le falta para conseguir
  más reuniones?"), answer in "answer": Spanish, at most 80 words, concrete, judged against the GOAL and what works in
  B2B sales, naming the items you mean. No preamble, no lists longer than 3.
- When they ask to add, change or remove something, write in "change" one precise instruction for the playbook editor
  in Spanish ("Añade la objeción «Lo tengo que hablar con mi socio» con la respuesta: …"; "Cambia la respuesta a «Es
  caro» por: …"), keeping their words, and say in "answer" in one sentence what you will change. Otherwise "change" is "".
- Never invent facts about the product, prices or clients that are not in COMPANY or MATERIAL.
- Write only in Spanish, as a colleague would: say «el objetivo», never "GOAL", "MATERIAL" or other labels of this brief."""
ADVISOR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer", "change"],
                  "properties": {"answer": {"type": "string"}, "change": {"type": "string"}}}


@app.post("/prototype/copilot/ask")
def ask_advisor(body: dict):
    """{"title", "goal", "content", "company", "history": [{who, text}], "text"} → {answer, change}."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    history = "\n".join(f"{'Manager' if h.get('who') == 'user' else 'You'}: {h.get('text', '')}" for h in body.get("history", [])[-8:])
    user = (f"CONVERSATION: {body.get('title', '')}\nGOAL: {body.get('goal', '')}\n\nMATERIAL:\n{body.get('content', '') or '(empty)'}\n\n"
            f"COMPANY:\n{body.get('company', '')}\n\nCHAT SO FAR:\n{history or '(none)'}\n\nMANAGER NOW: {body.get('text', '')}")
    out = v2.ask(ADVISOR, user, "none", 600, ADVISOR_SCHEMA, "prototype-advisor", temperature=0.3)
    return {**(out["parsed"] or {"answer": "No te he entendido, ¿me lo dices de otra forma?", "change": ""}), "cost": out["cost"]}


ROUTER = """A sales manager pasted material into Vocify. Split it by the company's TYPES of conversation: for each type, copy
the parts of the material that are about that type of conversation (verbatim, nothing added). A part about one type
goes only there; a part that says it is for every conversation goes to each; general facts about the company, its
product, prices or customers go to "company". A type the material says nothing about gets "". Answer JSON."""


@app.post("/prototype/copilot/route")
def route(body: dict):
    """{"text", "types": [{key, label}]} → {"parts": {key: text}, "company": text}: which part of an import goes where."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    types = body.get("types", [])
    schema = {"type": "object", "additionalProperties": False, "required": ["company", *[t["key"] for t in types]],
              "properties": {"company": {"type": "string"}, **{t["key"]: {"type": "string"} for t in types}}}
    listing = "\n".join(f"- {t['key']}: {t['label']}" for t in types)
    out = v2.ask(ROUTER, f"TYPES:\n{listing}\n\nMATERIAL:\n{body.get('text', '')}", "none", 4000, schema, "prototype-route", temperature=0.0)
    parsed = out["parsed"] or {}
    return {"parts": {t["key"]: parsed.get(t["key"], "") for t in types}, "company": parsed.get("company", ""), "cost": out["cost"]}


STRUCTURER = """You organise a company's playbook for one type of conversation into Vocify's editor, so a sales manager sees
at a glance what the conversation is for and how their live assistant will help. Spanish (Spain), short, concrete, in
the company's voice. Use only what the MATERIAL and COMPANY say; never invent facts, numbers, clients or features.

- "goal": the main goal in at most 12 words, as how the assistant recognises the conversation is going well (not the
  pitch): "Conseguir una demo con alguien que tenga una necesidad relevante".
- "alternatives": 2 or 3 other endings that also count, each "label" (2 to 4 words, starting with a capital letter) and "when" (the signal that
  justifies it, at most 14 words): {"label": "Descalificación", "when": "no aparece necesidad tras explorarla
  brevemente"}.
- "orientation": ONE paragraph (at most 60 words) on how Vocify's cards should help in THIS kind of conversation: when
  to go deeper, when to propose the next step, when to stop insisting, when to stay quiet because the rep is doing well.
  A judgement, never a checklist of questions (that goes in "info") and never a script (that goes in the steps). Do not
  turn "try another angle" into an automatism: only when a new signal justifies it.
- "steps": for every step Sn: "n" and "when": when it makes sense, as the situation in which it helps, at most 14 words,
  starting with a capital letter («Cuando el interlocutor necesita entender quién llama»), never its place in a sequence
  («tras la apertura») and never an order.
- "info": for every item Qn: "n", "evidence" (what counts as a real answer, at most 20 words), "not_evidence" (what does
  not count, at most 14 words), "essential" (true only when without it the main goal is not met; a real need or reason
  to continue comes before team size, tools or process).
- "themes": 4 to 7 themes that group ALL the answers Rn by what the prospect is really saying: "name" (2 to 4 words,
  sentence case) and "answers" (their n). Every Rn in exactly one theme."""
STRUCTURE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["goal", "alternatives", "orientation", "steps", "info", "themes"],
    "properties": {
        "goal": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "when"],
                                                    "properties": {"label": {"type": "string"}, "when": {"type": "string"}}}},
        "orientation": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["n", "when"],
                                             "properties": {"n": {"type": "integer"}, "when": {"type": "string"}}}},
        "info": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["n", "evidence", "not_evidence", "essential"],
                                            "properties": {"n": {"type": "integer"}, "evidence": {"type": "string"}, "not_evidence": {"type": "string"}, "essential": {"type": "boolean"}}}},
        "themes": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["name", "answers"],
                                              "properties": {"name": {"type": "string"}, "answers": {"type": "array", "items": {"type": "integer"}}}}},
    },
}


@app.post("/prototype/copilot/structure")
def structure(body: dict):
    """{"title", "goal", "content" (S/Q/R numbered), "company", "conduct"} → the four areas."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    user = (f"CONVERSATION: {body.get('title', '')}\nGOAL: {body.get('goal', '')}\n\nMATERIAL:\n{body.get('content', '')}\n\n"
            f"CONDUCT THE COMPANY WROTE:\n{body.get('conduct', '') or '(none)'}\n\nCOMPANY:\n{body.get('company', '')}")
    out = v2.ask(STRUCTURER, user, "none", 8000, STRUCTURE_SCHEMA, "prototype-structure", temperature=0.2)
    return {**(out["parsed"] or {}), "error": out.get("error"), "completion_tokens": out.get("completion_tokens"), "cost": out["cost"]}


EDIT_ROUTER = """A sales manager asks Vocify's playbook editor for a change, in their words. Decide where it goes:
- "criteria": how Vocify should help or behave in this conversation (insist or not, go deeper, change course, when to
  stop). Return the whole CRITERIA with the change made (same shape: title and text, a judgement and never a script),
  changing nothing else; a new criterion only when no existing one is about it.
- "playbook": a step of the conversation, something to find out, or an answer to what prospects say. Return "criteria"
  exactly as given.
"summary": one short sentence in Spanish saying what will change and where."""
CRITERIA_SCHEMA = {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "text"],
                                              "properties": {"title": {"type": "string"}, "text": {"type": "string"}}}}


@app.post("/prototype/copilot/edit")
def edit(body: dict):
    """{"request", "criteria"} → {"area": "criteria"|"playbook", "criteria", "summary"}."""
    import json

    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    schema = {"type": "object", "additionalProperties": False, "required": ["area", "criteria", "summary"],
              "properties": {"area": {"type": "string", "enum": ["criteria", "playbook"]}, "criteria": CRITERIA_SCHEMA, "summary": {"type": "string"}}}
    user = f"CRITERIA:\n{json.dumps(body.get('criteria', []), ensure_ascii=False)}\n\nREQUEST: {body.get('request', '')}"
    out = v2.ask(EDIT_ROUTER, user, "none", 1500, schema, "prototype-edit", temperature=0.0)
    return {**(out["parsed"] or {"area": "playbook", "criteria": body.get("criteria", []), "summary": ""}), "cost": out["cost"]}


IMPROVER = """A sales manager wants one CRITERION of their live assistant (how Vocify helps in this conversation) to behave
as they describe, but does not know how to word it. Rewrite it: "title" (2 to 5 words, sentence case) and "text" (at
most 35 words), Spanish, a judgement about when to push, go deeper, change course or stop, never a checklist or a
script, keeping what still applies. "summary": one short sentence saying what changed."""


@app.post("/prototype/copilot/improve")
def improve(body: dict):
    """{"criterion": {title, text}, "request", "goal"} → {title, text, summary}: a proposal, nothing applied."""
    import json

    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    schema = {"type": "object", "additionalProperties": False, "required": ["title", "text", "summary"],
              "properties": {"title": {"type": "string"}, "text": {"type": "string"}, "summary": {"type": "string"}}}
    user = f"GOAL: {body.get('goal', '')}\nCRITERION: {json.dumps(body.get('criterion', {}), ensure_ascii=False)}\nWHAT THE MANAGER WANTS: {body.get('request', '')}"
    out = v2.ask(IMPROVER, user, "none", 400, schema, "prototype-improve", temperature=0.2)
    return {**(out["parsed"] or {}), "cost": out["cost"]}


EXAMPLES_WRITER = """A sales manager wrote a CRITERION for Vocify, the live assistant of their reps, in this kind of conversation.
Write two short situations that test it, in Spanish (Spain), each one thing a prospect says right now in this company's
calls: "a" where the criterion means the assistant should hold back (stay silent or not push), and "b" where it means
the assistant should act. Each: "label" (3 to 6 words, sentence case: what is happening) and "them" (what the prospect
says, natural, at most 30 words)."""
EXAMPLES_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["a", "b"],
                   "properties": {k: {"type": "object", "additionalProperties": False, "required": ["label", "them"],
                                      "properties": {"label": {"type": "string"}, "them": {"type": "string"}}} for k in ("a", "b")}}


@app.post("/prototype/copilot/examples")
def examples(body: dict):
    """{"motion", "title", "criterion", "rules"} → two situations and what the live brain does in each with the rules."""
    from concurrent.futures import ThreadPoolExecutor

    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    out = v2.ask(EXAMPLES_WRITER, f"CONVERSATION: {body.get('title', '')}\nCRITERION: {body.get('criterion', '')}", "none", 500,
                 EXAMPLES_SCHEMA, "prototype-examples", temperature=0.7)
    pair = out["parsed"] or {}
    if not pair.get("a") or not pair.get("b"):
        return {"situations": [], "cost": out["cost"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        cards = list(pool.map(lambda s: simulate({"motion": body.get("motion"), "text": s["them"], "rules": body.get("rules", [])}), [pair["a"], pair["b"]]))
    return {"situations": [{**pair[k], "say": c["say"]} for k, c in zip(("a", "b"), cards)], "cost": out["cost"] + sum(c["cost"] for c in cards)}


TEACHER = """A sales manager is reviewing what Vocify, their reps' live assistant, suggested at one MOMENT of a conversation,
and tells you how it should have acted. Turn that into a general criterion for this TYPE of conversation, so the manager
never has to write rules.

- "interpretation": what you understood, in Spanish, as a general preference (not about this prospect), one or two
  sentences starting «Entiendo:». E.g. «Entiendo: cuando el cliente ya tiene resuelta una necesidad, prefieres no
  intentar demostrarle que sigue teniendo el problema.»
- "criteria": the whole list of CURRENT CRITERIA with this preference built in: change the criterion it belongs to,
  or add one (title 2 to 5 words, sentence case; text at most 35 words, a judgement, never a script or a checklist).
  Change nothing that does not need to change.
- "summary": one short sentence: what changes in the criteria.
- "conflict": "" or one sentence when the preference contradicts a current criterion, and how the new list resolves it.
When the manager says the suggestion was good, "criteria" is the current list unchanged and "interpretation" says what
you will keep doing."""
TEACH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["interpretation", "criteria", "summary", "conflict"],
                "properties": {"interpretation": {"type": "string"}, "summary": {"type": "string"}, "conflict": {"type": "string"},
                               "criteria": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "text"],
                                                                       "properties": {"title": {"type": "string"}, "text": {"type": "string"}}}}}}


@app.post("/prototype/copilot/teach")
def teach(body: dict):
    """{"title", "goal", "criteria", "them", "say", "feedback": good|silence|different, "text"} → a proposal, nothing applied."""
    import json

    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    said = f"«{body.get('say')}»" if body.get("say") else "(nothing: it stayed silent)"
    wanted = {"good": "It was right: keep doing this.", "silence": "It should have stayed silent here.",
              "different": "It should have done something different."}.get(body.get("feedback", ""), "")
    user = (f"TYPE: {body.get('title', '')}\nGOAL: {body.get('goal', '')}\nCURRENT CRITERIA:\n{json.dumps(body.get('criteria', []), ensure_ascii=False)}\n\n"
            f"MOMENT — the prospect said: «{body.get('them', '')}»\nVocify suggested: {said}\n\nTHE MANAGER: {wanted} {body.get('text', '')}")
    out = v2.ask(TEACHER, user, "none", 1500, TEACH_SCHEMA, "prototype-teach", temperature=0.2)
    return {**(out["parsed"] or {}), "cost": out["cost"]}


ORIENTER = """A sales manager adjusts the ORIENTATION of Vocify, their reps' live assistant, for one type of conversation: one
paragraph on how its cards should help. Rewrite the paragraph with what they ask, in Spanish, at most 70 words, still ONE
paragraph that reads as a judgement (when to go deeper, propose the next step, stop insisting, stay quiet), never a list
of rules or cases: fold the request into a general way of acting, keep what still applies. When the request comes from a
MOMENT of a call, generalise it beyond that prospect. "summary": one short sentence in Spanish on what changes. When the
paragraph already says it, return it unchanged and say so in "summary"."""


@app.post("/prototype/copilot/orient")
def orient(body: dict):
    """{"orientation", "goal", "request", "moment"?: {them, say, feedback}} → {orientation, summary}: a proposal."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    moment = body.get("moment") or {}
    told = ""
    if moment:
        said = f"«{moment.get('say')}»" if moment.get("say") else "(nothing)"
        told = f"\nMOMENT — the prospect said «{moment.get('them', '')}», Vocify suggested {said}; the manager: {moment.get('feedback', '')}"
    schema = {"type": "object", "additionalProperties": False, "required": ["orientation", "summary"],
              "properties": {"orientation": {"type": "string"}, "summary": {"type": "string"}}}
    user = f"GOAL: {body.get('goal', '')}\nORIENTATION: {body.get('orientation', '')}{told}\nTHE MANAGER ASKS: {body.get('request', '')}"
    out = v2.ask(ORIENTER, user, "none", 500, schema, "prototype-orient", temperature=0.2)
    return {**(out["parsed"] or {}), "cost": out["cost"]}



CHAT = """You are Vocify, talking with a sales manager about the playbook of ONE type of conversation: its GOAL (and the
other endings that count), the ORIENTATION (one paragraph on how Vocify's cards help in these calls) and the PLAYBOOK
(S steps of the conversation guide, Q what to find out, R objections and answers), with the company's notes in COMPANY.

- A question or a request for your judgement ("¿qué le falta?", "¿por qué insistiría aquí?", "¿está bien la respuesta
  al precio?"): answer in "answer", Spanish, at most 70 words, concrete, judged against the GOAL, naming the items you
  mean (by their name, never by their S/Q/R number). "change" is "none".
- A request to change how Vocify helps (more or less insistent, go deeper, interrupt less, stop earlier…): "change" is
  "orientation" and "text" is the whole paragraph rewritten, at most 70 words, still ONE paragraph that reads as a
  judgement, never a list of rules or cases, keeping what still applies.
- A request to change what we want to achieve: "change" is "goal" and "text" the new goal, one short line.
- A request to add, change or remove something of the playbook (a step, a question, an objection and its answer):
  "change" is "playbook" and "text" one precise instruction for the playbook editor in Spanish, keeping their words.
- "answer" always says, in one short sentence when there is a change, what you propose. Never invent facts about the
  product, prices or clients that are not in COMPANY or the PLAYBOOK. Write as a colleague, without labels of this brief."""
CHAT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer", "change", "text"],
               "properties": {"answer": {"type": "string"}, "change": {"type": "string", "enum": ["none", "orientation", "goal", "playbook"]},
                              "text": {"type": "string"}}}


@app.post("/prototype/copilot/chat")
def chat(body: dict):
    """{"title", "goal", "alternatives", "orientation", "content", "company", "history": [{who, text}], "text"}
    → {answer, change, text}: an answer, or a change Vocify proposes (the page shows it before applying it)."""
    from evals.copilot.run import load_production_provider
    from evals.strategic import run_v2 as v2

    load_production_provider()
    history = "\n".join(f"{'Manager' if h.get('who') == 'user' else 'You'}: {h.get('text', '')}" for h in body.get("history", [])[-8:])
    user = (f"CONVERSATION: {body.get('title', '')}\nGOAL: {body.get('goal', '')}\nALSO GOOD: {body.get('alternatives', '')}\n"
            f"ORIENTATION: {body.get('orientation', '')}\n\nPLAYBOOK:\n{body.get('content', '') or '(empty)'}\n\n"
            f"COMPANY:\n{body.get('company', '')}\n\nCHAT SO FAR:\n{history or '(none)'}\n\nMANAGER NOW: {body.get('text', '')}")
    out = v2.ask(CHAT, user, "none", 700, CHAT_SCHEMA, "prototype-chat", temperature=0.3)
    return {**(out["parsed"] or {"answer": "No te he entendido, ¿me lo dices de otra forma?", "change": "none", "text": ""}), "cost": out["cost"]}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8888, log_level="warning")
