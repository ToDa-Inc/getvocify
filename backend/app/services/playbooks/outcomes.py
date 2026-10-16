"""What happened to each live-help suggestion: did the rep say it, did it settle the objection or the doubt.

It runs LATER and apart, never when a call ends: it reads what is already stored (the live-help log and the call's own
post-call reading) in bounded batches, so the post-call process takes no longer. The "resolved" half comes from what that
reading already decided for the same objection (`resolution`, `response`, `quote`), so there is one definition of
"resolved" in the product; only "did they use the suggestion" (and the questions that reading does not cover) go to a model.
Unknown is a verdict of its own and never counts as success.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import settings
from app.services.playbooks.structure import _client, _fold, _literal_in
from app.services.playbooks.structured import OBJECTION_CATEGORIES, clip_text
from app.services.playbooks.versions import parse_ts

logger = logging.getLogger(__name__)

PROMPT_VERSION = "suggestion_outcome_v1"
_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"
MIN_MATCH = 0.6
WINDOW_CHARS = 1800
TIMEOUT_S = 40.0
MIN_CASES = 3
# A card is judged this long after it was shown, so the call has ended and its post-call reading has had time to exist.
MIN_AGE_HOURS = 6
AGREEMENT_FLOOR = 0.8
UNKNOWN_CEILING = 0.3
_USED = ("used", "adapted", "not_used", "unknown")
_RESOLVED = ("resolved", "not_resolved", "unknown")
_FIXED_KINDS = frozenset(OBJECTION_CATEGORIES) - {"other"}
_RESOLUTION = {"resolved": "resolved", "open": "not_resolved"}


@lru_cache(maxsize=1)
def _prompt() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def memo_objections(memo: dict) -> list[dict]:
    """The objections the post-call reading found in a call (never obstacles): {category, quote, response, resolution}."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    intel = memo.get("intelligence") or extraction.get("intelligence")
    items = intel.get("objections") if isinstance(intel, dict) else None
    return [o for o in items or [] if isinstance(o, dict) and o.get("kind", "objection") == "objection"]


def _tokens(text: str) -> set[str]:
    return {word for word in _fold(text).split() if len(word) >= 3}


def _overlap(a: str, b: str) -> float:
    left, right = _tokens(a), _tokens(b)
    return len(left & right) / min(len(left), len(right)) if left and right else 0.0


def _jaccard(a: str, b: str) -> float:
    left, right = _tokens(a), _tokens(b)
    return len(left & right) / len(left | right) if left and right else 0.0


def match_objection(event: dict, objections: list[dict]) -> Optional[dict]:
    """The objection of the call the suggestion was about: the one whose words overlap the prospect's at least MIN_MATCH
    (the logged words are cut at 300 characters, so overlap is measured against the shorter side) and, for a usual kind of
    objection, of the same kind. The best overlap wins, the closest wording breaking a tie; None when nothing is close enough."""
    turn = str(event.get("latest_turn") or "")
    kind = event.get("objection_type")
    best: tuple[tuple[float, float], Optional[dict]] = ((0.0, 0.0), None)
    for objection in objections:
        if kind in _FIXED_KINDS and objection.get("category") not in (kind, None):
            continue
        quote = str(objection.get("quote") or "")
        score = (_overlap(turn, quote), _jaccard(turn, quote))
        if score[0] >= MIN_MATCH and score > best[0]:
            best = (score, objection)
    return best[1]


def ready_for_judging(event: dict, memo: Optional[dict], *, now: Optional[datetime] = None) -> bool:
    """Whether a card can be judged now, later and apart from the call: it has a call (`capture_id`), is at least
    MIN_AGE_HOURS old, and that call's post-call reading already exists. Nothing is ever judged while a call is still
    going or being processed, so this work never competes with it."""
    if not event.get("capture_id") or not memo:
        return False
    extraction = memo.get("extraction")
    if not isinstance(extraction, dict) or not extraction:
        return False
    shown = parse_ts(event.get("created_at"))
    if shown is None:
        return False
    return shown <= (now or datetime.now(timezone.utc)) - timedelta(hours=MIN_AGE_HOURS)


def transcript_window(transcript: str, latest_turn: str, *, chars: int = WINDOW_CHARS) -> Optional[str]:
    """The transcript from the line where the prospect said `latest_turn`, at most `chars`; None when it is not in it."""
    words = re.findall(r"\w+", latest_turn or "")[:10]
    if not words or not transcript:
        return None
    found = re.search(r"\W+".join(re.escape(word) for word in words), transcript, re.IGNORECASE)
    if not found:
        return None
    start = transcript.rfind("\n", 0, found.start()) + 1
    return transcript[start : start + chars]


async def _ask(messages: list[dict], llm: Any) -> Any:
    client = _client(llm)
    result = client.chat_json(messages=messages, model=settings.INTELLIGENCE_MODEL, temperature=0.0, timeout=TIMEOUT_S, max_retries=0)
    if inspect.isawaitable(result):
        result = await result
    return result


def _label(value: Any, allowed: tuple[str, ...]) -> str:
    return value if isinstance(value, str) and value in allowed else "unknown"


async def judge_use(say_this: str, rep_reply: Optional[str], *, llm: Any = None) -> str:
    """used | adapted | not_used | unknown for what the rep answered after the suggestion. A rep who said nothing did not use
    it (no model asked); an unreadable answer or a failing model is unknown."""
    if not (rep_reply or "").strip():
        return "not_used"
    user = f"Task: use_only\nSuggested line: {say_this}\nSalesperson's reply: {rep_reply}"
    try:
        raw = await asyncio.wait_for(_ask([{"role": "system", "content": _prompt()}, {"role": "user", "content": user}], llm), TIMEOUT_S + 5)
    except Exception as exc:
        logger.warning("suggestion use not judged: %s", type(exc).__name__)
        return "unknown"
    return _label(raw.get("used") if isinstance(raw, dict) else None, _USED)


async def judge_question(window: str, latest_turn: str, say_this: str, *, llm: Any = None) -> dict:
    """{used, resolved, rep_said} from the transcript at that moment, for what the post-call reading does not cover.
    `rep_said` must be in the transcript or it is dropped; `resolved` only counts when the line was used or adapted."""
    user = (
        f"Task: both\nSuggested line: {say_this}\nWhat the prospect said: {latest_turn}\n\n"
        f'Transcript from that moment on:\n"""\n{window}\n"""'
    )
    try:
        raw = await asyncio.wait_for(_ask([{"role": "system", "content": _prompt()}, {"role": "user", "content": user}], llm), TIMEOUT_S + 5)
    except Exception as exc:
        logger.warning("question outcome not judged: %s", type(exc).__name__)
        return {"used": "unknown", "resolved": "unknown", "rep_said": None}
    data = raw if isinstance(raw, dict) else {}
    used = _label(data.get("used"), _USED)
    resolved = _label(data.get("resolved"), _RESOLVED) if used in ("used", "adapted") else "unknown"
    said = " ".join(str(data.get("rep_said") or "").split())
    return {"used": used, "resolved": resolved, "rep_said": clip_text(said, 300) if said and _literal_in(said, _fold(window)) else None}


async def outcome_for_event(event: dict, memo: Optional[dict], *, llm: Any = None) -> dict:
    """The verdict for one live-help card of a finished call -> {event_id, used, resolved, resolved_by, rep_text, …the card}.
    With no call (or the moment not in it) nothing is guessed and no model is asked."""
    say_this = str(event.get("say_this") or "")
    turn = str(event.get("latest_turn") or "")
    out = {
        "event_id": str(event["id"]), "capture_id": event.get("capture_id"), "sales_motion_key": event.get("sales_motion_key"),
        "entry_id": event.get("entry_id"), "source_id": event.get("source_id"), "objection_type": event.get("objection_type"),
        "observed_at": event.get("created_at"), "client_text": clip_text(turn, 300), "suggestion_text": clip_text(say_this, 400),
        "rep_text": None, "used": "unknown", "resolved": "unknown", "resolved_by": "judge",
    }
    if not memo:
        return out
    matched = match_objection(event, memo_objections(memo))
    if matched is not None:
        reply = str(matched.get("response") or "").strip() or None
        out.update({
            "used": await judge_use(say_this, reply, llm=llm),
            "resolved": _RESOLUTION.get(str(matched.get("resolution")), "unknown"),
            "resolved_by": "extraction",
            "rep_text": clip_text(reply, 300) if reply else None,
        })
        return out
    window = transcript_window(str(memo.get("transcript") or ""), turn)
    if window is None:
        return out
    judged = await judge_question(window, turn, say_this, llm=llm)
    out.update({"used": judged["used"], "resolved": judged["resolved"], "rep_text": judged["rep_said"]})
    return out


def success_stats(rows: list[dict], *, min_cases: int = MIN_CASES) -> dict:
    """The success rate and the use rate of a set of verdicts.
    success rate = resolved / (used or adapted, with a clear verdict on whether it resolved); use rate = (used or adapted) /
    verdicts that say whether it was used. A rate is None below `min_cases` cases: two cases say nothing. Unknown is
    counted apart and is never a success."""
    used_rows = [r for r in rows if r.get("used") in ("used", "adapted")]
    clear = [r for r in used_rows if r.get("resolved") in ("resolved", "not_resolved")]
    resolved = sum(1 for r in clear if r["resolved"] == "resolved")
    judged = [r for r in rows if r.get("used") != "unknown"]
    return {
        "resolved": resolved, "clear": len(clear), "unknown": len(used_rows) - len(clear),
        "rate": resolved / len(clear) if len(clear) >= min_cases else None,
        "used": len(used_rows), "judged": len(judged),
        "use_rate": len(used_rows) / len(judged) if len(judged) >= min_cases else None,
        "sample": len(rows),
    }


def score_labels(rows: list[dict]) -> dict:
    """The feasibility check: our verdicts against the ones Toni labelled by hand ({used, resolved, label_used,
    label_resolved}) -> {n, agreement, unknown_rate, decision}. SIGUE when they agree at least AGREEMENT_FLOOR of the time
    and at most UNKNOWN_CEILING are unknown; otherwise DETENER; SIN ETIQUETAS when nothing is labelled."""
    labelled = [r for r in rows if r.get("label_used")]
    if not labelled:
        return {"n": 0, "agreement": None, "unknown_rate": None, "decision": "SIN ETIQUETAS"}

    def agrees(row: dict) -> bool:
        if row["used"] != row["label_used"]:
            return False
        return not row.get("label_resolved") or row["resolved"] == row["label_resolved"]

    def unknown(row: dict) -> bool:
        return row["used"] == "unknown" or (row["used"] in ("used", "adapted") and row["resolved"] == "unknown")

    n = len(labelled)
    agreement = sum(1 for r in labelled if agrees(r)) / n
    unknown_rate = sum(1 for r in labelled if unknown(r)) / n
    return {
        "n": n, "agreement": agreement, "unknown_rate": unknown_rate,
        "decision": "SIGUE" if agreement >= AGREEMENT_FLOOR and unknown_rate <= UNKNOWN_CEILING else "DETENER",
    }
