"""Run step-1 CRM extraction (note, tasks, fields) on labeled real calls, without writing anything.

Usage (from backend/, with the backend env loaded):
  .venv/bin/python scripts/eval_crm_extraction.py --labels evals/C04/real/<set>.json \
      --reading-run evals/C04/real/.cache/run-<v8 run>.json --out <dir> [--model M] [--only-grounded]

Two variants per call, same field specs (the author's, as production builds them) and product
context: `legacy` (today's prompt on the raw transcript) and `grounded` (the C04 v8 pipeline: the
call reading from --reading-run relabels the transcript You:/Them: and sets the call type).
Writes <out>/crm_<variant>.json with {memo_id, summary, nextSteps, fields} per call, the input a
judge reads next to the transcript and the labels' must_have / must_not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.intelligence.call_reading import relabel, split_turns  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / "evals" / "C04" / "real" / ".cache"
_SKIP = {"confidence", "summary", "intelligence", "description"}


def _flat(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in (d or {}).items():
        if k in _SKIP or v in (None, "", [], {}):
            continue
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


async def main_async(args) -> int:
    from supabase import create_client

    from app.api.memos import _curated_field_specs_for_primary_crm
    from app.services.extraction import ExtractionService

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    labels = json.loads(Path(args.labels).read_text())
    memos = json.loads((CACHE / "memos.json").read_text())
    reading = json.loads(Path(args.reading_run).read_text())["outputs"]
    if args.model:
        settings.EXTRACTION_MODEL = args.model
    specs_by_user: dict[str, list] = {}
    context_by_company: dict[str, str] = {}
    name_by_company: dict[str, str] = {}
    variants = ["grounded"] if args.only_grounded else ["legacy", "grounded"]
    results = {v: [] for v in variants}
    semaphore = asyncio.Semaphore(args.concurrency)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = out_dir / "checkpoint.jsonl"
    done: set[tuple[str, str]] = set()
    if checkpoint.exists():  # a killed run resumes: finished (call, variant) pairs are kept
        for line in checkpoint.read_text().splitlines():
            row = json.loads(line)
            results.setdefault(row["variant"], []).append(row["row"])
            done.add((row["row"]["memo_id"], row["variant"]))

    async def one(memo_id: str):
        memo = memos[memo_id]
        user, company = str(memo["user_id"]), str(memo["company_id"])
        if user not in specs_by_user:
            specs_by_user[user] = await _curated_field_specs_for_primary_crm(sb, user) or []
        if company not in context_by_company and company in ("None", ""):
            context_by_company[company], name_by_company[company] = "", ""
        if company not in context_by_company:
            row = sb.table("companies").select("product_context,name").eq("id", company).limit(1).execute().data or [{}]
            context_by_company[company] = str(row[0].get("product_context") or "")
            name_by_company[company] = str(row[0].get("name") or "").replace(" TEST", "").strip()
        call = (reading.get(memo_id) or {}).get("call")
        turns = split_turns(memo.get("transcript") or "")
        for variant in variants:
            if variant == "grounded" and not call or (memo_id, variant) in done:
                continue
            transcript = memo["transcript"]
            if variant == "grounded" and len(turns) >= 2:
                transcript = relabel(turns, call)
            async with semaphore:
                try:
                    out = await asyncio.wait_for(ExtractionService().extract(
                        transcript,
                        field_specs=specs_by_user[user],
                        product_context=context_by_company[company],
                        source_context=memo.get("source_type") or "voice_memo",
                        call_date=str(memo.get("capture_started_at") or memo.get("created_at") or "")[:10],
                        call_reading={**call, "rep_company": name_by_company.get(company)} if variant == "grounded" else None,
                    ), timeout=240)
                except Exception as exc:  # a failed call is reported, not fatal
                    print(f"  {memo_id[:8]} {variant} error {str(exc)[:100]}", flush=True)
                    continue
            data = out.model_dump()
            raw = data.get("raw_extraction") or {}
            row = {
                "memo_id": memo_id,
                "summary": data.get("summary"),
                "nextSteps": data.get("nextSteps"),
                "fields": _flat({k: v for k, v in raw.items() if k not in ("nextSteps",)}),
            }
            results[variant].append(row)
            with checkpoint.open("a") as handle:
                handle.write(json.dumps({"variant": variant, "row": row}, ensure_ascii=False, default=str) + "\n")
            print(f"  {memo_id[:8]} {variant} ok", flush=True)

    ids = [lab["memo_id"] for lab in labels if lab["memo_id"] in memos]
    await asyncio.gather(*(one(memo_id) for memo_id in ids))
    for variant, rows in results.items():
        (out_dir / f"crm_{variant}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        filled = sum(len(r["fields"]) for r in rows)
        print(f"{variant}: {len(rows)} calls, {filled} filled fields -> {out_dir / f'crm_{variant}.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--reading-run", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--only-grounded", action="store_true")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
