"""Re-publish objection patterns and score for a user's memos that already have current C04 intelligence.

Memos extracted before C04 objections fed interaction_patterns never reached Team or the weekly report.
Usage (from backend/): .venv/bin/python scripts/reproject_patterns.py <user_id> [limit]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deps import get_supabase  # noqa: E402
from app.services.intelligence.extract import is_current  # noqa: E402
from app.services.memo_extraction_hooks import refresh_coaching_from_intelligence  # noqa: E402


def main(user_id: str, limit: int) -> None:
    supabase = get_supabase()
    memos = (
        supabase.table("memos")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    done = skipped = 0
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        if not is_current(memo):
            skipped += 1
            continue
        refresh_coaching_from_intelligence(supabase, memo, extraction)
        done += 1
        objections = [item.get("category") for item in (extraction.get("intelligence") or {}).get("objections") or []]
        print(json.dumps({"memo_id": memo["id"], "objections": objections}, ensure_ascii=False))
    print(json.dumps({"reprojected": done, "skipped_not_current": skipped}))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 50)
