"""C04 v8, pass 1: read the call before judging it.

Diarization labels (S1/S2) do not say who sells, and they swap mid-call. This pass reads each
numbered turn and says who spoke by what they said, what kind of call it was and how far the
conversation got. The transcript is then rewritten with You:/Them: so every later check (the
rep's own words, the prospect's answer, whether the rep replied) works on real roles.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.transcript_turns import parse_transcript_turns

PROMPT_VERSION = "call_reading_v1"
_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"

CALL_TYPES = frozenset({
    "cold_first_contact",
    "follow_up",
    "meeting_confirmation",
    "meeting_reschedule",
    "discovery_meeting",
    "bad_moment",
    "gatekeeper",
    "wrong_person",
    "no_conversation",
    "not_a_sales_call",
    "dictated_note",
    "other",
})
PHASES = ("none", "opening", "discovery", "pitch", "closing")
# A call of these types never gets past the opening, whatever steps the playbook has.
OPENING_ONLY = frozenset({"bad_moment", "gatekeeper", "wrong_person"})
NOT_JUDGED = frozenset({"no_conversation", "not_a_sales_call", "dictated_note"})
# Calls that pick up an earlier conversation: only their opening is the rep's job to get right.
CONTINUES_EARLIER = frozenset({"follow_up", "meeting_confirmation", "meeting_reschedule"})

_LABELED_LINE = re.compile(r"^\s*([^:\n]{1,40}?)\s*:\s*(\S.*)$")


def split_turns(transcript: str) -> list[dict]:
    """[{speaker, text}] in order. SPEAKER: S1 blocks, or one `Label: text` per line
    (You/Them, names from a meeting bot). One unlabeled turn when nothing parses."""
    turns = [t for t in parse_transcript_turns(transcript) if (t.get("text") or "").strip()]
    if any(t.get("speaker") for t in turns):
        return [{"speaker": t.get("speaker"), "text": " ".join(str(t["text"]).split())} for t in turns]
    lines = [line for line in str(transcript or "").splitlines() if line.strip()]
    labeled = [_LABELED_LINE.match(line) for line in lines]
    if lines and sum(1 for m in labeled if m) >= max(2, len(lines) // 2):
        out: list[dict] = []
        for line, match in zip(lines, labeled):
            if match:
                out.append({"speaker": match.group(1).strip(), "text": " ".join(match.group(2).split())})
            elif out:
                out[-1]["text"] = f"{out[-1]['text']} {' '.join(line.split())}"
        return out
    text = " ".join(str(transcript or "").split())
    return [{"speaker": None, "text": text}] if text else []


def numbered(turns: list[dict]) -> str:
    return "\n".join(f"[{n}] {t.get('speaker') or '?'}: {t['text']}" for n, t in enumerate(turns, 1))


def build_reading_messages(
    turns: list[dict],
    *,
    captured_at: str,
    rep_name: str | None = None,
    company_name: str | None = None,
    prior_conversations: int | None = None,
    playbooks: dict[str, str] | None = None,
) -> list[dict]:
    payload: dict[str, Any] = {"captured_at": captured_at, "turns": numbered(turns)}
    if playbooks:
        # The company's own types: the same read also says which playbook the call was.
        payload["playbooks"] = [{"key": key, "what_it_is": what} for key, what in playbooks.items()]
    if rep_name:
        payload["rep_name"] = rep_name
    if company_name:
        payload["rep_company"] = company_name
    if prior_conversations is not None:
        payload["prior_conversations_with_this_contact"] = prior_conversations
    return [
        {"role": "system", "content": _PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _turn_numbers(value: Any, count: int) -> set[int]:
    out: set[int] = set()
    for item in value if isinstance(value, list) else []:
        if isinstance(item, bool):
            continue
        if isinstance(item, int) and 1 <= item <= count:
            out.add(item)
        elif isinstance(item, str) and re.fullmatch(r"\d+\s*-\s*\d+", item.strip()):
            start, end = (int(x) for x in item.split("-"))
            out.update(n for n in range(start, end + 1) if 1 <= n <= count)
        elif isinstance(item, str) and item.strip().isdigit() and 1 <= int(item) <= count:
            out.add(int(item))
    return out


def shape_reading(raw: Any, turns: list[dict], playbooks: dict[str, str] | None = None) -> dict:
    """Only values the schema allows. A turn nobody claimed stays the prospect's: the rep is
    the one with something to prove, so an unclaimed line never counts as the rep doing a step."""
    raw = raw if isinstance(raw, dict) else {}
    count = len(turns)
    call_type = raw.get("call_type") if raw.get("call_type") in CALL_TYPES else "other"
    phase = raw.get("phase_reached") if raw.get("phase_reached") in PHASES else "none"
    rep = _turn_numbers(raw.get("rep_turns"), count)
    other = _turn_numbers(raw.get("other_turns"), count) - rep
    reached = raw.get("reached_conversation")
    if not isinstance(reached, bool):
        reached = call_type not in NOT_JUDGED and phase != "none"
    if call_type == "no_conversation":
        reached, phase = False, "none"
    reason = " ".join(str(raw.get("call_type_reason") or "").split())[:200] or None
    playbook = raw.get("playbook")
    # Only one of the company's types; "unknown" (or anything else) names none.
    playbook = playbook if playbooks and isinstance(playbook, str) and playbook in playbooks and playbook != "unknown" else None
    return {
        "version": PROMPT_VERSION,
        "call_type": call_type,
        "ended_abruptly": raw.get("ended_abruptly") is True,
        "call_type_reason": reason,
        "phase_reached": phase,
        "reached_conversation": reached,
        "rep_turns": sorted(rep),
        "other_turns": sorted(other),
        "turn_count": count,
        "playbook": playbook,
    }


def relabel(turns: list[dict], reading: dict) -> str:
    """The transcript with You: (rep) / Them: (prospect, or anyone else) on every turn."""
    rep = set(reading.get("rep_turns") or [])
    return "\n\n".join(
        f"{'You' if n in rep else 'Them'}: {t['text']}" for n, t in enumerate(turns, 1)
    )


async def read_call(
    transcript: str,
    llm: Any,
    *,
    model: str,
    captured_at: str,
    rep_name: str | None = None,
    company_name: str | None = None,
    prior_conversations: int | None = None,
    playbooks: dict[str, str] | None = None,
) -> tuple[dict | None, str, dict]:
    """(reading, You:/Them: transcript, call meta). No reading when there is no text, or one
    unlabeled block with nothing to split: the transcript is then returned as it was."""
    turns = split_turns(transcript)
    if not turns:
        return None, transcript, {}
    from app.config import settings

    effort = getattr(settings, "INTELLIGENCE_READING_EFFORT", None)
    raw = await llm.chat_json(
        build_reading_messages(
            turns, captured_at=captured_at, rep_name=rep_name,
            company_name=company_name, prior_conversations=prior_conversations, playbooks=playbooks,
        ),
        model=model,
        temperature=0.0,
        timeout=90.0,
        **({"reasoning_effort": effort} if effort else {}),
    )
    meta = dict(getattr(llm, "last_call_meta", None) or {})
    reading = shape_reading(raw, turns, playbooks)
    if len(turns) < 2:
        # Nothing to split: a dictated note, or a transcript without speaker labels. The text
        # stays as it was and the judging pass is told the roles are not marked.
        return {**reading, "roles_marked": False}, transcript, meta
    return {**reading, "roles_marked": True}, relabel(turns, reading), meta
