"""C04 facts from one transcript: interest, objections, commitments. One model call per revision."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.services.intelligence.worker import revision_for_memo

PROMPT_VERSION = "intelligence_v5"
# v6 = v5 + named competitors + one observation per playbook step (PLAYBOOK_OBSERVATIONS_ENABLED,
# per company). Both versions produce the same shape, so both count as current: a company
# turning the flag on gets v6 on new conversations; older ones keep their v5 facts.
# v5/v6 are v3/v4 plus the objection/obstacle split: `kind` "objection" (a concern about the offer)
# or "obstacle" (a practical block: bad moment, gatekeeper, wrong person, needs to consult).
OBSERVATIONS_PROMPT_VERSION = "intelligence_v6"
OBSERVATIONS_FLAG = "PLAYBOOK_OBSERVATIONS_ENABLED"
CURRENT_PROMPT_VERSIONS = frozenset({PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION})
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


def _evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    text = " ".join(str(quote or "").split())
    if not text or text not in " ".join(transcript.split()):
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


def _rep_evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    """T10: an objection's response only counts when it is the rep's own words. When the
    transcript has no speaker markers, fall back to the plain substring check."""
    ref = _evidence(memo_id, quote, transcript)
    if ref is None:
        return None
    turns = _turns(transcript)
    if turns is None:
        return ref
    rep_text = " ".join(" ".join(text.split()) for speaker, text in turns if speaker == "You")
    if ref["quote"] not in rep_text:
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
        out.append({
            "step_id": step_id,
            "label": " ".join(str(step.get("label") or step_id).split()),
            "criterion": " ".join(str(step.get("criterion") or "").split()),
            "status": status,
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
        objections.append({
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
        })

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
    if prompt_version == OBSERVATIONS_PROMPT_VERSION:
        competitors = _competitor_mentions(memo_id, raw.get("competitor_mentions"), transcript, evidence)
        if playbook_steps:
            observations = _playbook_observations(
                memo_id, raw.get("playbook_observations"), transcript, evidence, playbook_steps,
            )
    backed = bool(objections or commitments or interest in _INTEREST)
    return {
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


def build_messages(
    memo: dict,
    *,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
) -> list[dict]:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    payload = {
        "captured_at": str(memo.get("capture_started_at") or memo.get("created_at") or ""),
        "timezone": str(memo.get("timezone") or _DEFAULT_TZ),
        "summary": str((extraction or {}).get("summary") or ""),
        "transcript": str(memo.get("transcript") or ""),
    }
    if prompt_version == OBSERVATIONS_PROMPT_VERSION and playbook_steps:
        payload["playbook_steps"] = [
            {
                "step_id": str(step.get("step_id") or ""),
                "label": str(step.get("label") or ""),
                "criterion": str(step.get("criterion") or ""),
            }
            for step in playbook_steps
            if step.get("step_id")
        ]
    return [
        {"role": "system", "content": prompt_path(prompt_version).read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


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


def _needs_upgrade(memo: dict, planned_version: str) -> bool:
    """A v3 block is re-read once the company is on v4 (so the backfill script can add step
    observations to past conversations). A v4 block is never downgraded when the flag goes off."""
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    stored = ((extraction or {}).get("intelligence") or {}).get("prompt_version")
    return planned_version == OBSERVATIONS_PROMPT_VERSION and stored == PROMPT_VERSION


def extraction_plan(supabase: Any, memo: dict) -> tuple[str, list[dict]]:
    """(prompt version, playbook steps) for this memo's company."""
    from app.services.feature_flags import is_enabled

    if not is_enabled(supabase, memo.get("company_id"), OBSERVATIONS_FLAG):
        return PROMPT_VERSION, []
    return OBSERVATIONS_PROMPT_VERSION, pinned_playbook_steps(supabase, memo)


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
    shaped, meta = await extract_intelligence(memo, llm, prompt_version=prompt_version, playbook_steps=playbook_steps)
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


async def extract_intelligence(
    memo: dict,
    llm: Any,
    *,
    prompt_version: str = PROMPT_VERSION,
    playbook_steps: list[dict] | None = None,
) -> tuple[dict | None, dict]:
    """None when there is nothing to read. Metadata carries model and tokens for cost."""
    if not str(memo.get("transcript") or "").strip():
        return None, {}
    raw = await llm.chat_json(
        build_messages(memo, prompt_version=prompt_version, playbook_steps=playbook_steps),
        model=settings.INTELLIGENCE_MODEL,
        temperature=0.0,
        timeout=60.0,
    )
    meta = dict(getattr(llm, "last_call_meta", None) or {})
    shaped = shape_intelligence(
        memo, raw if isinstance(raw, dict) else {}, prompt_version=prompt_version, playbook_steps=playbook_steps,
    )
    return shaped, meta
