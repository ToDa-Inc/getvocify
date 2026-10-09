"""Draft the follow-up email as soon as a memo's extraction is ready.

Runs in the background, once per memo, and never blocks or fails the memo pipeline.
Single-flight mirrors pipeline_lease.py: an in-process guard for same-instant bursts
plus a DB lease (followup_run_started_at) that survives restarts.

When C04 is running for the memo in this process, the draft waits for it (up to
C04_WAIT_S) so it promises what the CRM and Hoy show.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.services.usage import scoped
from app.config import settings
from app.services.feature_flags import is_enabled
from app.services.text_guard import email_filler, spoken_language, strip_email_filler, word_count
from app.services.followup_logic import (
    DEFAULT_TZ,
    PROMPT_VERSION,
    PROMPT_VERSION_BY_FLOW,
    build_messages,
    c04_facts,
    is_eligible,
    parse_draft,
    should_generate,
    voice_texts,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_PATH = PROMPTS_DIR / f"{PROMPT_VERSION}.md"  # kept for scripts/eval_followup.py (the v2/off eval)
# LLM_TIMEOUT_S is per attempt and providers retry, so LEASE (and STALE_GENERATING) must cover
# C04_WAIT_S plus every attempt; otherwise the GET safety net reclaims and pays a second call.
LEASE = timedelta(minutes=4)
LLM_TIMEOUT_S = 25.0
C04_WAIT_S = 30.0
FLAG = "FOLLOWUP_ENABLED"
BY_FLOW_FLAG = "FOLLOWUP_BY_FLOW_ENABLED"
# is_current() hashes every memo field C04 reads, so read the row the way ensure_intelligence does.
MEMO_COLUMNS = "*"

_guard = threading.Lock()
_live: set[str] = set()
_tasks: set[asyncio.Task] = set()  # hold references so fire-and-forget tasks are not garbage-collected


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _first(result: Any) -> Optional[dict]:
    rows = getattr(result, "data", None) or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def _prompt_path(version: str) -> Path:
    return PROMPTS_DIR / f"{version}.md"


def _sales_strategy(supabase: Any, company_id: Optional[str]) -> Optional[str]:
    """companies.sales_strategy (D10), tolerant of the column not existing yet."""
    if not company_id:
        return None
    try:
        row = _first(supabase.table("companies").select("sales_strategy").eq("id", company_id).limit(1).execute())
    except Exception:
        return None
    return (row or {}).get("sales_strategy") or None


def _acquire(supabase: Any, memo_id: str, run_id: str, now: datetime, prompt_version: str) -> bool:
    started = now.isoformat()
    cutoff = (now - LEASE).isoformat()
    q = (
        supabase.table("memos")
        .update({
            "followup": {"status": "generating", "started_at": started, "run_id": run_id,
                         "prompt_version": prompt_version},
            "followup_run_started_at": started,
        })
        .eq("id", memo_id)
    )
    if hasattr(q, "or_"):  # same guard as pipeline_lease.py; without it: in-process single-flight only
        q = q.or_(f"followup.is.null,followup_run_started_at.lt.{cutoff}")
    q.execute()
    # PostgREST re-applies the PATCH filter to RETURNING (see pipeline_lease.py), so an
    # empty result does not mean we lost. Confirm ownership by primary key.
    row = _first(supabase.table("memos").select("followup").eq("id", memo_id).limit(1).execute())
    return bool(row) and (row.get("followup") or {}).get("run_id") == run_id


def _finish(supabase: Any, memo_id: str, run_id: str, followup: dict) -> None:
    (
        supabase.table("memos")
        .update({"followup": followup, "followup_run_started_at": None})
        .eq("id", memo_id)
        .eq("followup->>run_id", run_id)  # a reclaimed lease is not ours to overwrite
        .execute()
    )


def _read_memo(supabase: Any, memo_id: str) -> Optional[dict]:
    return _first(supabase.table("memos").select(MEMO_COLUMNS).eq("id", memo_id).limit(1).execute())


def _c04_task(memo_id: str) -> Optional[asyncio.Task]:
    """The C04 run schedule_intelligence started for this memo, if it is still going."""
    name = f"intelligence:{memo_id}"
    return next((task for task in asyncio.all_tasks() if task.get_name() == name and not task.done()), None)


async def _after_c04(supabase: Any, memo_id: str, memo: dict) -> dict:
    """Success or failure both release the draft; a slow C04 keeps running and lands later."""
    task = _c04_task(memo_id)
    if task is None:
        return memo
    await asyncio.wait({task}, timeout=C04_WAIT_S)
    return _read_memo(supabase, memo_id) or memo


def _rep_timezone(user_id: str) -> str:
    from app.services.coaching.brief_preferences import read_preference

    try:
        return read_preference(str(user_id)).get("timezone") or DEFAULT_TZ
    except Exception:
        return DEFAULT_TZ


def _facts(memo: dict) -> Optional[dict]:
    from app.services.intelligence.extract import is_current

    if not is_current(memo):
        return None
    return c04_facts(memo["extraction"]["intelligence"], _rep_timezone(memo.get("user_id")))


MIN_WORDS_AFTER_STRIP = 25
MIN_BODY_WORDS, MAX_BODY_WORDS = 60, 120  # the prompt's range (followup_v2/v3 "never under 60 or over 120")
LENGTH_RETRIES = 2


def _effort() -> dict:
    effort = getattr(settings, "FOLLOWUP_REASONING_EFFORT", None)
    return {"reasoning_effort": effort} if effort else {}


async def compose(llm: Any, messages: list[dict]) -> Optional[dict]:
    """The model call every draft makes, evals included.

    Guards, in order: a draft in another language than the call is asked for again in the call's
    language; a draft carrying a known filler phrase ("quedo a tu disposición", "gran oportunidad"…)
    is asked for once more, naming the phrases, and whatever still slips through is dropped sentence
    by sentence as long as a real email remains; a body under MIN_BODY_WORDS is asked for again
    with its word count (a model that answers without reasoning does not count words)."""
    want = _conversation_language(messages)
    messages = _with_language(messages, want)
    payload = await llm.chat_json(messages, model=settings.FOLLOWUP_MODEL, temperature=0.4, timeout=LLM_TIMEOUT_S, **_effort())
    draft = parse_draft(payload)
    if not draft:
        return draft
    if want and spoken_language(draft["body"]) not in (None, want):
        draft = await _in_language(llm, messages, payload, draft, want)
    found = email_filler(f"{draft['subject']}\n{draft['body']}")
    if found:
        retry = [
            *messages,
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
            {
                "role": "user",
                "content": "Rewrite it without these phrases, keeping every fact, the tone and the "
                f"length: {'; '.join(found)}. Return the same JSON.",
            },
        ]
        try:
            second = parse_draft(
                await llm.chat_json(retry, model=settings.FOLLOWUP_MODEL, temperature=0.4, timeout=LLM_TIMEOUT_S, **_effort())
            )
        except Exception:
            logger.warning("followup: filler retry failed; stripping instead", exc_info=True)
            second = None
        draft = second or draft
        if email_filler(draft["body"]):
            stripped = strip_email_filler(draft["body"])
            if word_count(stripped) >= MIN_WORDS_AFTER_STRIP:
                draft = {**draft, "body": stripped}
    for _ in range(LENGTH_RETRIES):
        if word_count(draft["body"]) >= MIN_BODY_WORDS:
            break
        draft = await _lengthen(llm, messages, payload, draft)
    if want and not draft.get("language"):
        draft = {**draft, "language": want}
    return draft


_LANGUAGE_NAMES = {"es": "Spanish from Spain", "en": "English"}


def _with_language(messages: list[dict], want: Optional[str]) -> list[dict]:
    """The call's language as an explicit field: voice samples in another language pull a model
    that does not reason towards theirs. Unchanged when the language is unclear."""
    if not want:
        return messages
    try:
        user = json.loads(messages[-1]["content"])
    except (ValueError, KeyError, TypeError):
        return messages
    if not isinstance(user, dict):
        return messages
    user["email_language"] = _LANGUAGE_NAMES[want]
    return [*messages[:-1], {**messages[-1], "content": json.dumps(user, ensure_ascii=False)}]


def _conversation_language(messages: list[dict]) -> Optional[str]:
    try:
        transcript = json.loads(messages[-1]["content"]).get("transcript") or ""
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return None
    return spoken_language(transcript)


async def _in_language(llm: Any, messages: list[dict], payload: object, draft: dict, want: str) -> dict:
    """A draft in another language than the call is asked for once more in the call's language."""
    retry = [
        *messages,
        {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        {"role": "user", "content": f"The conversation is in {_LANGUAGE_NAMES[want]}: rewrite subject and body "
         f'in {_LANGUAGE_NAMES[want]}, keeping every fact. Return the same JSON with "language": "{want}".'},
    ]
    try:
        second = parse_draft(
            await llm.chat_json(retry, model=settings.FOLLOWUP_MODEL, temperature=0.4, timeout=LLM_TIMEOUT_S, **_effort())
        )
    except Exception:
        logger.warning("followup: language retry failed; keeping the draft", exc_info=True)
        return draft
    if second and spoken_language(second["body"]) in (None, want):
        return {**second, "language": second.get("language") or want}
    return draft


async def _lengthen(llm: Any, messages: list[dict], payload: object, draft: dict) -> dict:
    """A model that answers without reasoning does not count words: a body under MIN_BODY_WORDS
    is asked for once more with its count. The longer draft wins only if it is no longer short."""
    words = word_count(draft["body"])
    retry = [
        *messages,
        {"role": "assistant", "content": json.dumps(draft, ensure_ascii=False)},  # the draft as it stands now
        {
            "role": "user",
            "content": f"The body has {words} words; it must have at least 75 and at most "
            f"{MAX_BODY_WORDS - 10}, greeting and sign-off included (aim for about 90). Add concrete content "
            "from the call (what was agreed, the next step and its day, what will be sent), never "
            'filler. Return the same JSON, with "language".',
        },
    ]
    try:
        second = parse_draft(
            await llm.chat_json(retry, model=settings.FOLLOWUP_MODEL, temperature=0.4, timeout=LLM_TIMEOUT_S, **_effort())
        )
    except Exception:
        logger.warning("followup: length retry failed; keeping the short draft", exc_info=True)
        return draft
    if second and MIN_BODY_WORDS <= word_count(second["body"]) <= MAX_BODY_WORDS and not email_filler(second["body"]):
        return {**second, "language": second.get("language") or draft.get("language")}
    return draft


async def _draft(supabase: Any, memo: dict, llm: Any, *, prompt_version: str, by_flow: bool) -> Optional[dict]:
    profile = _first(
        supabase.table("user_profiles").select("full_name,writing_samples")
        .eq("id", memo["user_id"]).limit(1).execute()
    ) or {}
    extraction = memo.get("extraction") or {}
    messages = build_messages(
        system_prompt=_prompt_path(prompt_version).read_text(encoding="utf-8"),
        transcript=memo.get("transcript") or "",
        summary=extraction.get("summary") or "",
        next_steps=list(extraction.get("nextSteps") or []),
        contact_name=extraction.get("contactName"),
        rep_name=profile.get("full_name"),
        voice_samples=voice_texts(profile.get("writing_samples") or []),
        facts=_facts(memo),
        sales_motion_key=memo.get("sales_motion_key") if by_flow else None,
        sales_strategy=_sales_strategy(supabase, memo.get("company_id")) if by_flow else None,
    )
    return await compose(llm, messages)


def read_followup_preference(supabase: Any, user_id: str) -> bool:
    """Whether this rep wants drafts. A missing row or column (before migration 074) means yes."""
    try:
        rows = (
            supabase.table("user_profiles").select("followup_suggestions").eq("id", user_id).limit(1).execute().data
            or []
        )
    except Exception:
        return True
    value = (rows[0] if rows else {}).get("followup_suggestions")
    return value is not False


def write_followup_preference(supabase: Any, user_id: str, suggest: bool) -> None:
    supabase.table("user_profiles").update({"followup_suggestions": bool(suggest)}).eq("id", user_id).execute()


@scoped("followup")
async def ensure_followup(supabase: Any, memo_id: str, *, llm: Any = None) -> None:
    """Idempotent. Safe to call from every path that completes an extraction."""
    memo_id = str(memo_id)
    with _guard:
        if memo_id in _live:
            return
        _live.add(memo_id)
    run_id = str(uuid.uuid4())
    acquired = False
    try:
        memo = _read_memo(supabase, memo_id)
        now = _utc_now()
        if not memo or not is_eligible(memo) or not should_generate(memo.get("followup"), now):
            return
        company_id = memo.get("company_id")
        if not is_enabled(supabase, company_id, FLAG):
            return
        if memo.get("user_id") and not read_followup_preference(supabase, str(memo["user_id"])):
            return  # the rep turned email drafts off
        by_flow = is_enabled(supabase, company_id, BY_FLOW_FLAG)
        prompt_version = PROMPT_VERSION_BY_FLOW if by_flow else PROMPT_VERSION
        acquired = _acquire(supabase, memo_id, run_id, now, prompt_version)
        if not acquired:
            return
        memo = await _after_c04(supabase, memo_id, memo)
        if llm is None:
            from app.services.llm import LLMClient

            llm = LLMClient()
        draft = await _draft(supabase, memo, llm, prompt_version=prompt_version, by_flow=by_flow)
        base = {"run_id": run_id, "prompt_version": prompt_version, "started_at": now.isoformat()}
        if draft:
            _finish(supabase, memo_id, run_id, {**base, "status": "ready", "ready_at": _utc_now().isoformat(), **draft})
        else:
            _finish(supabase, memo_id, run_id, {**base, "status": "unavailable", "reason": "empty_draft"})
    except Exception:
        logger.exception("followup: generation failed for memo %s", memo_id)
        if acquired:
            try:
                _finish(supabase, memo_id, run_id, {"run_id": run_id, "prompt_version": PROMPT_VERSION,
                                                     "status": "unavailable", "reason": "error"})
            except Exception:
                logger.exception("followup: could not mark memo %s unavailable", memo_id)
    finally:
        with _guard:
            _live.discard(memo_id)


def _memo_company(supabase: Any, memo_id: str) -> Optional[str]:
    try:
        row = _first(supabase.table("memos").select("company_id").eq("id", memo_id).limit(1).execute())
    except Exception:
        return None
    return (row or {}).get("company_id")


def schedule_followup(supabase: Any, memo_id: str, *, llm: Any = None, company_id: Optional[str] = None) -> bool:
    """Fire-and-forget from any path that just completed an extraction.

    Returns whether a run was started: never with the switch off for the memo's company,
    and never outside an event loop (GET /memos/{id}/followup is then the safety net).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    if company_id is None:
        company_id = _memo_company(supabase, str(memo_id))
    if not is_enabled(supabase, company_id, FLAG):
        return False
    task = loop.create_task(ensure_followup(supabase, str(memo_id), llm=llm))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True
