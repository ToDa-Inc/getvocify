"""LLM transcript repair as a patch.

The model lists only the words that were misheard ("Voicify" -> "Vocify") instead of writing the
whole transcript again: ~100 output tokens instead of ~2,500, so it takes about a second, and it
cannot drop or reword anything it was not asked to touch. Every proposed edit is then checked by
code (`validate_patch`) before it is applied, so a wrong, invented or oversized answer from the
model never reaches the transcript. Anything that goes wrong leaves the transcript as it was.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.services.transcript_turns import parse_transcript_turns, serialize_transcript_turns

logger = logging.getLogger(__name__)

MIN_CHARS = 80  # a 3-second call has nothing to repair
CHUNK_CHARS = 12_000  # long calls are repaired in parallel windows of about this size
MAX_PARALLEL_CHUNKS = 4
MAX_TOKENS = 1_500  # a patch is ~100-600 tokens; a runaway answer is cut here and discarded
TIMEOUT_S = 12.0
MAX_RETRIES = 1
MAX_PAIRS = 25  # replacements per chunk
MAX_SPAN_WORDS = 6  # the misheard text itself; spelled-out emails may be longer
MAX_EMAIL_SPAN_WORDS = 16
MIN_BUDGET_WORDS = 8  # a whole call may change by 2% of its words, and by at least this many
BUDGET_RATIO = 0.02

# Real products and services a rep names on a call. A correctly written one is never "fixed".
DEFAULT_PROTECTED = (
    "hubspot", "pipedrive", "salesforce", "zoho", "aircall", "ringover", "apollo", "gmail",
    "outlook", "linkedin", "zoom", "slack", "whatsapp", "vocify",
)
_EMAIL_SPOKEN = re.compile(r"\b(punto|arroba|arrova|punt|at|dot)\b", re.I)
_EMAIL_SHAPE = re.compile(r"^[\w.+-]+@([\w-]+(\.[\w-]+)*)?$")
_TLD_WORDS = {"com", "es", "net", "org", "io", "co", "cat", "eu", "ai", "app"}


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    return re.sub(r"[^\w@.]", "", _fold(text))


@dataclass
class PatchContext:
    """What the checks need to know about the call."""

    allowed: set[str] = field(default_factory=set)  # entities a word may be corrected INTO
    protected: set[str] = field(default_factory=set)  # real names that are never rewritten
    rep_names: set[str] = field(default_factory=set)  # the rep's own name: only valid on the rep's turns
    two_party: bool = False

    @classmethod
    def build(cls, terms: Iterable[Any], roles: Optional[dict[str, str]], two_party: bool,
              protected: Iterable[str] = DEFAULT_PROTECTED) -> "PatchContext":
        allowed: set[str] = set()
        for term in terms:
            canonical = (getattr(term, "canonical", "") or "").strip()
            if canonical:
                allowed.add(_norm(canonical))
                allowed.update(_norm(w) for w in canonical.split() if len(w) > 2)
        roles = roles or {}
        rep: set[str] = set()
        for key in ("rep_name", "contact_name", "company_name", "seller_company"):
            value = (roles.get(key) or "").strip()
            if value:
                allowed.add(_norm(value))
                allowed.update(_norm(w) for w in value.split() if len(w) > 2)
                if key == "rep_name":
                    rep.update(_norm(w) for w in value.split() if len(w) > 2)
        prot = {_norm(p) for p in protected if p}
        return cls(allowed=allowed - {""}, protected=prot, rep_names=rep - {""}, two_party=two_party)


@dataclass
class PatchResult:
    text: str
    edits: list[tuple[str, str]] = field(default_factory=list)
    rejected: list[tuple[str, str, str]] = field(default_factory=list)
    skipped: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def stage_info(self) -> dict[str, Any]:
        """What the pipeline stage records, so every change is auditable afterwards."""
        info: dict[str, Any] = {"model": self.model, "provider": self.provider, "skipped": self.skipped,
                                "prompt_tokens": self.prompt_tokens or None,
                                "completion_tokens": self.completion_tokens or None,
                                "edits_applied": len(self.edits), "edits_rejected": len(self.rejected)}
        if self.edits:
            info["edits"] = [[a[:60], b[:60]] for a, b in self.edits[:20]]
        if self.rejected:
            info["rejected"] = [[a[:40], b[:40], why] for a, b, why in self.rejected[:10]]
        return info


# --- prompt ---------------------------------------------------------------------------------

def build_prompt(turns: list[dict], indexes: list[int], entity_block: str, roles: Optional[dict[str, str]],
                 spoken_language: Optional[str], email_guidelines: str) -> str:
    roles = roles or {}
    lang = (spoken_language or "").strip().lower()
    language = {
        "ca": "Spoken language is Catalan (it may mix Spanish). Keep Catalan; never convert it to Spanish.",
        "es": "Spoken language is Spanish. Keep every word in the language it was spoken in; never translate.",
    }.get(lang, "Keep every word in the language it was spoken in; never translate.")
    rep, contact = roles.get("rep_name"), roles.get("contact_name")
    who = ""
    if rep or contact:
        who = (f"S1 is {rep or 'the sales rep'}"
               f"{' from ' + roles['seller_company'] if roles.get('seller_company') else ''}, "
               f"S2 is {contact or 'the prospect'}"
               f"{' at ' + roles['company_name'] if roles.get('company_name') else ''}.\n")
    numbered = "\n\n".join(f"[{i}] {turns[i].get('speaker') or ''}: {turns[i]['text']}" for i in indexes)
    return f"""You fix ASR (speech recognition) mistakes in a sales-call transcript by listing small word replacements.
{language}
{who}{email_guidelines}
Allowed entities - when a word was clearly meant to be one of these, spell it exactly like this:
{entity_block or "(none provided)"}

Fix ONLY:
1. A word or short phrase that was misheard and SOUNDS like the correct one (brand, product, company and person names, tocadas -> llamadas, hubs -> HubSpot).
2. Spelled-out emails ("juan punto perez arroba empresa punto com" -> "juan.perez@empresa.com"), using only the words that were spoken.

Hard rules:
- When unsure, change NOTHING. An empty list is normal; most calls need 0-6 changes.
- Never replace a word with one that means something different. The new text must sound like the old text.
- Never change a real product or company name that is already spelled correctly (HubSpot, Pipedrive, Salesforce...).
- Never translate or switch language. Never fix grammar, filler words, numbers or style. Never merge, split or reorder turns.
- Never turn one person's name into another person's name.
- "from" = the smallest exact substring (at most 6 words) copied character-for-character from that turn's text.
- Never invent facts, companies, domains or people.

Return JSON only:
{{"changes": [{{"i": <turn index>, "replace": [["exact wrong text", "corrected text"]]}}]}}
If nothing needs fixing: {{"changes": []}}

TRANSCRIPT (numbered turns):
\"\"\"
{numbered}
\"\"\"
"""


# --- the checks -----------------------------------------------------------------------------

def validate_patch(turns: list[dict], payload: Any, ctx: PatchContext,
                   indexes: Optional[list[int]] = None) -> tuple[list[tuple[int, str, str]], list[tuple[str, str, str]]]:
    """Return (accepted [(turn, old, new)], rejected [(old, new, reason)]). Never raises.

    Structural problems (not JSON of the right shape, a turn that does not exist, text that is not
    in the turn) and anything that is not a small, phonetically close fix of a misheard word are
    refused one by one; a patch that changes too much is refused whole."""
    accepted: list[tuple[int, str, str]] = []
    rejected: list[tuple[str, str, str]] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        return accepted, [("", "", "malformed")]
    scope = set(indexes) if indexes is not None else set(range(len(turns)))
    changes = [c for c in payload["changes"] if isinstance(c, dict)]
    if len(changes) > len(scope) + 5:  # more entries than turns: not a patch (the diff budget bounds the rest)
        return accepted, [("", "", f"too_many_changed_turns({len(changes)})")]
    full_text = " ".join(turns[i]["text"] for i in scope).lower()
    seen_pairs: set[tuple[int, str, str]] = set()
    n_pairs = 0
    for change in changes:
        i = change.get("i")
        if isinstance(i, bool) or not isinstance(i, int) or i not in scope:
            rejected.append(("", "", "bad_index"))
            continue
        pairs = change.get("replace")
        for pair in pairs if isinstance(pairs, list) else []:
            n_pairs += 1
            if not (isinstance(pair, (list, tuple)) and len(pair) == 2 and all(isinstance(x, str) for x in pair)):
                rejected.append(("", "", "bad_pair"))
                continue
            old, new = pair[0].strip(), pair[1].strip()
            if not old or old == new:
                continue  # nothing to change
            reason = _check_pair(turns[i], old, new, ctx, full_text, over_limit=n_pairs > MAX_PAIRS)
            if reason:
                rejected.append((old, new, reason))
            elif (i, old, new) not in seen_pairs:
                seen_pairs.add((i, old, new))
                accepted.append((i, old, new))
    return accepted, rejected


def _check_pair(turn: dict, old: str, new: str, ctx: PatchContext, full_text: str, over_limit: bool) -> Optional[str]:
    if over_limit:
        return "too_many_pairs"
    if old not in turn["text"]:
        return "not_in_turn"
    folded_old, folded_new = _fold(old), _fold(new)
    is_email = "@" in new and _EMAIL_SPOKEN.search(old) is not None
    n_old, n_new = len(old.split()), len(new.split())
    if n_old > (MAX_EMAIL_SPAN_WORDS if is_email else MAX_SPAN_WORDS) or n_new > n_old + 3:
        return "span_too_long"
    if not is_email and re.search(r"\d", old + new):
        return "touches_numbers"
    if not is_email and n_new < n_old - 1:
        return "drops_words"
    na, nb = _norm(old), _norm(new)
    if na in ctx.protected and na != nb:
        return "protected_real_name"
    if is_email:
        spoken = set(re.findall(r"[a-z0-9]+", folded_old)) | _TLD_WORDS
        written = set(re.findall(r"[a-z0-9]+", folded_new))
        if (not _EMAIL_SHAPE.match(new) or re.search(r"\b(punto|arroba|arrova)\b", folded_new)
                or not written <= spoken):
            return "email_not_built_from_spoken_words"
        return None
    target_known = nb in ctx.allowed or nb in ctx.protected
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    if target_known and ratio < 0.45:
        return f"known_name_but_not_phonetically_close({ratio:.2f})"
    if ctx.rep_names and nb in ctx.rep_names and ctx.two_party and (turn.get("speaker") or "") != "S1":
        return "rep_name_on_other_speakers_turn"
    if not target_known:
        if all(w[:1].isupper() for w in old.split()):
            return "name_changed_to_an_unknown_name"
        seen = len(re.findall(rf"\b{re.escape(new.lower())}\b", full_text)) if n_old <= 2 else 0
        need = 0.85 if n_old >= 4 else 0.6 if n_old == 3 else (0.5 if seen >= 3 else 0.6)
        if ratio < need:
            return f"not_phonetically_close({ratio:.2f})"
    return None


def within_budget(accepted: list[tuple[int, str, str]], total_words: int) -> bool:
    changed = sum(max(len(a.split()), len(b.split())) for _, a, b in accepted)
    return changed <= max(MIN_BUDGET_WORDS, int(total_words * BUDGET_RATIO))


def apply_edits(turns: list[dict], accepted: list[tuple[int, str, str]]) -> list[dict]:
    out = [dict(t) for t in turns]
    for i, old, new in accepted:
        out[i]["text"] = out[i]["text"].replace(old, new)
    return out


# --- the call -------------------------------------------------------------------------------

def _chunks(turns: list[dict]) -> list[list[int]]:
    groups: list[list[int]] = []
    cur: list[int] = []
    size = 0
    for i, turn in enumerate(turns):
        n = len(turn["text"]) + 12
        if cur and size + n > CHUNK_CHARS:
            groups.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        groups.append(cur)
    return groups


async def patch_transcript(
    transcript: str,
    terms: Iterable[Any],
    roles: Optional[dict[str, str]] = None,
    *,
    spoken_language: Optional[str] = None,
    two_party: bool = False,
    model: Optional[str] = None,
) -> PatchResult:
    """Repair misheard words in `transcript`. Always returns a result; `.text` is the input
    unchanged whenever the model fails, answers badly, or has nothing safe to change."""
    from app.services.usage import usage_scope

    result = PatchResult(text=transcript)
    try:
        with usage_scope("sanitize"):  # its tokens and cost are listed under "sanitize", not "extract"
            return await _patch(result, transcript, list(terms), roles, spoken_language, two_party, model)
    except Exception as exc:  # the transcript is already usable: never fail the memo over a repair
        logger.warning("Transcript patch skipped: %s", exc)
        result.text = transcript
        result.edits, result.skipped = [], f"error:{type(exc).__name__}"
        return result


async def _patch(result: PatchResult, transcript: str, terms: list[Any], roles: Optional[dict[str, str]],
                 spoken_language: Optional[str], two_party: bool, model: Optional[str]) -> PatchResult:
    from app.config import settings
    from app.services.llm import LLMClient
    from app.services.session_entities import format_terms_for_llm
    from app.services.transcript_sanitize import spelled_email_guidelines

    if not getattr(settings, "TRANSCRIPT_SANITIZE_LLM", True):
        result.skipped = "disabled"
        return result
    if not transcript or len(transcript.strip()) < MIN_CHARS:
        result.skipped = "short"
        return result
    turns = parse_transcript_turns(transcript)
    if not turns or serialize_transcript_turns(turns) != transcript:
        result.skipped = "unparseable"  # only transcripts that rebuild byte for byte are patched
        return result

    model = model or getattr(settings, "TRANSCRIPT_SANITIZE_MODEL", None) or settings.EXTRACTION_MODEL
    protected = list(DEFAULT_PROTECTED) + list(getattr(settings, "TRANSCRIPT_SANITIZE_PROTECTED_TERMS", None) or [])
    ctx = PatchContext.build(terms, roles, two_party, protected)
    entity_block = format_terms_for_llm(terms)
    email_block = spelled_email_guidelines(spoken_language)
    result.model = model
    sem = asyncio.Semaphore(MAX_PARALLEL_CHUNKS)

    async def one(indexes: list[int]) -> tuple[list[tuple[int, str, str]], list[tuple[str, str, str]]]:
        async with sem:
            llm = LLMClient(model=model)
            prompt = build_prompt(turns, indexes, entity_block, roles, spoken_language, email_block)
            messages = [
                {"role": "system", "content": "You repair ASR transcripts. You never summarize, translate, or invent. Return JSON."},
                {"role": "user", "content": prompt},
            ]
            try:
                payload = await llm.chat_json(messages, model=model, temperature=0.0, timeout=TIMEOUT_S,
                                              max_retries=MAX_RETRIES, max_tokens=MAX_TOKENS)
            except Exception as exc:
                logger.warning("Transcript patch call failed: %s", exc)
                return [], [("", "", f"llm_failed:{type(exc).__name__}")]
            meta = getattr(llm, "last_call_meta", None) or {}
            result.prompt_tokens += int(meta.get("prompt_tokens") or 0)
            result.completion_tokens += int(meta.get("completion_tokens") or 0)
            result.provider = result.provider or meta.get("provider") or ("together" if model.startswith("together/") else "openrouter")
            return validate_patch(turns, payload, ctx, indexes)

    outcomes = await asyncio.gather(*[one(ix) for ix in _chunks(turns)])
    accepted = [e for acc, _ in outcomes for e in acc]
    result.rejected = [r for _, rej in outcomes for r in rej]
    total_words = sum(len(t["text"].split()) for t in turns)
    if accepted and not within_budget(accepted, total_words):
        result.rejected.append(("", "", f"diff_budget_exceeded({len(accepted)} edits)"))
        accepted = []
    if accepted:
        result.text = serialize_transcript_turns(apply_edits(turns, accepted))
        result.edits = [(a, b) for _, a, b in accepted]
    if result.rejected:
        logger.info("Transcript patch rejected %d edit(s): %s", len(result.rejected), result.rejected[:5])
    if result.edits:
        logger.info("Transcript patch applied %d edit(s)", len(result.edits))
    return result
