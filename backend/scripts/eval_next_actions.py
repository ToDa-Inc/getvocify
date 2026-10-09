"""Score what a call leads to (follow-up email, callback and when, meeting and when) and print the
pre-call brief each call would produce, against hand labels of real calls.

Usage (from backend/, with the backend env loaded):
  .venv/bin/python scripts/eval_next_actions.py --labels evals/C04/real/<set>_next.local.json --stored
  .venv/bin/python scripts/eval_next_actions.py --labels ... --run-file evals/C04/real/.cache/run-<...>.json

--stored reads the intelligence production saved; --run-file the outputs of an eval_real_calls run.
Every decision is made by the same code the product runs (after_call.promised_email, the Hoy
commitment signal, the brief), so a miss here is a miss a rep sees. Brief lines are written next to
the labeled ideal brief for a judge to read (`--brief-out`); they are not scored here.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.after_call import promised_email  # noqa: E402
from app.services.briefs.v2 import prepare_brief_v2  # noqa: E402
from app.services.hoy.signals import UNANSWERED_OUTCOMES, screening_from_call  # noqa: E402
from app.services.intelligence.worker import revision_for_memo  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / "evals" / "C04" / "real" / ".cache"
MADRID = ZoneInfo("Europe/Madrid")


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=MADRID)


def _local(value) -> tuple[str | None, str | None]:
    """(YYYY-MM-DD, HH:MM or None) in Madrid. A date-only label/commitment has no time."""
    text = str(value or "")
    if len(text) == 10:
        return text, None
    parsed = _dt(text)
    if parsed is None:
        return None, None
    local = parsed.astimezone(MADRID)
    clock = local.strftime("%H:%M")
    return local.date().isoformat(), (None if clock == "00:00" else clock)


def system_view(intel: dict) -> dict:
    calls = [
        c for c in intel.get("commitments") or []
        if isinstance(c, dict) and c.get("kind") == "call"
    ]
    dated = sorted((c for c in calls if c.get("due_at")), key=lambda c: str(c["due_at"]))
    callback_when = None
    if dated:
        day, clock = _local(dated[0]["due_at"])
        if dated[0].get("temporal_precision") != "time":
            clock = None
        callback_when = f"{day}T{clock}" if clock else day
    nxt = intel.get("next") if isinstance(intel.get("next"), dict) else None
    if nxt is not None:  # v8: the call's own next block is what the product reads
        cb = nxt.get("callback") or {}
        calls = [cb] if cb.get("needed") else []
        dated = [cb] if cb.get("needed") and cb.get("when") else []
        callback_when = None
        if dated:
            day, clock = _local(cb["when"])
            callback_when = f"{day}T{clock}" if clock and cb.get("temporal_precision") == "time" else day
    meeting = intel.get("meeting") if isinstance(intel.get("meeting"), dict) else {}
    starts = None
    if meeting.get("starts_at"):
        day, clock = _local(meeting["starts_at"])
        starts = f"{day}T{clock}" if clock and meeting.get("precision") == "time" else day
    # What Hoy shows: an agreed callback, or a retry card when the call reading saw a voicemail
    # or a "can't talk now" (hoy.signals.screening_from_call).
    retry = screening_from_call(None, intel) in UNANSWERED_OUTCOMES
    return {
        "email": promised_email(intel),
        "callback": bool(calls) or retry,
        "callback_dated": bool(dated),
        "callback_when": callback_when,
        "meeting": meeting.get("agreed"),
        "meeting_starts_at": starts,
    }


def brief_for(memo: dict, intel: dict, *, days_after: int = 1) -> list[str]:
    """The SDR brief a rep would read the day after the call (or on the callback day)."""
    extraction = {k: v for k, v in (memo.get("extraction") or {}).items() if k != "intelligence"}
    row = {**memo, "extraction": extraction}
    block = {**intel, "input_revision": revision_for_memo(row)}
    row = {**row, "extraction": {**extraction, "intelligence": block}}
    at = _dt(memo.get("capture_started_at") or memo.get("created_at")) or datetime.now(timezone.utc)
    callbacks = [c for c in intel.get("commitments") or [] if isinstance(c, dict) and c.get("kind") == "call" and c.get("due_at")]
    now = at + timedelta(days=days_after)
    if callbacks:
        due = min(_dt(c["due_at"]) for c in callbacks if _dt(c["due_at"]))
        now = max(now, due + timedelta(minutes=1)) if due else now
    brief = prepare_brief_v2(coverage="complete", memos=[row], tz_name="Europe/Madrid", now=now, sdr_two_line=True)
    lines = [brief.get("text")] if brief.get("text") else []
    lines += [line["text"] for line in brief.get("lines") or []]
    if brief.get("label"):
        lines.append(f"[{brief['label']}]")
    return lines


def _match_when(want: str | None, got: str | None) -> str:
    if not want and not got:
        return "both_none"
    if not want:
        return "extra"
    if not got:
        return "missing"
    if want == got:
        return "exact"
    return "same_day" if want[:10] == got[:10] else "wrong"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stored", action="store_true")
    source.add_argument("--run-file")
    parser.add_argument("--brief-out")
    args = parser.parse_args()

    labels = json.loads(Path(args.labels).read_text())
    memos = json.loads((CACHE / "memos.json").read_text())
    if args.stored:
        outputs = {i: (memos[i].get("extraction") or {}).get("intelligence") or {} for i in memos}
        name = "stored"
    else:
        run = json.loads(Path(args.run_file).read_text())
        outputs, name = run["outputs"], run["name"]

    tally = {k: Counter() for k in ("email", "callback", "callback_when", "meeting", "meeting_when")}
    rows, briefs = [], []
    for label in labels:
        memo_id = label["memo_id"]
        intel = outputs.get(memo_id)
        if intel is None or memo_id not in memos:
            continue
        got = system_view(intel)
        email = label.get("followup_email") or {}
        want_email = bool(email.get("needed"))  # a calendar invite is a follow-up email too
        tally["email"][("TP" if got["email"] else "FN") if want_email else ("FP" if got["email"] else "TN")] += 1
        cb = label.get("callback") or {}
        want_cb = bool(cb.get("needed"))
        tally["callback"][("TP" if got["callback"] else "FN") if want_cb else ("FP" if got["callback"] else "TN")] += 1
        if want_cb:
            tally["callback_when"][_match_when(cb.get("when"), got["callback_when"])] += 1
        mt = label.get("meeting") or {}
        want_mt = mt.get("booked") is True
        tally["meeting"][("TP" if got["meeting"] is True else "FN") if want_mt else ("FP" if got["meeting"] is True else "TN")] += 1
        if want_mt:
            tally["meeting_when"][_match_when(mt.get("starts_at"), got["meeting_starts_at"])] += 1
        rows.append({"memo_id": memo_id, "got": got, "want": {
            "email": want_email, "callback": want_cb, "callback_when": cb.get("when"),
            "meeting": want_mt, "meeting_starts_at": mt.get("starts_at")}})
        briefs.append({"memo_id": memo_id, "ideal": label.get("brief_next_call") or [], "system": brief_for(memos[memo_id], intel)})

    def prf(c: Counter) -> dict:
        tp, fp, fn = c["TP"], c["FP"], c["FN"]
        return {**dict(c), "precision": round(tp / (tp + fp), 2) if tp + fp else None,
                "recall": round(tp / (tp + fn), 2) if tp + fn else None}

    summary = {
        "name": name, "calls": len(rows),
        "email": prf(tally["email"]), "callback": prf(tally["callback"]),
        "callback_when": dict(tally["callback_when"]),
        "meeting": prf(tally["meeting"]), "meeting_when": dict(tally["meeting_when"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    misses = [r for r in rows if r["got"]["email"] != r["want"]["email"] or r["got"]["callback"] != r["want"]["callback"]
              or (r["want"]["meeting"] != (r["got"]["meeting"] is True))]
    print(f"{len(misses)} calls with a wrong decision:")
    for r in misses:
        print(" ", r["memo_id"][:8], "got", r["got"], "want", r["want"])
    if args.brief_out:
        Path(args.brief_out).write_text(json.dumps(briefs, ensure_ascii=False, indent=1))
        print(f"briefs: {args.brief_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
