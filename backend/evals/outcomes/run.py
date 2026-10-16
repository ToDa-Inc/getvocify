"""Feasibility check of the success rate: can we tell, from stored data alone, whether a live-help suggestion was used
and whether it settled the objection or the doubt?

    cd backend && python -m evals.outcomes.run --email rep@company.com --limit 20 --out sheet.csv
    # label label_used / label_resolved by hand in sheet.csv, then:
    python -m evals.outcomes.run --score sheet.csv

The first command READS the live-help log and the company's finished calls (whatever SUPABASE_URL points at, with
backend/.env: production) and writes nothing to any database. It judges only cards that are at least MIN_AGE_HOURS old and
whose call already has its post-call reading, exactly the rule the later batch uses. The second command compares our
verdicts with the labels: SIGUE when they agree at least 80% of the time and at most 30% are unknown, DETENER otherwise.
Labels: label_used = used | adapted | not_used | unknown, label_resolved = resolved | not_resolved | unknown.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

COLUMNS = [
    "event_id", "motion", "client_text", "suggestion", "rep_text", "used", "resolved", "resolved_by", "label_used", "label_resolved",
]


def score(path: str) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.services.playbooks.outcomes import score_labels

    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = score_labels(rows)
    print(f"etiquetadas: {result['n']}")
    if result["n"]:
        print(f"acuerdo: {result['agreement']:.0%}   no se sabe: {result['unknown_rate']:.0%}")
    print(f"decisión: {result['decision']}")
    return 0 if result["decision"] == "SIGUE" else 1


def build(email: str):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from supabase import create_client

    from app.services.company import CompanyService

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    user = next((u for u in sb.auth.admin.list_users(per_page=1000) if (u.email or "").lower() == email.lower()), None)
    if user is None:
        sys.exit(f"no user {email}")
    return sb, CompanyService(sb).require_membership(user.id).company_id


async def sheet(email: str, days: int, limit: int, out: str) -> None:
    sb, company_id = build(email)
    from app.services.playbooks.gaps import recent_suggest_events
    from app.services.playbooks.outcomes import outcome_for_event, ready_for_judging

    events = [e for e in recent_suggest_events(sb, company_id, days=days, limit=1000) if e.get("is_objection") and e.get("capture_id")]
    rows: list[dict] = []
    for event in events:
        if len(rows) >= limit:
            break
        memo = (sb.table("memos").select("id,transcript,extraction").eq("id", event["capture_id"]).limit(1).execute().data or [None])[0]
        if not ready_for_judging(event, memo):
            continue
        verdict = await outcome_for_event(event, memo)
        rows.append({
            "event_id": verdict["event_id"], "motion": verdict["sales_motion_key"], "client_text": verdict["client_text"],
            "suggestion": verdict["suggestion_text"], "rep_text": verdict["rep_text"] or "", "used": verdict["used"],
            "resolved": verdict["resolved"], "resolved_by": verdict["resolved_by"], "label_used": "", "label_resolved": "",
        })
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} sugerencias en {out}. Etiqueta label_used y label_resolved y ejecuta --score {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", help="a user of the company to read")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default="sheet.csv")
    parser.add_argument("--score", metavar="SHEET", help="compare our verdicts with the labels of a sheet")
    args = parser.parse_args()
    if args.score:
        return score(args.score)
    if not args.email:
        parser.error("--email is required (or --score SHEET)")
    asyncio.run(sheet(args.email, args.days, args.limit, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
