"""Pure pieces of the follow-up draft: decisions, parsing, metrics and the view. No I/O."""
from __future__ import annotations

import difflib
import json
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.hoy.names import clean_name

PROMPT_VERSION = "followup_v2"
STALE_GENERATING = timedelta(minutes=2)
MAX_SUBJECT = 160
MAX_BODY = 4000
NO_EDIT_THRESHOLD = 0.02      # a fixed typo still counts as "sent as drafted"
VOICE_SAMPLE_MIN_EDIT = 0.05  # only bodies the rep actually reshaped teach us their voice
MAX_VOICE_SAMPLES = 5         # learned samples only; pasted ones are capped by MAX_PASTED
MAX_PASTED = 3
PASTED_MIN_CHARS = 40
PASTED_MAX_CHARS = 1500
PASTED = "pasted"
DEFAULT_TZ = "Europe/Madrid"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SKIPPED_SCREENING = frozenset({"voicemail", "no_response"})
# Sent drafts belong to «Hecho hoy», not to the pending list.
LISTABLE_STATUSES = ("ready", "generating", "unavailable")
LIST_WINDOW = timedelta(days=7)
LIST_LIMIT = 50


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
                   contact_name: Optional[str], rep_name: Optional[str], voice_samples: list[str],
                   facts: Optional[dict] = None) -> list[dict]:
    """Without C04 facts the input is exactly the pre-C04 one."""
    context = {
        "rep_name": rep_name or "",
        "contact_name": contact_name or "",
        "summary": summary or "",
        "next_steps": next_steps or [],
    }
    if facts is not None:
        context.update(commitments=facts.get("commitments") or [], meeting=facts.get("meeting"),
                       pain_quote=facts.get("pain_quote"))
    context.update(voice_samples=voice_samples[-3:], transcript=transcript)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]


def _zone(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def _day(value: date) -> str:
    """Weekday spelled out (not via the process locale): models misplace weekdays computed from bare dates."""
    return f"{WEEKDAYS[value.weekday()]} {value.isoformat()}"


def _when(value: Any, precision: Any, tz: ZoneInfo) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        if precision == "date":
            return {"day": _day(date.fromisoformat(value.strip()[:10]))}  # a day is that day in every zone
        if precision == "time":
            local = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone(tz)
            return {"day": _day(local.date()), "time": f"{local:%H:%M}"}
    except ValueError:
        return {}
    return {}


def _pain_quote(block: dict) -> Optional[str]:
    """C04 keeps no pointer to the pain evidence: it is the one no other fact references."""
    if block.get("pain_confirmed") is not True:
        return None
    referenced: set[str] = set()
    for value in block.values():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                referenced.update(str(ref) for ref in item.get("evidence_refs") or [])
    loose = [ev for ev in block.get("evidence") or [] if isinstance(ev, dict) and ev.get("id") not in referenced]
    quote = str(loose[0].get("quote") or "").strip() if len(loose) == 1 else ""
    return quote or None


def c04_facts(block: dict, tz_name: Optional[str]) -> dict:
    """What C04 agreed, in the rep's own day and time, as the follow-up prompt reads it."""
    tz = _zone(tz_name)
    commitments = []
    for item in block.get("commitments") or []:
        text = str((item or {}).get("text") or "").strip() if isinstance(item, dict) else ""
        if text:
            commitments.append({"text": text, **_when(item.get("due_at"), item.get("temporal_precision"), tz)})
    raw = block.get("meeting") if isinstance(block.get("meeting"), dict) else {}
    meeting = _when(raw.get("starts_at"), raw.get("precision"), tz) if raw.get("agreed") is True else {}
    return {"commitments": commitments, "meeting": meeting or None, "pain_quote": _pain_quote(block)}


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


def _is_pasted(sample: Any) -> bool:
    return isinstance(sample, dict) and sample.get("source") == PASTED


def next_voice_samples(samples: list, final_body: str, ratio: float) -> list:
    """Unedited drafts are our voice, not theirs; only reshaped bodies are kept.
    The cap drops the oldest learned sample, never one the rep pasted."""
    if ratio < VOICE_SAMPLE_MIN_EDIT or not final_body.strip():
        return samples
    grown = samples + [final_body.strip()]
    excess = sum(not _is_pasted(sample) for sample in grown) - MAX_VOICE_SAMPLES
    kept = []
    for sample in grown:
        if excess > 0 and not _is_pasted(sample):
            excess -= 1
            continue
        kept.append(sample)
    return kept


def voice_texts(samples: list) -> list[str]:
    """Learned samples are strings, pasted ones {"text", "source": "pasted"}; oldest first."""
    texts = []
    for sample in samples or []:
        text = sample.get("text") if _is_pasted(sample) else sample
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def pasted_samples(samples: list) -> list[str]:
    return voice_texts([sample for sample in samples or [] if _is_pasted(sample)])


def clean_pasted(raw: list[str]) -> list[str]:
    cleaned = [text.strip() for text in raw if isinstance(text, str) and text.strip()]
    if len(cleaned) > MAX_PASTED:
        raise ValueError(f"at most {MAX_PASTED} samples")
    if any(not PASTED_MIN_CHARS <= len(text) <= PASTED_MAX_CHARS for text in cleaned):
        raise ValueError(f"each sample needs {PASTED_MIN_CHARS} to {PASTED_MAX_CHARS} characters")
    return cleaned


def with_pasted(samples: list, pasted: list[str]) -> list:
    """The new pasted set replaces the old one as the most recent entries; learned ones stay."""
    learned = [sample for sample in samples or [] if not _is_pasted(sample)]
    return learned + [{"text": text, "source": PASTED} for text in pasted]


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


def listable_statuses(raw: str) -> tuple[str, ...]:
    wanted = tuple(dict.fromkeys(part.strip() for part in (raw or "").split(",") if part.strip()))
    if not wanted:
        return ("ready",)
    unknown = [value for value in wanted if value not in LISTABLE_STATUSES]
    if unknown:
        raise ValueError(f"status must be one of {', '.join(LISTABLE_STATUSES)}")
    return wanted


def pending_row(memo: dict) -> dict:
    """One draft the author still has to act on, as the rep home lists it."""
    current = memo.get("followup") or {}
    extraction = memo.get("extraction") or {}
    status = current.get("status")
    subject = (current.get("final_subject") or current.get("subject") or None) if status == "ready" else None
    return {
        "memo_id": memo.get("id"),
        "contact_id": memo.get("hubspot_contact_id") or None,
        "contact_name": clean_name(extraction.get("contactName")),
        "company_name": clean_name(extraction.get("companyName")),
        "subject": subject,
        "status": status,
        "generated_at": current.get("ready_at") or current.get("started_at") or None,
    }
