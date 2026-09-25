"""Pure pieces of the follow-up draft: decisions, parsing, metrics and the view. No I/O."""
from __future__ import annotations

import difflib
import json
from datetime import datetime, timedelta
from typing import Literal, Optional

PROMPT_VERSION = "followup_v1"
STALE_GENERATING = timedelta(minutes=2)
MAX_SUBJECT = 160
MAX_BODY = 4000
NO_EDIT_THRESHOLD = 0.02      # a fixed typo still counts as "sent as drafted"
VOICE_SAMPLE_MIN_EDIT = 0.05  # only bodies the rep actually reshaped teach us their voice
MAX_VOICE_SAMPLES = 5
SKIPPED_SCREENING = frozenset({"voicemail", "no_response"})


def is_eligible(memo: dict) -> bool:
    """A real conversation with an extraction. Voicemail and no-answer never get a draft."""
    if (memo.get("screening_outcome") or "") in SKIPPED_SCREENING:
        return False
    if not (memo.get("transcript") or "").strip():
        return False
    return bool(((memo.get("extraction") or {}).get("summary") or "").strip())


def should_generate(current: Optional[dict], now: datetime) -> bool:
    """Whether to try. The DB lease enforces single-flight; this avoids pointless writes."""
    if not current:
        return True
    if current.get("status") == "generating":
        started = current.get("started_at")
        return not started or now - datetime.fromisoformat(started) > STALE_GENERATING
    return False  # ready, sent, unavailable: never regenerate behind the rep's back


def build_messages(*, system_prompt: str, transcript: str, summary: str, next_steps: list[str],
                   contact_name: Optional[str], rep_name: Optional[str], voice_samples: list[str]) -> list[dict]:
    context = {
        "rep_name": rep_name or "",
        "contact_name": contact_name or "",
        "summary": summary or "",
        "next_steps": next_steps or [],
        "voice_samples": voice_samples[-3:],
        "transcript": transcript,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]


def parse_draft(payload: object) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None
    subject = " ".join(str(payload.get("subject") or "").split())
    body = str(payload.get("body") or "").strip()
    if not subject or not body:
        return None
    language = str(payload.get("language") or "").strip()[:5] or None
    return {"subject": subject[:MAX_SUBJECT], "body": body[:MAX_BODY], "language": language}


def edit_ratio(draft: str, final: str) -> float:
    """0.0 = sent untouched, 1.0 = rewritten. Whitespace-insensitive."""
    a, b = " ".join((draft or "").split()), " ".join((final or "").split())
    if a == b:
        return 0.0
    return round(1 - difflib.SequenceMatcher(None, a, b).ratio(), 3)


def is_no_edit(ratio: float) -> bool:
    return ratio <= NO_EDIT_THRESHOLD


def next_voice_samples(samples: list[str], final_body: str, ratio: float) -> list[str]:
    """Unedited drafts are our voice, not theirs; only reshaped bodies are kept."""
    if ratio < VOICE_SAMPLE_MIN_EDIT or not final_body.strip():
        return samples
    return (samples + [final_body.strip()])[-MAX_VOICE_SAMPLES:]


def apply_action(current: dict, *, action: Literal["sent", "copied"], channel: str,
                 subject: str, body: str, now: datetime) -> dict:
    ratio = edit_ratio(current.get("body") or "", body)
    updated = {
        **current,
        "final_subject": subject.strip() or current.get("subject") or "",
        "final_body": body.strip(),
        "edit_ratio": ratio,
        "no_edit": is_no_edit(ratio),
    }
    if action == "sent":
        updated.update(status="sent", channel=channel, sent_at=now.isoformat())
    elif action == "copied":
        updated["copied_at"] = now.isoformat()
    else:
        raise ValueError(f"unknown follow-up action {action!r}")
    return updated


def followup_view(memo: dict, *, scheduled: bool = False) -> dict:
    """What every surface renders — the FollowupView of shared/ui/components/followup.js."""
    current = memo.get("followup") or {}
    extraction = memo.get("extraction") or {}
    status = current.get("status") or ("generating" if scheduled else "unavailable")
    view: dict = {"status": status, "recipientName": extraction.get("contactName") or None}
    if status in ("ready", "sent"):
        view["subject"] = current.get("final_subject") or current.get("subject") or ""
        view["body"] = current.get("final_body") or current.get("body") or ""
        email = (extraction.get("contactEmail") or "").strip()
        phone = (extraction.get("contactPhone") or "").replace(" ", "").strip()
        if "@" in email:
            view["to"] = email
        if phone.startswith("+"):
            view["phone"] = phone  # WhatsApp needs the country code; never guess it
    if status == "sent":
        view["channel"] = current.get("channel") or "email"
    return view
