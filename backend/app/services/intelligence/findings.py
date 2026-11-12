"""What the head of sales looks for in a finished call beyond the steps (C04 findings, its own pass): the
prospect's questions and whether they were answered, the doors the rep let pass, what worked that the playbook
does not have, and what the rep conceded. A second, focused read of the same You:/Them: transcript, so it never
changes how the steps and objections are judged.

Every item stands on the speaker's own words found in the transcript (the prospect's for a question or a signal,
the rep's for an answer, a move or a concession); an item whose words are not there, or are the other side's, is
dropped. Items are named by a short topic, and the company's topics from earlier calls are given back to the model
so the same thing keeps the same name across calls: grouping is a lookup, never a second model call."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings
from difflib import SequenceMatcher

from app.services.intelligence.extract import _prospect_evidence as _prospect_words, _rep_evidence as _rep_words, _sentence

logger = logging.getLogger(__name__)

FINDINGS_VERSION = "findings_v1"
FINDINGS_FLAG = "CALL_FINDINGS_ENABLED"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"call_{FINDINGS_VERSION}.md"

# Calls with nothing of this to read: nobody talked, or it was not a sales call.
SKIPPED_CALLS = frozenset({"no_conversation", "not_a_sales_call", "dictated_note"})

_ANSWERED = frozenset({"yes", "partly", "later", "no"})
_SIGNAL = frozenset({"need", "interest", "timing", "unhappy", "buying", "referral", "other"})
_CONCESSION = frozenset({"price", "discount", "trial", "free", "payment", "commitment", "deadline", "other"})
# More than this in one call is padding, not findings.
_LIMITS = {"questions": 8, "signals": 3, "worked": 4, "concessions": 4}
_TOPIC_MAX = 60
_WHY_MAX = 280
_LINE_MAX = 240
_WHAT_MAX = 120
# What the model is shown of the company's material and of earlier topics: enough to judge, never the whole table.
_MATERIAL_FIELDS = ("value_short", "pricing", "notes", "differentiators", "proofs", "competitors", "value_long")
_MATERIAL_FIELD_MAX = 1800
KNOWN_TOPICS_MAX = 80


# How close the words found in the transcript must be to the words the model quoted. The quote helpers recover a
# quote the other side cut into by taking the speaker's longest matching piece; for a finding that piece has to be the
# same moment, never a few shared words from somewhere else in the call.
_SAME_MOMENT = 0.75


def _same_moment(ref: dict | None, asked: str) -> dict | None:
    if ref is None:
        return None
    found, wanted = " ".join(ref["quote"].casefold().split()), " ".join(asked.casefold().split())
    if not wanted or wanted in found or found in wanted and len(found) >= _SAME_MOMENT * len(wanted):
        return ref
    return ref if SequenceMatcher(None, found, wanted, autojunk=False).ratio() >= _SAME_MOMENT else None


def _prospect_evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    return _same_moment(_prospect_words(memo_id, quote, transcript), quote)


def _rep_evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    return _same_moment(_rep_words(memo_id, quote, transcript), quote)


def topic_key(text: Any) -> str:
    """Case, spacing and a closing full stop do not make a different topic."""
    return " ".join(str(text or "").casefold().split()).rstrip(" .;:")


def _topic(value: Any) -> str | None:
    text = " ".join(str(value or "").split()).strip(" .;:¿?¡!\"'«»")
    return text[:1].upper() + text[1:_TOPIC_MAX] if text else None


def compact_material(knowledge: Any) -> dict:
    """The company's own written material, field by field, each cut to a size the prompt can carry."""
    if not isinstance(knowledge, dict):
        return {}
    out: dict = {}
    for field in _MATERIAL_FIELDS:
        value = knowledge.get(field)
        if isinstance(value, list):
            value = "\n".join(
                " ".join(str(item.get("text") or item.get("name") or item.get("label") or "").split())
                if isinstance(item, dict) else " ".join(str(item).split())
                for item in value
            )
        text = str(value or "").strip()
        if text:
            out[field] = text[:_MATERIAL_FIELD_MAX]
    return out


def build_messages(
    transcript: str,
    *,
    call: dict | None,
    answers: list[dict] | None = None,
    steps: list[dict] | None = None,
    material: dict | None = None,
    known_topics: list[str] | None = None,
    rep_name: str | None = None,
    company_name: str | None = None,
) -> list[dict]:
    payload: dict = {
        "call": {key: (call or {}).get(key) for key in ("call_type", "phase_reached")},
        "rep_name": rep_name,
        "company_name": company_name,
        "playbook_answers": [
            {key: str(item.get(key) or "") for key in ("id", "label", "trigger", "answer")}
            for item in answers or [] if isinstance(item, dict) and item.get("id")
        ],
        "playbook_steps": [
            {key: str(step.get(key) or "") for key in ("step_id", "label", "criterion")}
            for step in steps or [] if isinstance(step, dict) and step.get("step_id")
        ],
        "material": material or {},
        "known_topics": list(known_topics or [])[:KNOWN_TOPICS_MAX],
        "transcript": transcript,
    }
    return [
        {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _canonical(topic: str, known: dict[str, str]) -> str:
    """A topic the model wrote with other casing or spacing than an earlier call's keeps the earlier name."""
    return known.get(topic_key(topic), topic)


def shape_findings(
    memo_id: str,
    raw: Any,
    transcript: str,
    *,
    answer_ids: set[str] | None = None,
    known_topics: list[str] | None = None,
) -> dict:
    """Keep what the speaker's own words back, one item per moment, within each list's limit."""
    raw = raw if isinstance(raw, dict) else {}
    known = {topic_key(name): name for name in known_topics or []}
    ids = answer_ids or set()
    # The prospect's moments (a question, a door) and the rep's (a move that worked, a concession) are counted apart:
    # the same words of the prospect are never both a question and a door, while one move of the rep can be both what
    # worked and what it conceded.
    seen = {"prospect": set(), "worked": set(), "concessions": set()}
    evidence: dict[str, dict] = {}

    def fresh(ref: dict | None, side: str) -> dict | None:
        if ref is None or ref["quote"] in seen[side]:
            return None
        seen[side].add(ref["quote"])
        evidence[ref["id"]] = ref
        return ref

    def items(key: str) -> list[dict]:
        return [item for item in raw.get(key) or [] if isinstance(item, dict)]

    questions: list[dict] = []
    topics_in: dict[str, set[str]] = {"questions": set(), "signals": set(), "worked": set()}
    for item in items("questions"):
        topic = _topic(item.get("topic"))
        answered = item.get("answered") if item.get("answered") in _ANSWERED else None
        if not topic or answered is None or topic_key(topic) in topics_in["questions"]:
            continue
        ref = fresh(_prospect_evidence(memo_id, str(item.get("quote") or ""), transcript), "prospect")
        if ref is None:
            continue
        answer_ref = None
        if answered in ("yes", "partly") and str(item.get("answer") or "").strip():
            answer_ref = _rep_evidence(memo_id, str(item["answer"]), transcript)
            if answer_ref is not None:
                evidence[answer_ref["id"]] = answer_ref
        covered = str(item.get("covered_by") or "").strip()
        topics_in["questions"].add(topic_key(topic))
        questions.append({
            "topic": _canonical(topic, known),
            "quote": ref["quote"],
            # An answer the rep's own words do not show is not an answer.
            "answered": answered if answered in ("later", "no") or answer_ref is not None else "no",
            "answer": answer_ref["quote"] if answer_ref is not None else None,
            "covered_by": covered if covered == "material" or covered in ids else None,
            # What to answer next time, from the playbook, the material or the rep's own right words; none means the
            # company has no answer to give yet.
            "better": _sentence(item.get("better"), _LINE_MAX),
            "evidence_refs": [ref["id"], *([answer_ref["id"]] if answer_ref else [])],
        })

    signals: list[dict] = []
    for item in items("signals"):
        topic = _topic(item.get("topic"))
        why = _sentence(item.get("why"), _WHY_MAX)
        if not topic or not why or topic_key(topic) in topics_in["signals"] or topic_key(topic) in topics_in["questions"]:
            continue
        ref = fresh(_prospect_evidence(memo_id, str(item.get("quote") or ""), transcript), "prospect")
        if ref is None:
            continue
        topics_in["signals"].add(topic_key(topic))
        # What the rep said right after: shown next to the door, only when they are the rep's own words.
        reply = _rep_evidence(memo_id, str(item.get("reply") or ""), transcript) if str(item.get("reply") or "").strip() else None
        if reply is not None:
            evidence[reply["id"]] = reply
        signals.append({
            "topic": _canonical(topic, known),
            "kind": item.get("kind") if item.get("kind") in _SIGNAL else "other",
            "quote": ref["quote"],
            "reply": reply["quote"] if reply is not None else None,
            "why": why,
            "line": _sentence(item.get("line"), _LINE_MAX),
            "evidence_refs": [ref["id"], *([reply["id"]] if reply is not None else [])],
        })

    worked: list[dict] = []
    for item in items("worked"):
        topic = _topic(item.get("topic"))
        why = _sentence(item.get("why"), _WHY_MAX)
        if not topic or not why or topic_key(topic) in topics_in["worked"]:
            continue
        after = _prospect_evidence(memo_id, str(item.get("after_quote") or ""), transcript)
        # Worked is a fact of the call: without the prospect's words that show it, it is an opinion.
        ref = fresh(_rep_evidence(memo_id, str(item.get("quote") or ""), transcript), "worked") if after else None
        if ref is None or after is None:
            continue
        evidence[after["id"]] = after
        topics_in["worked"].add(topic_key(topic))
        worked.append({
            "topic": _canonical(topic, known),
            "quote": ref["quote"],
            "after_quote": after["quote"],
            "why": why,
            "use_when": _sentence(item.get("use_when"), _WHY_MAX),
            "evidence_refs": [ref["id"], after["id"]],
        })

    concessions: list[dict] = []
    for item in items("concessions"):
        what = _sentence(item.get("what"), _WHAT_MAX)
        normal = _sentence(item.get("normal"), _WHAT_MAX)
        if not what or (normal and topic_key(normal) == topic_key(what)):
            continue
        ref = fresh(_rep_evidence(memo_id, str(item.get("quote") or ""), transcript), "concessions")
        if ref is None:
            continue
        concessions.append({
            "kind": item.get("kind") if item.get("kind") in _CONCESSION else "other",
            "what": what,
            "normal": normal,
            "quote": ref["quote"],
            "evidence_refs": [ref["id"]],
        })

    lists = {"questions": questions, "signals": signals, "worked": worked, "concessions": concessions}
    return {
        "version": FINDINGS_VERSION,
        **{key: value[:_LIMITS[key]] for key, value in lists.items()},
        "evidence": list(evidence.values()),
    }


def wants_findings(call: dict | None) -> bool:
    """Only a conversation that happened, of a sales call, has anything of this to say."""
    return bool(call) and bool(call.get("reached_conversation")) and call.get("call_type") not in SKIPPED_CALLS


async def read_findings(
    memo_id: str,
    transcript: str,
    llm: Any,
    *,
    call: dict | None,
    answers: list[dict] | None = None,
    steps: list[dict] | None = None,
    material: dict | None = None,
    known_topics: list[str] | None = None,
    rep_name: str | None = None,
    company_name: str | None = None,
) -> dict | None:
    """The findings of one call, or None when the call has none to give or the read failed: a failure never
    blocks the rest of the call's reading."""
    if not wants_findings(call) or not transcript.strip():
        return None
    messages = build_messages(
        transcript, call=call, answers=answers, steps=steps, material=material, known_topics=known_topics,
        rep_name=rep_name, company_name=company_name,
    )
    effort = getattr(settings, "CALL_FINDINGS_EFFORT", None)
    try:
        raw = await llm.chat_json(
            # A long call read with reasoning takes minutes; it runs after the call, nobody waits on it.
            messages, model=settings.INTELLIGENCE_MODEL, temperature=0.0, timeout=240.0,
            **({"reasoning_effort": effort} if effort else {}),
        )
    except Exception:
        logger.warning("call findings read failed", extra={"memo_id": memo_id}, exc_info=True)
        return None
    answer_ids = {str(item.get("id")) for item in answers or [] if isinstance(item, dict) and item.get("id")}
    return shape_findings(memo_id, raw, transcript, answer_ids=answer_ids, known_topics=known_topics)


def known_topics_of(rows: list[dict]) -> list[str]:
    """The topic names earlier calls of the company used, most used first, so a new call reuses them."""
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for row in rows:
        findings = row.get("findings") if isinstance(row, dict) else None
        if not isinstance(findings, dict):
            continue
        for key in ("questions", "signals", "worked"):
            for item in findings.get(key) or []:
                name = _topic(item.get("topic")) if isinstance(item, dict) else None
                if name:
                    names.setdefault(topic_key(name), name)
                    counts[topic_key(name)] = counts.get(topic_key(name), 0) + 1
    return [names[key] for key in sorted(counts, key=lambda k: (-counts[k], k))][:KNOWN_TOPICS_MAX]


def load_known_topics(supabase: Any, company_id: str) -> list[str]:
    """Best effort: [] when the read fails (the call then names its topics on its own)."""
    try:
        rows = (
            supabase.table("memos")
            .select("findings:extraction->intelligence->findings")
            .eq("company_id", str(company_id))
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        ).data or []
    except Exception:
        logger.warning("known topics read failed", extra={"company_id": company_id}, exc_info=True)
        return []
    return known_topics_of(rows)



def _same_words(a: Any, b: Any) -> bool:
    """Whether two quotes are the same moment: one holds the other once case and spacing are set aside."""
    left, right = topic_key(a), topic_key(b)
    return bool(left and right) and (left in right or right in left)


def coach_findings(findings: Any, reading: Any = None) -> dict | None:
    """What the rep's own Coaching shows of a call's findings: the questions not fully answered (with what to answer
    next time, or none when the company has no answer yet), the doors let pass (with the line to try) and what worked
    (with when to use it again). Concessions are the head of sales' business, not coaching. None when nothing is left."""
    if not isinstance(findings, dict):
        return None
    # The moment the call turned is already shown with what to say there: the same moment is not shown twice.
    moment = ((reading or {}).get("decisive_moment") or {}).get("quote") if isinstance(reading, dict) else None
    keep = ("topic", "quote")
    questions = [
        {**{k: item.get(k) for k in (*keep, "answered", "answer", "better")}, "no_answer": not item.get("better") and not item.get("covered_by")}
        for item in findings.get("questions") or []
        if isinstance(item, dict) and item.get("answered") != "yes" and not _same_words(item.get("quote"), moment)
    ]
    signals = [
        {k: item.get(k) for k in (*keep, "kind", "reply", "why", "line")}
        for item in findings.get("signals") or [] if isinstance(item, dict) and not _same_words(item.get("quote"), moment)
    ]
    worked = [{k: item.get(k) for k in (*keep, "after_quote", "why", "use_when")} for item in findings.get("worked") or [] if isinstance(item, dict)]
    if not (questions or signals or worked):
        return None
    return {"questions": questions, "signals": signals, "worked": worked}
