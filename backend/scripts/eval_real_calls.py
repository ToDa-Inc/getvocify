"""Score C04 against hand-labeled real calls.

Usage (from backend/, with the backend env loaded):
  .venv/bin/python -u scripts/eval_real_calls.py --labels evals/C04/real/<set>.json --stored
  .venv/bin/python -u scripts/eval_real_calls.py --labels evals/C04/real/<set>.json --run intelligence_v8 [--model M]

--stored scores what production already saved on each memo (no model call). --run re-reads every
call with that prompt version and the company's pinned playbook, without writing anything back.

The label file holds no conversation text: memo ids, call type, phase, a few turn numbers whose
speaker is certain, and one status per playbook step (with `doubt` when the labeler was unsure).
Transcripts are read from the memos table and cached under evals/C04/real/.cache/ (gitignored),
together with every run's raw output, so a disagreement can be read next to its call.

Reported: call type and speaker accuracy (v8 only), and per-step agreement with the labels on
the firm (no doubt) ones, plus how often the model says "missed" when the label says otherwise:
a false "no lo hiciste" is what costs a rep's trust in coaching.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.intelligence.call_reading import split_turns  # noqa: E402
from app.services.intelligence.extract import (  # noqa: E402
    extract_intelligence,
    pinned_playbook_steps,
    pinned_qualification_inputs,
)

CACHE = Path(__file__).resolve().parents[1] / "evals" / "C04" / "real" / ".cache"
MEMO_COLUMNS = (
    "id,created_at,capture_started_at,transcript,extraction,playbook_version_id,sales_motion_key,"
    "hubspot_contact_id,user_id,company_id"
)


def _supabase():
    from supabase import create_client

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def load_memos(supabase, ids: list[str], *, refresh: bool) -> dict[str, dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "memos.json"
    cached = json.loads(path.read_text()) if path.exists() and not refresh else {}
    missing = [memo_id for memo_id in ids if memo_id not in cached]
    for start in range(0, len(missing), 50):
        chunk = missing[start:start + 50]
        for row in supabase.table("memos").select(MEMO_COLUMNS).in_("id", chunk).execute().data or []:
            cached[row["id"]] = row
    path.write_text(json.dumps(cached, ensure_ascii=False, default=str))
    return cached


def _steps(block: dict) -> dict[str, dict]:
    return {o["step_id"]: o for o in (block or {}).get("playbook_observations") or [] if o.get("step_id")}


def score(labels: list[dict], outputs: dict[str, dict], memos: dict[str, dict]) -> dict:
    step_firm = defaultdict(Counter)
    confusion = Counter()
    call_type = Counter()
    speaker = Counter()
    disagreements = []
    for label in labels:
        memo_id = label["memo_id"]
        block = outputs.get(memo_id)
        if block is None:
            continue
        got_call = block.get("call") or {}
        if got_call:
            call_type["total"] += 1
            if got_call.get("call_type") == label["call_type"]:
                call_type["correct"] += 1
            else:
                disagreements.append({"memo_id": memo_id, "field": "call_type",
                                      "expected": label["call_type"], "got": got_call.get("call_type")})
            rep = set(got_call.get("rep_turns") or [])
            for turn in label.get("rep_turns_sample") or []:
                speaker["total"] += 1
                speaker["correct"] += turn in rep
            for turn in label.get("prospect_turns_sample") or []:
                speaker["total"] += 1
                speaker["correct"] += turn not in rep
        got_steps = _steps(block)
        for step_id, expected in (label.get("steps") or {}).items():
            got = (got_steps.get(step_id) or {}).get("status", "absent")
            want = expected["status"]
            confusion[(want, got)] += 1
            if expected.get("doubt"):
                continue
            step_firm[step_id]["total"] += 1
            step_firm[step_id]["correct"] += got == want
            if got == "missed" and want != "missed":
                step_firm[step_id]["false_missed"] += 1
            if got != want:
                disagreements.append({
                    "memo_id": memo_id, "field": step_id, "expected": want, "got": got,
                    "reason": (got_steps.get(step_id) or {}).get("reason"),
                })
    firm_total = sum(c["total"] for c in step_firm.values())
    firm_correct = sum(c["correct"] for c in step_firm.values())
    said_missed = sum(n for (want, got), n in confusion.items() if got == "missed")
    false_missed = sum(c["false_missed"] for c in step_firm.values())
    return {
        "calls": len([lab for lab in labels if lab["memo_id"] in outputs]),
        "steps_firm": {"correct": firm_correct, "total": firm_total,
                       "pct": round(100 * firm_correct / firm_total, 1) if firm_total else None},
        "steps_by_id": {k: dict(v) for k, v in step_firm.items()},
        "false_missed": {"count": false_missed, "of_said_missed": said_missed},
        "call_type": dict(call_type),
        "speaker": dict(speaker),
        "confusion": {f"{want}->{got}": n for (want, got), n in sorted(confusion.items())},
        "disagreements": disagreements,
    }


def _clean_name(value: str | None) -> str | None:
    """Test accounts carry a "(test)"/"TEST" tag no real rep says out loud."""
    if not value:
        return None
    for tag in ("(test)", "(TEST)", " TEST", " test"):
        value = value.replace(tag, "")
    return " ".join(value.split()) or None


CALL_TIMEOUT_S = 240


async def run_model(supabase, memos: dict[str, dict], ids: list[str], version: str, concurrency: int,
                    overrides: dict[str, str] | None = None, checkpoint: Path | None = None) -> dict[str, dict]:
    """Every finished call is appended to `checkpoint` (JSONL) at once, and calls already there
    are not run again: a killed run resumes where it stopped."""
    overrides = overrides or {}
    done: dict[str, dict] = {}
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            row = json.loads(line)
            done[row["memo_id"]] = row["output"]
    ids = [memo_id for memo_id in ids if memo_id not in done]
    print(f"  {len(done)} calls already in the checkpoint, {len(ids)} to run", flush=True)
    from app.services.intelligence.extract import call_context
    from app.services.llm import LLMClient

    llm_pool = [LLMClient() for _ in range(concurrency)]
    semaphore = asyncio.Semaphore(concurrency)
    out: dict[str, dict] = {}

    async def one(index: int, memo_id: str):
        memo = memos[memo_id]
        if not memo.get("playbook_version_id") and overrides.get(memo_id):
            memo = {**memo, "playbook_version_id": overrides[memo_id]}  # a label's playbook for an unpinned call
        async with semaphore:
            llm = llm_pool[index % concurrency]
            steps = pinned_playbook_steps(supabase, memo)
            qualification, objections = pinned_qualification_inputs(supabase, memo)
            context = call_context(supabase, memo)
            context = {k: _clean_name(v) if isinstance(v, str) else v for k, v in context.items()}
            for attempt in range(2):
                try:
                    shaped, meta = await asyncio.wait_for(extract_intelligence(
                        memo, llm, prompt_version=version, playbook_steps=steps,
                        playbook_qualification=qualification, playbook_objections=objections, **context,
                    ), timeout=CALL_TIMEOUT_S)
                    out[memo_id] = {**(shaped or {}), "_meta": meta}
                    if checkpoint:
                        with checkpoint.open("a") as handle:
                            handle.write(json.dumps({"memo_id": memo_id, "output": out[memo_id]}, ensure_ascii=False, default=str) + "\n")
                    print(f"  {memo_id[:8]} ok ({len(out) + len(done)}/{len(ids) + len(done)})", flush=True)
                    return
                except Exception as exc:  # one retry, then the call counts as missing
                    print(f"  {memo_id[:8]} error {type(exc).__name__}: {str(exc)[:120]}", flush=True)
                    await asyncio.sleep(5)

    await asyncio.gather(*(one(i, memo_id) for i, memo_id in enumerate(ids)))
    return {**done, **out}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stored", action="store_true")
    mode.add_argument("--run")
    parser.add_argument("--model")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--refresh", action="store_true", help="re-read memos instead of the cache")
    parser.add_argument("--only", nargs="*", help="memo id prefixes to run")
    parser.add_argument("--checkpoint", help="JSONL file: finished calls are saved there and skipped on a rerun")
    args = parser.parse_args()

    labels = json.loads(Path(args.labels).read_text())
    if args.only:
        labels = [lab for lab in labels if any(lab["memo_id"].startswith(p) for p in args.only)]
    ids = [lab["memo_id"] for lab in labels]
    supabase = _supabase()
    memos = load_memos(supabase, ids, refresh=args.refresh)
    for memo_id in ids:  # the labels' turn numbers are this split's numbers
        memos[memo_id]["_turns"] = len(split_turns(memos[memo_id].get("transcript") or ""))

    if args.stored:
        name = "stored"
        outputs = {i: (memos[i].get("extraction") or {}).get("intelligence") or {} for i in ids}
    else:
        if args.model:
            settings.INTELLIGENCE_MODEL = args.model
        name = f"{args.run}-{settings.INTELLIGENCE_MODEL.replace('/', '_')}"
        overrides = {lab["memo_id"]: lab["playbook_version_id"] for lab in labels if lab.get("playbook_version_id")}
        checkpoint = Path(args.checkpoint) if args.checkpoint else None
        outputs = asyncio.run(run_model(supabase, memos, ids, args.run, args.concurrency, overrides, checkpoint))

    result = score(labels, outputs, memos)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"run-{stamp}-{name}.json").write_text(
        json.dumps({"name": name, "result": result, "outputs": outputs}, ensure_ascii=False, default=str, indent=1)
    )
    summary = {k: v for k, v in result.items() if k != "disagreements"}
    print(json.dumps({"name": name, **summary}, ensure_ascii=False, indent=1))
    print(f"full run: {CACHE / f'run-{stamp}-{name}.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
