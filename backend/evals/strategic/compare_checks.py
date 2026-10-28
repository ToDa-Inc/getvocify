"""The same saved candidate cards through the checks of several versions: what each version lets through, without the
model writing different cards.

    cd backend && .venv/bin/python -m evals.strategic.compare_checks --runs RUN.json,... --verdicts V.json,... \
        --version 3.1=PATH --version 3.2=PATH --version 3.3=PATH

A candidate is a card the gate approved on all five questions (its saved gate answer is reused, not asked again). Each
version then applies its own later checks: the fact check (3.1: answers only; 3.2 on: every card, with the conversation),
the same-objective dedupe (3.1/3.2: words said after the earlier card; 3.3 on: the state check), the same answer still
on screen, the end of the call and the other side's goodbye. Each version is run with the checks its file has. The history is the run's own cards shown before it. The fact
and state checks are model calls (about 0.3 s each, a fraction of a cent).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.strategic.run import CALLS, ends, finished_by  # noqa: E402

READY_S = 1.3  # a dropped candidate keeps when it was born; it was checked about one reading later


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(f"brain_{name.replace('.', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def approved(gate: dict | None) -> bool:
    return bool(gate) and gate["correct"] and gate["fits_playbook"] and gate["adds"] and gate["timing"] == "now" and gate["worth_interrupting"]


def candidates(run_file: str, verdict_file: str | None) -> list[dict]:
    verdict = {v["id"]: v for v in json.loads(Path(verdict_file).read_text(encoding="utf-8"))["cards"]} if verdict_file else {}
    out = []
    for p in json.loads(Path(run_file).read_text(encoding="utf-8"))["played"]:
        shown = sorted(p["shown"], key=lambda s: s["visible_t"])
        for k, s in enumerate(shown, 1):
            v = verdict.get(f"{p['id'].replace('-real', '')}-T{k}")
            out.append({"call": p["id"], "at": s["visible_t"], "card": {"act": s["kind"], "help": s["how"], "source": s.get("source") or "",
                        "source_quote": s.get("source_quote", ""), "say": s["say"], "born_t": s["born_t"], "objective": s.get("objective", "")},
                        "gate": s.get("gate"), "history": shown[:k - 1], "run": run_file, "verdict": v})
        for d in p["dropped"]:
            gate = (d.get("gates") or [None])[-1]
            if approved(gate):
                at = d["born_t"] + READY_S
                out.append({"call": p["id"], "at": at, "card": {k: d.get(k) for k in ("act", "help", "source", "source_quote", "say", "born_t", "objective")},
                            "gate": gate, "history": [s for s in shown if s["visible_t"] < at], "run": run_file, "verdict": None,
                            "was": d["why"]})
    return out


def decide(version: str, b, c: dict, turns: list[dict], sources: str) -> str:
    """What version `version` (module `b`) does with candidate `c` after its gate approved it."""
    end = ends(turns)
    card, gate, shown, at = dict(c["card"]), c["gate"], c["history"], c["at"]
    card["authorized"] = b.authorized_text(sources, card) if hasattr(b, "authorized_text") else ""
    done = finished_by(end, at)
    if not hasattr(b, "conversation_lines"):  # 3.1: answers only, with the seller's last words
        if card["act"] == "answer":
            said = " ".join(" ".join(t["text"].split()) for t in turns[max(0, done - 4):done] if t["who"] == "you")
            facts = b.fact_check(card, "compare-31", " ".join(said.split()[-60:]))["parsed"] or {"unsupported": True}
            if facts["unsupported"]:
                return "dato"
    else:
        conv = (b.conversation_lines(turns, end, at, n=b.FACT_TURNS, chars=b.FACT_CHARS) if hasattr(b, "FACT_TURNS")
                else b.conversation_lines(turns, end, at))
        facts = b.fact_check(card, "compare-32", conv)["parsed"] or {"unsupported": True}
        if facts["unsupported"]:
            return "dato"
    if hasattr(b, "closing_check"):
        closing = b.closing_check(b.conversation_lines(turns, end, at, n=b.CLOSING_TURNS), "compare-closing")["parsed"]
        if b.closing_confirmed(closing, turns, end, at):
            return "cierre"
    mine = " ".join((gate.get("same_objective_as") or "").lower().split())
    earlier = [s for s in shown if mine and SequenceMatcher(None, mine, (s.get("objective") or "").lower()).ratio() >= b.SAME_OBJECTIVE]
    if earlier:
        last = earlier[-1]
        if hasattr(b, "state_check"):
            state = b.state_check(last.get("objective") or mine, last["say"], b.conversation_lines(turns, end, at, since=last["visible_t"]), "compare-33")
            st = state["parsed"] or {"changed": False, "evidence": ""}
            if not st["changed"] or not b.said_after(st["evidence"], turns, done, end, last["visible_t"]):
                return "mismo objetivo"
        elif not b.said_after(gate.get("relevant_change") or "", turns, done, end, last["visible_t"]):
            return "mismo objetivo"
    if hasattr(b, "answer_on_screen"):
        if b.answer_on_screen(card, gate.get("same_objective_as") or "", shown):
            return "respuesta en pantalla"
        if b.call_over(at, end[-1]):
            return "llamada terminada"
    if hasattr(b, "after_goodbye") and b.after_goodbye(turns, end, at):
        return "tras despedida"
    return "sale"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--verdicts", default="")
    parser.add_argument("--version", action="append", required=True, help="NAME=path to that version's run_v2.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from evals.copilot.run import load_production_provider

    load_production_provider()
    from evals.strategic.run import context_for

    versions = dict(v.split("=", 1) for v in args.version)
    modules = {name: load(name, path) for name, path in versions.items()}
    runs, verdicts = args.runs.split(","), (args.verdicts.split(",") if args.verdicts else [None] * len(args.runs.split(",")))
    cands = [c for r, v in zip(runs, verdicts) for c in candidates(r, v)]
    calls = {c["call"] for c in cands}
    turns = {cid: json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8"))["turns"] for cid in calls}
    sources = {cid: context_for({**json.loads((CALLS / f"{cid}.local.json").read_text(encoding="utf-8")), "playbook_version_id": None}) for cid in calls}

    def row(c):
        return {**{k: c[k] for k in ("call", "at", "run", "verdict")}, "say": c["card"]["say"], "act": c["card"]["act"], "was": c.get("was"),
                "decisions": {name: decide(name, m, c, turns[c["call"]], sources[c["call"]]) for name, m in modules.items()}}

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(row, cands))
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for name in modules:
        print(f"{name}: {sum(r['decisions'][name] == 'sale' for r in rows)} of {len(rows)} candidates shown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
