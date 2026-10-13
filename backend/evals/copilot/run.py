"""Simulate a live call against the real turn check and live help, and check they follow the playbook.

    cd backend && python -m evals.copilot.run --email rep@company.com
    python -m evals.copilot.run --email rep@company.com --only discovery-objections-es --no-turn

Real: the /copilot/turn and /copilot/suggest endpoints (their router, classifier, prompt and model, which
use OPENROUTER_API_KEY), asked in the order the Mac app asks them, as the rep, with the rep's published
playbook read from the database. Nothing is written: neither endpoint writes. Read-only against whatever
SUPABASE_URL points at, so with backend/.env that is production.

Per prospect turn it checks what the rep would see: no card for small talk, the right card for an
objection (a fixed kind, or one of the playbook's own entries by its id), and that the answer follows the
approved entry (source_id), is not empty, and does not repeat the filler line the rep is already saying.
`--no-turn` skips the classifier, as the app does when it can't be reached. Exit 1 when a hard check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

CASES = Path(__file__).with_name("cases.json")
SUGGEST_LATE_MS = 5000  # the Mac app drops an answer slower than this and keeps only the filler line
# src/lib/live-assist.ts BRIDGES (Spanish): the filler line shown, and said, while the answer is written.
FILLERS = {
    "price": "Es normal mirarlo con lupa…",
    "timing": "Tiene sentido, el momento importa…",
    "authority": "Claro, que lo vea quien decide…",
    "competitor": "Bien que ya tengáis algo…",
    "status_quo": "Si hoy os funciona, tiene sentido…",
    "trust": "Normal querer verlo antes…",
    "question": "Mira…",
    "other": "Te entiendo…",
    "custom": "Te entiendo…",
}


def sse_events(text: str) -> list[dict]:
    return [json.loads(block[6:]) for block in text.split("\n\n") if block.startswith("data: ")]


def expected_entry(expect: str) -> str | None:
    """The playbook entry id suffix an expectation names ('custom:x' -> entries ending 'x')."""
    return expect.split(":", 1)[1] if expect.startswith("custom:") else None


def check_turn(expect: str, reading: dict | None, source_id: str | None, say: str, filler: str) -> list[str]:
    """Empty list = pass. Each string is one reason it did not."""
    seen = (reading or {}).get("objection")
    entry = (reading or {}).get("entry_id") or ""
    if expect == "none":
        return [] if seen in (None, "none") else [f"expected no card, got {seen}"]
    fails: list[str] = []
    wanted = expected_entry(expect)
    if wanted:
        if seen != "custom" or not entry.endswith(wanted):
            fails.append(f"expected the playbook entry …{wanted}, the turn check said {entry or seen}")
        if not (source_id or "").endswith(wanted):
            fails.append(f"answer did not follow …{wanted} (source_id {source_id})")
    else:
        if seen != expect:
            fails.append(f"expected a {expect} card, got {seen}")
        if source_id != f"objection:{expect}":
            fails.append(f"answer did not follow objection:{expect} (source_id {source_id})")
    if not say:
        fails.append("empty answer")
    head = filler.rstrip("….").strip().lower()
    if say and head and len(head) > 3 and say.lower().lstrip("¿¡ ").startswith(head):
        fails.append(f"answer repeats the filler line «{filler}»")
    return fails


def build_client(email: str):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from supabase import create_client

    from app.api import copilot as copilot_api
    from app.deps import get_membership, get_supabase, get_user_id
    from app.services.company import CompanyService

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    user = next((u for u in sb.auth.admin.list_users(per_page=1000) if (u.email or "").lower() == email.lower()), None)
    if user is None:
        sys.exit(f"no user {email}")
    membership = CompanyService(sb).require_membership(user.id)
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_user_id] = lambda: user.id
    app.dependency_overrides[get_membership] = lambda: membership
    app.dependency_overrides[get_supabase] = lambda: sb
    return TestClient(app)


def run_case(client, case: dict, use_turn: bool) -> list[dict]:
    rows, lines, shown = [], [], []
    for turn in case["turns"]:
        lines.append(f"{turn['speaker']}: {turn['text']}")
        expect = turn.get("expect")
        if turn["speaker"] != "Them" or expect is None:
            continue
        window = "\n".join(lines)
        reading, turn_ms = None, 0
        if use_turn:
            t = time.perf_counter()
            reading = client.post("/api/v1/copilot/turn", json={
                "transcript_window": window, "latest_turn": turn["text"], "sales_motion_key": case["motion"],
            }).json()
            turn_ms = int((time.perf_counter() - t) * 1000)
        row = {"text": turn["text"], "expect": expect, "soft": bool(turn.get("soft")), "reading": reading,
               "turn_ms": turn_ms, "say": "", "source_id": None, "suggest_ms": 0, "filler": ""}
        if use_turn and (reading or {}).get("objection") in (None, "none"):
            row["fails"] = check_turn(expect, reading, None, "", "") if expect == "none" else check_turn(expect, reading, None, "x", "")
            rows.append(row)
            continue
        kind = (reading or {}).get("objection")
        body = {
            "transcript_window": window, "latest_turn": turn["text"], "call_mode": case["call_mode"],
            "speaker_role": "prospect", "sales_motion_key": case["motion"],
        }
        if kind:
            row["filler"] = FILLERS.get(kind, "")
            body.update(objection_type=kind, filler=row["filler"])
            if reading.get("entry_id"):
                body["entry_id"] = reading["entry_id"]
        if shown:
            body["previous_answers"] = shown[-6:]
        t = time.perf_counter()
        events = sse_events(client.post("/api/v1/copilot/suggest", json=body).text)
        row["suggest_ms"] = int((time.perf_counter() - t) * 1000)
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        suggestion = (result or {}).get("suggestion") or {}
        row["say"], row["source_id"] = suggestion.get("say_this") or "", suggestion.get("source_id")
        if not use_turn:
            # No classifier: the answer model decides; "no card" is an answer that is not an objection.
            card = bool(suggestion.get("is_objection") and row["say"])
            reading = {"objection": (suggestion.get("objection_type") or "other") if card else "none"}
            if card and (row["source_id"] or "").startswith("objection:custom:"):
                reading = {"objection": "custom", "entry_id": row["source_id"]}
            row["reading"] = reading
        if row["say"]:
            shown.append(row["say"])
        if expect == "none":
            row["fails"] = [] if reading["objection"] == "none" else [f"expected no card, got {reading['objection']}"]
        else:
            row["fails"] = check_turn(expect, reading, row["source_id"], row["say"], row["filler"])
        if row["suggest_ms"] > SUGGEST_LATE_MS:
            row["fails"].append(f"answer took {row['suggest_ms']} ms; the app drops it after {SUGGEST_LATE_MS}")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", default=os.environ.get("EVAL_USER_EMAIL"), help="the rep whose playbook is used")
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--no-turn", action="store_true", help="skip the turn check")
    args = parser.parse_args()
    if not args.email:
        sys.exit("pass --email (or set EVAL_USER_EMAIL): the rep whose published playbook the call is run against")
    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8")) if not args.only or c["id"] in args.only.split(",")]
    client = build_client(args.email)
    hard = soft = total = 0
    for case in cases:
        print(f"\n== {case['id']} ({case['motion']}, {case['call_mode']}) ==")
        for row in run_case(client, case, use_turn=not args.no_turn):
            total += 1
            failed = bool(row["fails"])
            hard += failed and not row["soft"]
            soft += failed and row["soft"]
            mark = ("SOFT" if row["soft"] else "FAIL") if failed else "ok  "
            reading = row["reading"] or {}
            print(f"[{mark}] «{row['text'][:70]}»")
            print(f"        expected {row['expect']} | turn {reading.get('entry_id') or reading.get('objection')} "
                  f"({row['turn_ms']} ms) | answer {row['suggest_ms']} ms | {row['source_id']}")
            if row["say"]:
                print(f"        {row['filler']} {row['say']}".rstrip())
            for reason in row["fails"]:
                print(f"        ✗ {reason}")
    print(f"\n{total - hard - soft}/{total} turns ok, {hard} failed, {soft} soft")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
