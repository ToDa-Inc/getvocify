"""Extract C04 intelligence for a user's latest memos and print tokens and cost.

Usage (from backend/): .venv/bin/python scripts/backfill_intelligence.py <user_id> [limit]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.deps import get_supabase  # noqa: E402
from app.services.intelligence.extract import ensure_intelligence  # noqa: E402
from app.services.llm import LLMClient  # noqa: E402


def model_price(model: str) -> tuple[float, float] | None:
    """USD per token from OpenRouter's public model list."""
    try:
        rows = httpx.get("https://openrouter.ai/api/v1/models", timeout=20).json().get("data") or []
    except Exception:
        return None
    for row in rows:
        if row.get("id") == model:
            pricing = row.get("pricing") or {}
            return float(pricing.get("prompt") or 0), float(pricing.get("completion") or 0)
    return None


async def main(user_id: str, limit: int) -> None:
    supabase = get_supabase()
    rows = (
        supabase.table("memos")
        .select("id,transcript")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit * 3)
        .execute()
        .data
        or []
    )
    targets = [row["id"] for row in rows if str(row.get("transcript") or "").strip()][:limit]
    price = model_price(settings.INTELLIGENCE_MODEL)
    llm = LLMClient()
    total_in = total_out = 0
    summary = {"stored": 0, "current": 0, "no_transcript": 0, "failed": 0}
    found = {"interest": 0, "objections": 0, "commitments": 0}
    for memo_id in targets:
        try:
            outcome = await ensure_intelligence(supabase, memo_id, llm=llm)
        except Exception as exc:
            summary["failed"] += 1
            print(json.dumps({"memo_id": memo_id, "status": "failed", "error": type(exc).__name__}))
            continue
        status = outcome.get("status")
        summary[status] = summary.get(status, 0) + 1
        meta = outcome.get("meta") or {}
        total_in += int(meta.get("prompt_tokens") or 0)
        total_out += int(meta.get("completion_tokens") or 0)
        block = outcome.get("intelligence") or {}
        if block.get("interest"):
            found["interest"] += 1
        found["objections"] += len(block.get("objections") or [])
        found["commitments"] += len(block.get("commitments") or [])
        print(json.dumps({
            "memo_id": memo_id,
            "status": status,
            "model": meta.get("model"),
            "prompt_tokens": meta.get("prompt_tokens"),
            "completion_tokens": meta.get("completion_tokens"),
            "interest": block.get("interest"),
            "objections": [item.get("category") for item in block.get("objections") or []],
            "commitments": [item.get("text") for item in block.get("commitments") or []],
        }, ensure_ascii=False))
    cost = None
    if price is not None:
        cost = round(total_in * price[0] + total_out * price[1], 6)
    print(json.dumps({
        "model": settings.INTELLIGENCE_MODEL,
        "memos": len(targets),
        **summary,
        "prompt_tokens": total_in,
        "completion_tokens": total_out,
        "usd_total": cost,
        "usd_per_memo": round(cost / max(summary["stored"], 1), 6) if cost is not None else None,
        "found": found,
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20))
