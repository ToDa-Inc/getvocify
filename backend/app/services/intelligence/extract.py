"""C04 facts from one transcript: interest, objections, commitments. One model call per revision."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.usage import scoped
from app.config import settings
from app.services.playbooks.outcome_steps import step_outcome
from app.services.intelligence.worker import revision_for_memo

PROMPT_VERSION = "intelligence_v5"
# v6 = v5 + named competitors + one observation per playbook step (PLAYBOOK_OBSERVATIONS_ENABLED,
# per company). Both versions produce the same shape, so both count as current: a company
# turning the flag on gets v6 on new conversations; older ones keep their v5 facts.
# v5/v6 are v3/v4 plus the objection/obstacle split: `kind` "objection" (a concern about the offer)
# or "obstacle" (a practical block: bad moment, gatekeeper, wrong person, needs to consult).
OBSERVATIONS_PROMPT_VERSION = "intelligence_v6"
OBSERVATIONS_FLAG = "PLAYBOOK_OBSERVATIONS_ENABLED"
# v7 = v6 + one observation per "what has to come out of the call" criterion and a match of each
# objection to the company's own objections (PLAYBOOK_QUALIFICATION_ENABLED, per company). Same
# shape as v6 plus `qualification_observations` and `objection_id`; a company turning the flag on
# gets v7 on new conversations and past v5/v6 blocks are re-read (`_needs_upgrade`). Nothing is
# ever downgraded when the flag goes off.
QUALIFICATION_PROMPT_VERSION = "intelligence_v7"
QUALIFICATION_FLAG = "PLAYBOOK_QUALIFICATION_ENABLED"
# v8 = v7 read after a first pass (call_reading.py) that says who spoke in each turn by what they
# said, what kind of call it was and how far it got. Steps are judged by their purpose and
# adapted to the call type, each with a reason and, when missed, advice for the rep
# (INTELLIGENCE_CALL_READING_ENABLED, per company). Same shape as v7 plus `call`.
CALL_READING_PROMPT_VERSION = "intelligence_v8"
CALL_READING_FLAG = "INTELLIGENCE_CALL_READING_ENABLED"
CURRENT_PROMPT_VERSIONS = frozenset({
    PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION, QUALIFICATION_PROMPT_VERSION, CALL_READING_PROMPT_VERSION,
})
_READS_STEPS = frozenset({OBSERVATIONS_PROMPT_VERSION, QUALIFICATION_PROMPT_VERSION, CALL_READING_PROMPT_VERSION})
_READS_QUALIFICATION = frozenset({QUALIFICATION_PROMPT_VERSION, CALL_READING_PROMPT_VERSION})
_REASON_MAX = 240
_QUALITY = frozenset({"solid", "improvable"})
_MAX_CRITERIA = 8
_MAX_CUSTOM_OBJECTIONS = 12
_CUSTOM_ENTRY_PREFIX = "objection:custom:"
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_PATH = _PROMPTS_DIR / f"{PROMPT_VERSION}.md"


def prompt_path(version: str) -> Path:
    return _PROMPTS_DIR / f"{version}.md"

_INTEREST = frozenset({"high", "medium", "low", "none"})
_CATEGORY = frozenset({"price", "timing", "authority", "competitor", "status_quo", "trust", "other"})
_OBSTACLE_CATEGORY = frozenset({"bad_moment", "gatekeeper", "wrong_person", "needs_to_consult", "other"})
_EPISODE_KIND = frozenset({"objection", "obstacle"})
_RESOLUTION = frozenset({"resolved", "open", "unknown"})
_KIND = frozenset({"call", "email", "send", "meeting", "other"})
_ORIGIN = frozenset({"rep_promise", "prospect_request"})
_OBSERVATION = frozenset({"met", "missed", "not_applicable", "unknown"})
_QUALIFICATION = frozenset({"found", "missing", "not_applicable", "unknown"})
_VALUE_MAX = 80
_COMPETITOR_MAX = 60
_TEXT_MAX = 80
_DEFAULT_TZ = "Europe/Madrid"


def _speaker(transcript: str, quote: str) -> str | None:
    """Who said it, read from the nearest speaker marker before the quote. Never from the model."""
    text = " ".join(transcript.split())
    at = text.find(quote)
    if at < 0:
        return None
    before = text[:at]
    rep, prospect = before.rfind("You:"), before.rfind("Them:")
    if rep == prospect:
        return None
    return "rep" if rep > prospect else "prospect"


def _fold(text: str) -> tuple[str, list[int]]:
    """Lowercase, no accents, no punctuation, single spaces; and where each kept character
    came from in `text`, so a match can be cut back out of the original."""
    out: list[str] = []
    where: list[int] = []
    for index, char in enumerate(text):
        base = unicodedata.normalize("NFKD", char)
        base = "".join(c for c in base if not unicodedata.combining(c)).lower()
        for c in base:
            if c.isalnum():
                out.append(c)
                where.append(index)
            elif out and out[-1] != " ":
                out.append(" ")
                where.append(index)
    while out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), where


def _locate(quote: str, transcript: str) -> str | None:
    """The transcript's own words for a quote. Exact first; then ignoring case, accents and
    punctuation, which ASR and models never copy the same way. A quote shorter than three
    words must match exactly: folded, it could land anywhere."""
    text = " ".join(str(quote or "").split())
    flat = " ".join(str(transcript or "").split())
    if not text:
        return None
    if text in flat:
        return text
    folded_quote, _ = _fold(text)
    if len(folded_quote.split()) < 3:
        return None
    folded, where = _fold(flat)
    at = folded.find(folded_quote)
    if at < 0:
        return None
    start, end = where[at], where[at + len(folded_quote) - 1]
    return flat[start:end + 1].strip()


def _evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    text = _locate(quote, transcript)
    if not text:
        return None
    digest = hashlib.sha256(f"{memo_id}:{text}".encode()).hexdigest()[:16]
    ref = {"id": f"ev-{digest}", "source_type": "transcript", "source_id": memo_id, "quote": text}
    speaker = _speaker(transcript, text)
    if speaker:
        ref["speaker_role"] = speaker
    return ref


_TURN = re.compile(r"(You|Them):\s*")


def _turns(transcript: str) -> list[tuple[str, str]] | None:
    """Ordered (speaker, text) turns when the transcript uses the You:/Them: convention.
    None when the transcript carries no speaker markers we recognize (T10: a response then
    counts on a plain substring match, same as before; it does not favor either speaker)."""
    matches = list(_TURN.finditer(transcript))
    if not matches:
        return None
    turns = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(transcript)
        turns.append((match.group(1), transcript[start:end].strip()))
    return turns


def _own_words(memo_id: str, quote: str, transcript: str, speaker: str) -> dict | None:
    """The speaker's quote when the other side cut in ("Sí.", "Vale.") halfway through it: the
    quote is found across that speaker's turns, and the evidence is its longest piece inside a
    single turn, so it is still the transcript's own contiguous words."""
    turns = _turns(transcript)
    if turns is None:
        return None
    own = [" ".join(text.split()) for who, text in turns if who == speaker]
    # The quote may span the other side too (the rep's question and the prospect's answer):
    # what counts is the speaker's own longest piece of it, inside a single turn.
    matched = _locate(quote, " ".join(own)) or _locate(quote, transcript) or " ".join(str(quote or "").split())
    best = ""
    for text in own:
        hit = SequenceMatcher(None, text.lower(), matched.lower(), autojunk=False).find_longest_match(0, len(text), 0, len(matched))
        piece = text[hit.a:hit.a + hit.size].strip(" ,.;:¿?¡!")
        if len(piece) > len(best):
            best = piece
    if len(best.split()) < 4:
        return None
    return _evidence(memo_id, best, transcript)


def _rep_evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    """T10: an objection's response only counts when it is the rep's own words. When the
    transcript has no speaker markers, fall back to the plain substring check."""
    ref = _evidence(memo_id, quote, transcript)
    if ref is None:
        return _own_words(memo_id, quote, transcript, "You")
    turns = _turns(transcript)
    if turns is None:
        return ref
    rep_text = " ".join(" ".join(text.split()) for speaker, text in turns if speaker == "You")
    if _locate(ref["quote"], rep_text) is None:
        return None
    return ref


def _prospect_evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    """v7: a qualification criterion is only found when the PROSPECT said it. With speaker
    markers the quote must sit inside the prospect's own turns; without them it counts on a
    plain substring match, as a rep quote does."""
    ref = _evidence(memo_id, quote, transcript)
    if ref is None:
        return _own_words(memo_id, quote, transcript, "Them")
    turns = _turns(transcript)
    if turns is None:
        return ref
    prospect_text = " ".join(" ".join(text.split()) for speaker, text in turns if speaker == "Them")
    if _locate(ref["quote"], prospect_text) is None:
        return None
    return ref


def _rep_replied_after(transcript: str, quote: str) -> bool | None:
    """T10: whether a rep ("You") turn exists after the turn that raised this objection.
    None when the transcript has no speaker markers: score_assembly then never marks the
    objection missed on evidence it cannot actually see."""
    turns = _turns(transcript)
    if turns is None:
        return None
    needle = " ".join(quote.split())
    found_index = None
    for index, (_, text) in enumerate(turns):
        if needle in " ".join(text.split()):
            found_index = index
            break
    if found_index is None:
        return None
    return any(speaker == "You" for speaker, _ in turns[found_index + 1 :])


def _due(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat() if parsed.tzinfo else None


def _meeting_start(value: Any) -> tuple[str | None, str]:
    if isinstance(value, str) and len(value.strip()) == 10:
        try:
            return date.fromisoformat(value.strip()).isoformat(), "date"
        except ValueError:
            return None, "unknown"
    due = _due(value)
    return (due, "time") if due else (None, "unknown")


def _zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or _DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(_DEFAULT_TZ)


def _commitment_due(value: Any, tz_name: Any) -> tuple[str | None, str]:
    """A day without a time starts that day in the memo timezone, so Hoy shows it that morning."""
    day, precision = _meeting_start(value)
    if precision != "date":
        return day, precision
    start = datetime.combine(date.fromisoformat(day), time(), tzinfo=_zone(tz_name))
    return start.isoformat(), "date"


_EMAIL_KIND = frozenset({"info", "proposal", "calendar_invite", "recap", "other"})
_WHO_ASKED = frozenset({"prospect", "rep"})


def _short(value: Any, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip() or None


def _backed(memo_id: str, quote: Any, transcript: str, evidence: dict[str, dict]) -> list[str]:
    ref = _evidence(memo_id, quote, transcript) if quote else None
    if ref is None:
        return []
    evidence[ref["id"]] = ref
    return [ref["id"]]


def _spoken_day_wins(due: str | None, precision: str, when_text: Any, captured_at: Any, tz_name: Any) -> tuple[str | None, str]:
    """When code can read the day from the words that were said ("el viernes", "en un año"), that
    day wins over the model's arithmetic; the model's clock time, if any, is kept."""
    from app.services.relative_dates import resolve_schedule

    try:
        ref = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00")).astimezone(_zone(tz_name)).date()
    except (TypeError, ValueError):
        return due, precision
    day = resolve_schedule(str(when_text or ""), ref)
    if not day:
        return due, precision
    if due and precision == "time":
        parsed = datetime.fromisoformat(due)
        return datetime.combine(date.fromisoformat(day), parsed.timetz()).isoformat(), "time"
    resolved, _ = _commitment_due(day, tz_name)
    return resolved, "date"


def _next_actions(memo_id: str, raw: Any, transcript: str, evidence: dict[str, dict], tz_name: Any, captured_at: Any = None) -> dict:
    """v8: what the call leads to, ready for the brief, Hoy and the follow-up email. Texts are
    the model's short Spanish; a part whose `needed` the transcript does not back is dropped."""
    raw = raw if isinstance(raw, dict) else {}
    outcome_raw = raw.get("outcome") if isinstance(raw.get("outcome"), dict) else {}
    outcome = None
    if _short(outcome_raw.get("text"), 200):
        outcome = {"text": _short(outcome_raw.get("text"), 200),
                   "evidence_refs": _backed(memo_id, outcome_raw.get("quote"), transcript, evidence)}

    cb = raw.get("callback") if isinstance(raw.get("callback"), dict) else {}
    callback = {"needed": False}
    if cb.get("needed") is True:
        due, precision = (None, "unknown")
        if cb.get("when"):
            due, precision = _commitment_due(cb.get("when"), tz_name)
        due, precision = _spoken_day_wins(due, precision, cb.get("when_text"), captured_at, tz_name)
        callback = {
            "needed": True,
            "who_asked": cb.get("who_asked") if cb.get("who_asked") in _WHO_ASKED else None,
            "when": due,
            "temporal_precision": precision if due else "unknown",
            "when_text": _short(cb.get("when_text"), 60),
            "reason": _short(cb.get("reason"), 120),
            "evidence_refs": _backed(memo_id, cb.get("quote"), transcript, evidence),
        }

    em = raw.get("followup_email") if isinstance(raw.get("followup_email"), dict) else {}
    email = {"needed": False}
    if em.get("needed") is True:
        email = {
            "needed": True,
            "kind": em.get("kind") if em.get("kind") in _EMAIL_KIND else "other",
            "content": _short(em.get("content"), 160),
            "to": _short(em.get("to"), 80),
            "evidence_refs": _backed(memo_id, em.get("quote"), transcript, evidence),
        }

    ref_raw = raw.get("referral") if isinstance(raw.get("referral"), dict) else None
    referral = None
    if ref_raw and (_short(ref_raw.get("name"), 60) or _short(ref_raw.get("role"), 60)):
        referral = {"name": _short(ref_raw.get("name"), 60), "role": _short(ref_raw.get("role"), 60),
                    "evidence_refs": _backed(memo_id, ref_raw.get("quote"), transcript, evidence)}
    return {"outcome": outcome, "callback": callback, "followup_email": email,
            "referral": referral, "hook": _short(raw.get("hook"), 120)}


def _meeting(memo_id: str, raw: Any, transcript: str, evidence: dict[str, dict]) -> dict:
    empty = {"agreed": None, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("agreed"), bool):
        return empty
    ref = _evidence(memo_id, raw.get("quote"), transcript)
    if ref is None:
        return empty
    evidence[ref["id"]] = ref
    starts_at, precision = _meeting_start(raw.get("starts_at")) if raw["agreed"] else (None, "unknown")
    return {**empty, "agreed": raw["agreed"], "starts_at": starts_at, "precision": precision, "evidence_refs": [ref["id"]]}


def _competitor_mentions(memo_id: str, raw: Any, transcript: str, evidence: dict[str, dict]) -> list[dict]:
    """v4: a named competitor only counts with its exact quote; one entry per name."""
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())
        if not name or len(name) > _COMPETITOR_MAX or name.lower() in seen:
            continue
        ref = _evidence(memo_id, item.get("quote"), transcript)
        if ref is None:
            continue
        evidence[ref["id"]] = ref
        seen.add(name.lower())
        out.append({"name": name, "quote": ref["quote"], "evidence_refs": [ref["id"]]})
    return out


def _playbook_observations(
    memo_id: str,
    raw: Any,
    transcript: str,
    evidence: dict[str, dict],
    steps: list[dict],
) -> list[dict]:
    """v4: exactly one observation per playbook step, in the playbook's order.

    met needs the rep's own words, missed needs the moment it should have happened; a
    status the transcript does not back becomes unknown (score_assembly would ignore it
    anyway). A step the model skipped is unknown, so coverage stays honest."""
    by_step: dict[str, dict] = {}
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("step_id") and str(item["step_id"]) not in by_step:
            by_step[str(item["step_id"])] = item
    out: list[dict] = []
    for step in steps:
        step_id = str(step.get("step_id") or "")
        if not step_id:
            continue
        item = by_step.get(step_id) or {}
        status = item.get("status") if item.get("status") in _OBSERVATION else "unknown"
        refs: list[str] = []
        if status in ("met", "missed"):
            finder = _rep_evidence if status == "met" else _evidence
            ref = finder(memo_id, item.get("quote"), transcript)
            if ref is None:
                status = "unknown"
            else:
                evidence[ref["id"]] = ref
                refs = [ref["id"]]
        entry = {
            "step_id": step_id,
            "label": " ".join(str(step.get("label") or step_id).split()),
            "criterion": " ".join(str(step.get("criterion") or "").split()),
            "status": status,
            "quote": evidence[refs[0]]["quote"] if refs else None,
            "evidence_refs": refs,
        }
        reason = " ".join(str(item.get("reason") or "").split())[:_REASON_MAX] or None
        advice = " ".join(str(item.get("advice") or "").split())[:_REASON_MAX] or None
        quality = item.get("quality") if status == "met" and item.get("quality") in _QUALITY else None
        if reason:
            entry["reason"] = reason
        if quality:
            entry["quality"] = quality
        if advice and (status == "missed" or quality == "improvable"):
            entry["advice"] = advice
        out.append(entry)
    return out


def _qualification_observations(
    memo_id: str,
    raw: Any,
    transcript: str,
    evidence: dict[str, dict],
    criteria: list[dict],
) -> list[dict]:
    """v7: exactly one observation per criterion, in the playbook's order.

    found needs the prospect's own words (and carries what they said as a short value);
    missing needs the moment it should have come up; a status the transcript does not back
    becomes unknown. A criterion the model skipped is unknown, so coverage stays honest."""
    by_id: dict[str, dict] = {}
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("criterion_id") and str(item["criterion_id"]) not in by_id:
            by_id[str(item["criterion_id"])] = item
    out: list[dict] = []
    for criterion in criteria:
        criterion_id = str(criterion.get("criterion_id") or "")
        if not criterion_id:
            continue
        item = by_id.get(criterion_id) or {}
        status = item.get("status") if item.get("status") in _QUALIFICATION else "unknown"
        refs: list[str] = []
        value = None
        if status in ("found", "missing"):
            finder = _prospect_evidence if status == "found" else _evidence
            ref = finder(memo_id, item.get("quote"), transcript)
            if ref is None:
                status = "unknown"
            else:
                evidence[ref["id"]] = ref
                refs = [ref["id"]]
        if status == "found":
            text = " ".join(str(item.get("value") or "").split())
            value = text[:_VALUE_MAX].rstrip() or None
        out.append({
            "criterion_id": criterion_id,
            "label": " ".join(str(criterion.get("label") or criterion_id).split()),
            "status": status,
            "value": value,
            "quote": evidence[refs[0]]["quote"] if refs else None,
            "evidence_refs": refs,
        })
    return out


def shape_intelligence(
    memo: dict,
    raw: dict,
    *,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
    playbook_qualification: list[dict] | None = None,
    playbook_objections: list[dict] | None = None,
) -> dict:
    """Keep what the transcript backs. A quote that is not in the text removes its fact."""
    memo_id = str(memo.get("id") or "")
    transcript = str(memo.get("transcript") or "")
    evidence: dict[str, dict] = {}

    interest = raw.get("interest")
    pain = raw.get("pain_confirmed")
    pain_ref = _evidence(memo_id, raw.get("pain_quote"), transcript) if isinstance(pain, bool) else None
    if pain_ref is None:
        pain = None
    else:
        evidence[pain_ref["id"]] = pain_ref

    custom_ids = {
        str(item.get("id")) for item in playbook_objections or [] if isinstance(item, dict) and item.get("id")
    }
    objections = []
    for item in raw.get("objections") or []:
        if not isinstance(item, dict):
            continue
        ref = _evidence(memo_id, item.get("quote"), transcript)
        if ref is None:
            continue
        evidence[ref["id"]] = ref
        kind = item.get("kind") if item.get("kind") in _EPISODE_KIND else "objection"
        allowed = _CATEGORY if kind == "objection" else _OBSTACLE_CATEGORY
        category = item.get("category") if item.get("category") in allowed else "other"
        resolution = item.get("resolution") if item.get("resolution") in _RESOLUTION else "unknown"
        response = None
        response_evidence_refs: list[str] = []
        response_quote = item.get("response")
        if isinstance(response_quote, str) and response_quote.strip():
            response_ref = _rep_evidence(memo_id, response_quote, transcript)
            if response_ref is not None:
                evidence[response_ref["id"]] = response_ref
                response = {"text": response_ref["quote"]}
                response_evidence_refs = [response_ref["id"]]
        entry = {
            "id": f"obj-{ref['id'][3:]}",
            "category": category,
            "kind": kind,
            "resolution": resolution,
            "quote": ref["quote"],
            "evidence_refs": [ref["id"]],
            # T10/SCORING_OBJECTION_CREDIT_ENABLED: the rep's own cited reply, and whether the
            # rep spoke again at all after the objection (never invented from a missing turn).
            "response": response,
            "response_evidence_refs": response_evidence_refs,
            "rep_replied_after": _rep_replied_after(transcript, ref["quote"]),
        }
        if prompt_version in _READS_QUALIFICATION:
            # v7: the id of the company's own objection this one clearly is; an id the playbook
            # does not have (or one on an obstacle) is dropped, the category stays a fixed one.
            matched = str(item.get("objection_id") or "").strip()
            entry["objection_id"] = matched if kind == "objection" and matched in custom_ids else None
        objections.append(entry)

    commitments = []
    for item in raw.get("commitments") or []:
        if not isinstance(item, dict):
            continue
        undated = item.get("due_at") is None
        due, precision = (None, "unknown") if undated else _commitment_due(item.get("due_at"), memo.get("timezone"))
        text = " ".join(str(item.get("text") or "").split()).rstrip(".")
        ref = _evidence(memo_id, item.get("quote"), transcript)
        if not (due or undated) or not text or ref is None:
            continue
        evidence[ref["id"]] = ref
        commitments.append({
            "id": f"com-{ref['id'][3:]}",
            "kind": item.get("kind") if item.get("kind") in _KIND else "other",
            "origin": item.get("origin") if item.get("origin") in _ORIGIN else "rep_promise",
            "text": text[:_TEXT_MAX].rstrip(),
            "due_at": due,
            "temporal_precision": precision,
            "evidence_refs": [ref["id"]],
        })

    meeting = _meeting(memo_id, raw.get("meeting"), transcript, evidence)
    competitors: list[dict] = []
    observations: list[dict] = []
    qualification: list[dict] = []
    if prompt_version in _READS_STEPS:
        competitors = _competitor_mentions(memo_id, raw.get("competitor_mentions"), transcript, evidence)
        if playbook_steps:
            observations = _playbook_observations(
                memo_id, raw.get("playbook_observations"), transcript, evidence, playbook_steps,
            )
        if prompt_version in _READS_QUALIFICATION and playbook_qualification:
            qualification = _qualification_observations(
                memo_id, raw.get("qualification_observations"), transcript, evidence, playbook_qualification,
            )
    backed = bool(objections or commitments or interest in _INTEREST)
    shaped = {
        "version": 1,
        "input_revision": revision_for_memo(memo),
        "status": "ready" if backed else "partial",
        "interest": interest if interest in _INTEREST else None,
        "pain_confirmed": pain,
        "objections": objections,
        "commitments": commitments,
        "meeting": meeting,
        "competitor_mentions": competitors,
        "playbook_observations": observations,
        "evidence": list(evidence.values()),
        "prompt_version": prompt_version,
    }
    if prompt_version in _READS_QUALIFICATION:
        shaped["qualification_observations"] = qualification
    if prompt_version == CALL_READING_PROMPT_VERSION:
        shaped["next"] = _next_actions(
            memo_id, raw.get("next"), transcript, evidence, memo.get("timezone"),
            memo.get("capture_started_at") or memo.get("created_at"),
        )
        shaped["evidence"] = list(evidence.values())
    return shaped


def build_messages(
    memo: dict,
    *,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
    playbook_qualification: list[dict] | None = None,
    playbook_objections: list[dict] | None = None,
    transcript: str | None = None,
    call: dict | None = None,
) -> list[dict]:
    """`transcript` (v8) is the You:/Them: copy the call reading produced; `call` its verdict."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    payload = {
        "captured_at": str(memo.get("capture_started_at") or memo.get("created_at") or ""),
        "timezone": str(memo.get("timezone") or _DEFAULT_TZ),
        "summary": str((extraction or {}).get("summary") or ""),
    }
    if call:
        payload["call"] = {
            "call_type": call.get("call_type"),
            "phase_reached": call.get("phase_reached"),
            "reached_conversation": call.get("reached_conversation"),
            "roles_marked": call.get("roles_marked", True),
        }
    payload["transcript"] = str(transcript if transcript is not None else memo.get("transcript") or "")
    if prompt_version in _READS_STEPS and playbook_steps:
        payload["playbook_steps"] = []
        for step in playbook_steps:
            if not step.get("step_id"):
                continue
            if prompt_version == CALL_READING_PROMPT_VERSION and step_outcome(step):
                continue  # the rep declares it after the call; the model never judges it
            row = {
                "step_id": str(step.get("step_id") or ""),
                "label": str(step.get("label") or ""),
                "criterion": str(step.get("criterion") or ""),
            }
            example = " ".join(str(step.get("example") or "").split())
            if example and prompt_version == CALL_READING_PROMPT_VERSION:
                row["example"] = example
            payload["playbook_steps"].append(row)
    if prompt_version in _READS_QUALIFICATION:
        if playbook_qualification:
            payload["playbook_qualification"] = [
                {
                    key: value
                    for key, value in (
                        ("criterion_id", str(item.get("criterion_id") or "")),
                        ("label", str(item.get("label") or "")),
                        ("good", str(item.get("good") or "")),
                    )
                    if value or key != "good"
                }
                for item in playbook_qualification
                if item.get("criterion_id")
            ]
        if playbook_objections:
            payload["playbook_objections"] = [
                {"id": str(item.get("id") or ""), "label": str(item.get("label") or ""), "trigger": str(item.get("trigger") or "")}
                for item in playbook_objections
                if item.get("id")
            ]
    system = prompt_path(prompt_version).read_text(encoding="utf-8")
    addendum = prompt_path(f"{prompt_version}_no_reasoning")
    if call is not None and addendum.exists() and _judge_without_reasoning():
        system += addendum.read_text(encoding="utf-8")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _judge_without_reasoning() -> bool:
    from app.services.llm.shared import answers_without_reasoning

    return answers_without_reasoning(settings.INTELLIGENCE_MODEL, getattr(settings, "INTELLIGENCE_JUDGE_EFFORT", None))


def is_current(memo: dict) -> bool:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    block = (extraction or {}).get("intelligence")
    return (
        isinstance(block, dict)
        and block.get("prompt_version") in CURRENT_PROMPT_VERSIONS
        and block.get("input_revision") == revision_for_memo(memo)
    )


def pinned_playbook_steps(supabase: Any, memo: dict) -> list[dict]:
    """The steps of the playbook version pinned on this memo; [] when none or unreadable."""
    version_id = memo.get("playbook_version_id")
    if not version_id:
        return []
    try:
        rows = (
            supabase.table("playbook_versions")
            .select("steps")
            .eq("id", str(version_id))
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        return []
    steps = (rows[0] if rows else {}).get("steps") or []
    return [step for step in steps if isinstance(step, dict) and step.get("step_id")]


def playbook_qualification_inputs(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(criteria, custom objections) from a pinned version row, tolerant of anything missing:
    no `qualification` column, an empty one, or an entry without a label."""
    row = rows[0] if rows else {}
    criteria: list[dict] = []
    for item in row.get("qualification") or []:
        if not isinstance(item, dict):
            continue
        criterion_id = str(item.get("criterion_id") or "").strip()
        label = " ".join(str(item.get("label") or "").split())
        if not criterion_id or not label or any(c["criterion_id"] == criterion_id for c in criteria):
            continue
        criterion = {"criterion_id": criterion_id, "label": label}
        good = " ".join(str(item.get("good") or "").split())
        if good:
            criterion["good"] = good
        criteria.append(criterion)
    objections: list[dict] = []
    for entry in row.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("category") != "custom":
            continue
        entry_id = str(entry.get("entry_id") or "").strip()
        slug = entry_id[len(_CUSTOM_ENTRY_PREFIX):] if entry_id.startswith(_CUSTOM_ENTRY_PREFIX) else ""
        label = " ".join(str(entry.get("label") or "").split())
        if not slug or not label or any(o["id"] == slug for o in objections):
            continue
        objections.append({"id": slug, "label": label, "trigger": " ".join(str(entry.get("trigger") or "").split())})
    return criteria[:_MAX_CRITERIA], objections[:_MAX_CUSTOM_OBJECTIONS]


def pinned_qualification_inputs(supabase: Any, memo: dict) -> tuple[list[dict], list[dict]]:
    """The qualification criteria and the company's own objections of the version pinned on
    this memo. ([], []) when nothing is pinned, the column is not there yet or the read fails."""
    version_id = memo.get("playbook_version_id")
    if not version_id:
        return [], []
    rows: list[dict] = []
    for columns in ("qualification,entries", "entries"):
        try:
            rows = (
                supabase.table("playbook_versions").select(columns).eq("id", str(version_id)).limit(1).execute()
            ).data or []
            break
        except Exception:
            continue
    return playbook_qualification_inputs(rows)


def pinned_playbook_answer_categories(supabase: Any, memo: dict) -> frozenset[str] | None:
    """Objection categories the pinned playbook version has an answer for. None when there is
    no pin or it cannot be read (the score then keeps counting every category)."""
    version_id = memo.get("playbook_version_id")
    if not version_id:
        return None
    try:
        rows = (
            supabase.table("playbook_versions")
            .select("entries")
            .eq("id", str(version_id))
            .limit(1)
            .execute()
        ).data or []
    except Exception:
        return None
    if not rows:
        return None
    return frozenset(
        str(entry.get("category") or "").strip().lower()
        for entry in (rows[0].get("entries") or [])
        if isinstance(entry, dict) and str(entry.get("guidance") or "").strip() and entry.get("category")
    )


def _needs_upgrade(memo: dict, planned_version: str) -> bool:
    """A v3 block is re-read once the company is on v4 (so the backfill script can add step
    observations to past conversations), and a v3-v6 block once it is on v7 (qualification and
    the company's own objections). A newer block is never downgraded when the flag goes off."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    stored = ((extraction or {}).get("intelligence") or {}).get("prompt_version")
    if planned_version == CALL_READING_PROMPT_VERSION:
        return stored in (PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION, QUALIFICATION_PROMPT_VERSION)
    if planned_version == QUALIFICATION_PROMPT_VERSION:
        return stored in (PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION)
    return planned_version == OBSERVATIONS_PROMPT_VERSION and stored == PROMPT_VERSION


def extraction_plan(supabase: Any, memo: dict) -> tuple[str, list[dict]]:
    """(prompt version, playbook steps) for this memo's company."""
    from app.services.feature_flags import is_enabled

    if is_enabled(supabase, memo.get("company_id"), CALL_READING_FLAG):
        return CALL_READING_PROMPT_VERSION, pinned_playbook_steps(supabase, memo)
    if is_enabled(supabase, memo.get("company_id"), QUALIFICATION_FLAG):
        return QUALIFICATION_PROMPT_VERSION, pinned_playbook_steps(supabase, memo)
    if not is_enabled(supabase, memo.get("company_id"), OBSERVATIONS_FLAG):
        return PROMPT_VERSION, []
    return OBSERVATIONS_PROMPT_VERSION, pinned_playbook_steps(supabase, memo)


@scoped("intelligence")
async def ensure_intelligence(supabase: Any, memo_id: str, *, llm: Any = None) -> dict:
    """Idempotent per revision. A failure leaves the memo as it was."""
    result = supabase.table("memos").select("*").eq("id", str(memo_id)).limit(1).execute()
    rows = list(getattr(result, "data", None) or [])
    if not rows:
        return {"status": "missing"}
    memo = rows[0]
    prompt_version, playbook_steps = extraction_plan(supabase, memo)
    if is_current(memo) and not _needs_upgrade(memo, prompt_version):
        return {"status": "current"}
    if llm is None:
        from app.services.llm import LLMClient

        llm = LLMClient()
    qualification: list[dict] = []
    objections: list[dict] = []
    if prompt_version in _READS_QUALIFICATION:
        qualification, objections = pinned_qualification_inputs(supabase, memo)
    context = call_context(supabase, memo) if prompt_version == CALL_READING_PROMPT_VERSION else {}
    shaped, meta = await extract_intelligence(
        memo, llm, prompt_version=prompt_version, playbook_steps=playbook_steps,
        playbook_qualification=qualification, playbook_objections=objections, **context,
    )
    if shaped is None:
        return {"status": "no_transcript"}
    from app.services.intelligence.interpret import extraction_with_intelligence

    stored = extraction_with_intelligence(memo.get("extraction"), shaped)
    supabase.table("memos").update({"extraction": stored}).eq("id", str(memo_id)).execute()
    from app.services.memo_extraction_hooks import refresh_meeting_proposal

    memo_with_extraction = {**memo, "extraction": stored}
    refresh_meeting_proposal(supabase, memo_with_extraction)
    from app.services.memo_extraction_hooks import refresh_coaching_from_intelligence

    refresh_coaching_from_intelligence(supabase, memo_with_extraction, stored)
    return {"status": "stored", "meta": meta, "intelligence": shaped}


_tasks: set = set()


def schedule_intelligence(supabase: Any, memo_id: str, company_id: str | None = None) -> bool:
    """After an extraction save. Off by the memo company's flag; never blocks the save."""
    import asyncio
    import logging

    from app.services.feature_flags import is_enabled

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    if not company_id:
        try:
            result = supabase.table("memos").select("company_id").eq("id", str(memo_id)).limit(1).execute()
            rows = list(getattr(result, "data", None) or [])
            company_id = rows[0].get("company_id") if rows else None
        except Exception:
            company_id = None
    if not is_enabled(supabase, company_id, "INTELLIGENCE_EXTRACT_ENABLED"):
        return False

    async def run():
        status = None
        try:
            status = (await ensure_intelligence(supabase, str(memo_id))).get("status")
        except Exception:
            logging.getLogger(__name__).exception("intelligence extraction failed", extra={"memo_id": str(memo_id)})
        if status not in ("stored", "current"):
            from app.services import memo_extraction_hooks

            try:
                memo_extraction_hooks.publish_coaching_without_intelligence(supabase, str(memo_id))
            except Exception:
                logging.getLogger(__name__).exception("coaching fallback failed", extra={"memo_id": str(memo_id)})

    task = loop.create_task(run(), name=f"intelligence:{memo_id}")  # followup._c04_task waits on it
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


def call_context(supabase: Any, memo: dict) -> dict:
    """What the call reading needs to tell the rep from the prospect: the rep's name, the
    company they sell for, and how many earlier conversations exist with this contact.
    Each read is best effort; a missing value only makes the reading less sure."""
    context: dict[str, Any] = {}
    try:
        rows = (
            supabase.table("user_profiles").select("full_name").eq("id", str(memo.get("user_id") or "")).limit(1).execute().data
            or []
        )
        if rows and rows[0].get("full_name"):
            context["rep_name"] = str(rows[0]["full_name"])
    except Exception:
        pass
    try:
        rows = supabase.table("companies").select("name").eq("id", str(memo.get("company_id") or "")).limit(1).execute().data or []
        if rows and rows[0].get("name"):
            context["company_name"] = str(rows[0]["name"])
    except Exception:
        pass
    contact_id = memo.get("hubspot_contact_id")
    if contact_id:
        try:
            rows = (
                supabase.table("memos").select("id")
                .eq("company_id", str(memo.get("company_id") or "")).eq("hubspot_contact_id", str(contact_id))
                .lt("created_at", str(memo.get("created_at") or "")).limit(20).execute().data
                or []
            )
            context["prior_conversations"] = len(rows)
        except Exception:
            pass
    return context


def _stored_reading(memo: dict) -> tuple[dict, str] | None:
    """The call reading the CRM pass already made for this transcript (same prompt version, same
    turns), with its You:/Them: transcript; None when it does not fit and the call must be read."""
    from app.services.intelligence.call_reading import PROMPT_VERSION as READING_VERSION, relabel, split_turns

    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    reading = extraction.get("call_reading") if isinstance(extraction.get("call_reading"), dict) else None
    if not reading or reading.get("version") != READING_VERSION:
        return None
    turns = split_turns(str(memo.get("transcript") or ""))
    if not turns or reading.get("turn_count") != len(turns):
        return None
    reading = {k: v for k, v in reading.items() if k != "rep_company"}
    if len(turns) < 2:
        return reading, str(memo.get("transcript") or "")
    return reading, relabel(turns, reading)


def _skipped_steps(raw: Any, messages: list[dict]) -> bool:
    """Whether the reply misses a step it was asked to judge."""
    try:
        asked = {s["step_id"] for s in json.loads(messages[1]["content"]).get("playbook_steps") or []}
    except (ValueError, KeyError, TypeError):
        return False
    got = {
        str(item.get("step_id")) for item in (raw or {}).get("playbook_observations") or []
        if isinstance(item, dict) and item.get("status")
    } if isinstance(raw, dict) else set()
    return bool(asked - got)


def _mark_outcome_steps(observations: list[dict], steps: list[dict]) -> list[dict]:
    """A step the rep's declared outcome settles (a meeting booked) carries no model verdict:
    it waits, unknown, for `rep_outcome`."""
    outcomes = {str(step.get("step_id")): step_outcome(step) for step in steps if step.get("step_id")}
    out = []
    for item in observations:
        outcome = outcomes.get(item["step_id"])
        if not outcome:
            out.append(item)
            continue
        out.append({
            **{k: v for k, v in item.items() if k not in ("advice", "reason")},
            "status": "unknown", "quote": None, "evidence_refs": [],
            "judged_by": "rep_outcome", "outcome": outcome,
        })
    return out


def _apply_call_reading(observations: list[dict], call: dict) -> list[dict]:
    """What the call type settles on its own: no conversation means nothing to judge, and a
    call that stopped at the door (bad moment, gatekeeper, wrong person) only had an opening."""
    from app.services.intelligence.call_reading import CONTINUES_EARLIER, NOT_JUDGED, OPENING_ONLY

    if not call.get("reached_conversation") or call.get("call_type") in NOT_JUDGED:
        # Nothing to judge: every step, including one the rep's outcome settles, is not applicable.
        return [
            item if item["status"] == "not_applicable"
            else {**{k: v for k, v in item.items() if k not in ("advice", "judged_by", "outcome")},
                  "status": "not_applicable", "quote": None, "evidence_refs": []}
            for item in observations
        ]
    if call.get("call_type") in OPENING_ONLY | CONTINUES_EARLIER:
        # Only the opening is required: a call stopped at the door, or a follow-up whose
        # discovery was the earlier conversation's job. A step done anyway still counts as done;
        # not doing it is never a miss.
        first = observations[0]["step_id"] if observations else None
        door = call.get("call_type") in OPENING_ONLY  # a follow-up can still book the meeting
        out = []
        for item in observations:
            if item.get("judged_by") and door:
                out.append({**{k: v for k, v in item.items() if k not in ("judged_by", "outcome")},
                            "status": "not_applicable", "quote": None, "evidence_refs": []})
            elif item["step_id"] == first or item["status"] != "missed" or item.get("judged_by"):
                out.append(item)
            else:
                out.append({**{k: v for k, v in item.items() if k != "advice"},
                            "status": "not_applicable", "quote": None, "evidence_refs": []})
        return out
    return observations


async def extract_intelligence(
    memo: dict,
    llm: Any,
    *,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
    playbook_qualification: list[dict] | None = None,
    playbook_objections: list[dict] | None = None,
    rep_name: str | None = None,
    company_name: str | None = None,
    prior_conversations: int | None = None,
) -> tuple[dict | None, dict]:
    """None when there is nothing to read. Metadata carries model and tokens for cost.
    v8 reads the call first (roles, type, phase) and judges the You:/Them: transcript."""
    if not str(memo.get("transcript") or "").strip():
        return None, {}
    call = None
    transcript = None
    reading_meta: dict = {}
    reused = _stored_reading(memo) if prompt_version == CALL_READING_PROMPT_VERSION else None
    if reused is not None:
        call, transcript = reused
    elif prompt_version == CALL_READING_PROMPT_VERSION:
        from app.services.intelligence.call_reading import read_call

        call, transcript, reading_meta = await read_call(
            str(memo.get("transcript") or ""), llm,
            model=settings.INTELLIGENCE_MODEL,
            captured_at=str(memo.get("capture_started_at") or memo.get("created_at") or ""),
            rep_name=rep_name, company_name=company_name, prior_conversations=prior_conversations,
        )
    messages = build_messages(
        memo, prompt_version=prompt_version, playbook_steps=playbook_steps,
        playbook_qualification=playbook_qualification, playbook_objections=playbook_objections,
        transcript=transcript, call=call,
    )
    effort = getattr(settings, "INTELLIGENCE_JUDGE_EFFORT", None) if call else None
    judge = {"reasoning_effort": effort} if effort else {}
    from app.services.intelligence.call_reading import NOT_JUDGED

    if call and (not call.get("reached_conversation") or call.get("call_type") == "no_conversation"):
        # Nobody answered for real: there is nothing to judge or to act on, and the second pass
        # would be paid for an empty answer.
        raw = {}
    else:
        raw = await llm.chat_json(messages, model=settings.INTELLIGENCE_MODEL, temperature=0.0,
                                  timeout=90.0 if call else 60.0, **judge)
    if call and raw and _skipped_steps(raw, messages):
        # v8: a step the model left out would read as "no evidence" on a call where it is plain;
        # one more read is cheaper than a wrong coaching line.
        raw = await llm.chat_json(messages, model=settings.INTELLIGENCE_MODEL, temperature=0.0, timeout=90.0, **judge)
    meta = dict(getattr(llm, "last_call_meta", None) or {})
    if reading_meta:
        meta["call_reading"] = reading_meta
    read_memo = {**memo, "transcript": transcript} if transcript is not None else memo
    shaped = shape_intelligence(
        read_memo, raw if isinstance(raw, dict) else {}, prompt_version=prompt_version, playbook_steps=playbook_steps,
        playbook_qualification=playbook_qualification, playbook_objections=playbook_objections,
    )
    if call:
        shaped["call"] = call
        shaped["playbook_observations"] = _apply_call_reading(
            _mark_outcome_steps(shaped["playbook_observations"], playbook_steps or []), call,
        )
        if raw and getattr(settings, "JEV_DECISIONS_ENABLED", False):
            await _apply_jev_decisions(shaped, transcript if transcript is not None else str(memo.get("transcript") or ""))
    return shaped, meta


async def _apply_jev_decisions(shaped: dict, transcript: str) -> None:
    """Jev answers follow-up email / callback / meeting yes-no; an "unknown" (low confidence or Jev
    down) keeps the verdict the judge gave. Days, reasons and quotes stay the judge's."""
    from app.services.llm import JevClient
    from app.services.llm.jev_schemas import DECISION_QUESTIONS

    try:
        result = await JevClient().classify_questions({"transcript": transcript}, DECISION_QUESTIONS)
    except Exception:
        logging.getLogger(__name__).warning("jev decisions failed; keeping the judge's", exc_info=True)
        return
    answers = result.get("answers") or {}
    nxt = shaped.get("next") if isinstance(shaped.get("next"), dict) else None
    if nxt is not None:
        for key, block in (("followup_email", "followup_email"), ("callback", "callback")):
            if answers.get(key) in ("yes", "no") and isinstance(nxt.get(block), dict):
                nxt[block] = {**nxt[block], "needed": answers[key] == "yes"}
    if answers.get("meeting_agreed") in ("yes", "no") and isinstance(shaped.get("meeting"), dict):
        shaped["meeting"] = {**shaped["meeting"], "agreed": True if answers["meeting_agreed"] == "yes" else None}
