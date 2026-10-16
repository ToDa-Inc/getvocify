"""Judge the live-help cards of finished calls in bulk: the same batch the "Actualizar" button of the improvement screen
runs, for as many batches as asked, apart from the post-call process (nothing here runs when a call ends).

Usage (from backend/):
  .venv/bin/python scripts/refresh_playbook_outcomes.py --company <company_id> [--batches 5]
  .venv/bin/python scripts/refresh_playbook_outcomes.py --all [--batches 5]      # every company with the success rate switched on

Reads the live-help log and the finished calls, calls the per-call model (settings.INTELLIGENCE_MODEL) for the cards it
has to judge and writes ONLY the assistant's own tables (playbook_suggestion_outcomes, playbook_review_moments). Never the
CRM. A card already judged is skipped, so running it again only continues. Needs migration 082 applied.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deps import get_supabase  # noqa: E402
from app.services.feature_flags import is_enabled  # noqa: E402
from app.services.playbooks.assistant_store import get_assistant_store  # noqa: E402
from app.services.playbooks.review_queue import failing_by_answer, recent_outcomes, refresh_moments, refresh_outcomes  # noqa: E402

FLAGS = ("PLAYBOOK_ASSISTANT_ENABLED", "PLAYBOOK_SUCCESS_RATE_ENABLED")


def companies_with_success_rate(supabase) -> list[str]:
    rows = supabase.table("companies").select("id").execute().data or []
    return [r["id"] for r in rows if all(is_enabled(supabase, r["id"], flag) for flag in FLAGS)]


async def refresh_company(supabase, company_id: str, batches: int) -> tuple[int, int]:
    store = get_assistant_store(supabase)
    judged = 0
    for _ in range(batches):
        done = await refresh_outcomes(store, supabase, company_id)
        judged += done
        if not done:
            break
    queued = refresh_moments(store, company_id, failing_by_answer(recent_outcomes(store, company_id)))
    return judged, queued


async def main(company_ids: list[str] | None, batches: int) -> None:
    supabase = get_supabase()
    targets = company_ids or companies_with_success_rate(supabase)
    for company_id in targets:
        judged, queued = await refresh_company(supabase, company_id, batches)
        print(f"{company_id}: judged {judged}, queued {queued}")
    if not targets:
        print("no company has the success rate switched on")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", action="append", help="a company id (repeatable)")
    parser.add_argument("--all", action="store_true", help="every company with the success rate switched on")
    parser.add_argument("--batches", type=int, default=5, help="how many batches of up to 40 cards per company")
    args = parser.parse_args()
    if not args.company and not args.all:
        parser.error("--company or --all is required")
    asyncio.run(main(args.company, args.batches))
