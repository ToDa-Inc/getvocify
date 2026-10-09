"""Step 1 (note, tasks, CRM fields) on labeled calls with its cost and latency, writing nothing.

Usage (from backend/, with the backend env loaded; the model comes from EXTRACTION_MODEL):
  .venv/bin/python evals/tools/step1_timed.py evals/C04/notes/<set>.json \
      evals/C04/real/.cache/run-<v8 run>.json <out_dir>

Writes <out_dir>/crm_grounded.json (what evals/tools/ab_judge.py compares) and prints calls, cost per
call (vendor cost, or settings.TOGETHER_PRICES for a together/ model) and latency.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.services.extraction as extraction  # noqa: E402
import app.services.llm.providers.openrouter as provider  # noqa: E402
import scripts.eval_crm_extraction as crm_eval  # noqa: E402
from app.config import settings  # noqa: E402

metas: list[dict] = []
times: list[float] = []
_meta = provider.openrouter_call_meta
_extract = extraction.ExtractionService.extract


def _spy(data, *, requested_model):
    meta = _meta(data, requested_model=requested_model)
    metas.append(meta)
    return meta


async def _timed(self, *args, **kwargs):
    started = time.perf_counter()
    try:
        return await _extract(self, *args, **kwargs)
    finally:
        times.append(time.perf_counter() - started)


def main() -> None:
    provider.openrouter_call_meta = _spy
    extraction.ExtractionService.extract = _timed

    class Args:
        labels, reading_run, out = sys.argv[1:4]
        model = None
        concurrency = 3
        only_grounded = True

    asyncio.run(crm_eval.main_async(Args()))
    model = settings.EXTRACTION_MODEL
    together_id = model.split("/", 1)[1] if model.startswith(provider.TOGETHER_PREFIX) else None
    cost = sum((provider._priced(m, provider.TOGETHER_PROVIDER, together_id) if together_id else m).get("cost_usd") or 0
               for m in metas)
    print(f"{model}: {len(times)} calls | {100 * cost / max(1, len(times)):.3f} c$ per call | "
          f"latency median {statistics.median(times):.1f}s max {max(times):.1f}s")


if __name__ == "__main__":
    main()
