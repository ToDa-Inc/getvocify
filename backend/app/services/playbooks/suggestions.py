"""«Sugerencias»: what the team's calls taught, for the head of sales to take into the playbook or set aside with a reason.

Every finished conversation is read for the head of sales (findings.py): the objections no playbook answer is for, the
clients' questions nobody could answer, what a rep did off the playbook that moved the call on, and the openings let
pass. Here they are grouped by topic and call type across the calls, ranked by how often they happened and what they
cost, and each comes with a ready draft: a colleague's reply after which the call went on, else the line the reading
wrote from the playbook and the company's material.

Nothing enters the playbook without the head of sales. Accepting writes the draft they approved (edited or not):
an objection or a question becomes an answer of the call type's playbook, published at once unless the type already had
unpublished edits; what worked and an opening let pass become a situation of «Cómo trabajamos», which live help reads
on its next card. Setting one aside takes a reason, and the reason is what Vocify learns: «isolated» comes back if it
keeps happening, «not_applicable» never comes back and the reading stops proposing it, «covered» names the answer that
already covers it and the reading learns to recognise it there."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from app.services.intelligence.findings import topic_key

logger = logging.getLogger(__name__)

TABLE = "playbook_suggestion_decisions"
KINDS = ("objection", "question", "worked", "opportunity")
REASONS = ("isolated", "not_applicable", "covered")
# A suggestion set aside as an isolated case comes back once it happened this many more times.
ISOLATED_AGAIN = 2
# An opening let pass in one call is that deal's coaching (a name, a date, a person); it is the team's pattern, and so
# the playbook's business, once it happens in this many calls.
OPPORTUNITY_MIN_CALLS = 2
WINDOW_DAYS = 56
MAX_EXAMPLES = 3
TEXT_MAX = 1200

# Which list of a call's findings feeds each kind, and whose words open the exchange.
_SOURCES = {"objection": "new_objections", "question": "questions", "worked": "worked", "opportunity": "signals"}
_MISSING_MARKERS = ("does not exist", "could not find", "pgrst205", "42p01")


class SuggestionsUnavailable(Exception):
    """The decisions table is not there yet (migration 089): the list still shows, nothing can be decided."""


class SuggestionError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def suggestion_key(kind: str, motion: str, topic: str) -> str:
    """The same thing in the same call type is one suggestion, whatever call it came from next."""
    return hashlib.sha1(f"{kind}|{motion}|{topic_key(topic)}".encode()).hexdigest()[:16]


def _turn(who: str, quote: Any, said: Any) -> Optional[dict]:
    text = " ".join(str(quote or "").split())
    if not text:
        return None
    meant = " ".join(str(said or "").split()) or None
    return {"who": who, "quote": text, "said": meant}


def _exchange(kind: str, item: dict) -> list[dict]:
    """The exchange as it happened: an objection, a question or an opening opens with the client and the rep's reply follows;
    a move that worked opens with the rep and the client's reaction follows."""
    if kind == "worked":
        turns = [_turn("rep", item.get("quote"), item.get("said")), _turn("client", item.get("after_quote"), item.get("after_said"))]
    else:
        reply, reply_said = (item.get("answer"), item.get("answer_said")) if kind == "question" else (item.get("reply"), item.get("reply_said"))
        turns = [_turn("client", item.get("quote"), item.get("said")), _turn("rep", reply, reply_said)]
    return [turn for turn in turns if turn]


def _wanted(kind: str, item: dict) -> bool:
    if kind == "question":
        # Answered well in the call, or answered by the playbook or the material: nothing to write.
        return item.get("answered") != "yes" and not item.get("covered_by")
    return True


def _draft(kind: str, item: dict) -> tuple[Optional[str], Optional[str]]:
    """(text, where it comes from) for one call's item: a colleague's own words that moved the call on come first."""
    if kind == "objection":
        if item.get("after") == "advanced" and (item.get("reply_said") or item.get("reply")):
            return str(item.get("reply_said") or item.get("reply")), "colleague"
        return (str(item["better"]), "vocify") if item.get("better") else (None, None)
    if kind == "question":
        return (str(item["better"]), "vocify") if item.get("better") else (None, None)
    if kind == "worked":
        return str(item.get("said") or item.get("quote") or "") or None, "colleague"
    return (str(item["line"]), "vocify") if item.get("line") else (None, None)


def _same_words(a: Any, b: Any) -> bool:
    left, right = topic_key(a), topic_key(b)
    return bool(left and right) and (left in right or right in left)


def _score(group: dict) -> int:
    weight = {"objection": 3, "question": 3, "worked": 3, "opportunity": 2}[group["kind"]]
    return group["count"] * weight + 2 * group.get("lost", 0) + 2 * group.get("unanswered", 0)


def build_suggestions(
    rows: list[dict], names: dict[str, str], labels: dict[str, str], decisions: dict[str, dict] | None = None,
) -> list[dict]:
    """The suggestions of these interaction rows (rep_coaching.interaction_row), best first, without the ones the head of
    sales already decided on. Each: {key, kind, motion, motion_label, title, count, reps, memo_ids, last_at, lost,
    unanswered, examples: [{memo_id, observed_at, rep, turns, after}], draft, draft_from, why, use_when}."""
    decided = decisions or {}
    groups: dict[str, dict] = {}
    for row in sorted(rows, key=lambda r: r.get("observed_at") or "", reverse=True):
        findings = row.get("findings")
        motion = str(row.get("motion") or "")
        if not row.get("is_conversation", True) or not isinstance(findings, dict) or not motion:
            continue
        # A move that worked which is the very reply to an objection of the same call is that objection's draft already.
        replies = [o.get("reply") for o in findings.get("new_objections") or [] if isinstance(o, dict) and o.get("reply")]
        for kind, source in _SOURCES.items():
            for item in findings.get(source) or []:
                if not isinstance(item, dict) or not item.get("topic") or not _wanted(kind, item):
                    continue
                if kind == "worked" and any(_same_words(item.get("quote"), reply) for reply in replies):
                    continue
                key = suggestion_key(kind, motion, item["topic"])
                group = groups.setdefault(key, {
                    "key": key, "kind": kind, "motion": motion, "motion_label": labels.get(motion) or motion,
                    "title": str(item["topic"]), "count": 0, "reps": [], "memo_ids": [], "last_at": row.get("observed_at"),
                    "lost": 0, "unanswered": 0, "examples": [], "draft": None, "draft_from": None, "why": None, "use_when": None,
                })
                group["count"] += 1
                rep = names.get(str(row.get("user_id")), "")
                if rep and rep not in group["reps"]:
                    group["reps"].append(rep)
                if row.get("memo_id") not in group["memo_ids"]:
                    group["memo_ids"].append(row.get("memo_id"))
                if kind == "objection" and item.get("after") in ("ended", "stalled"):
                    group["lost"] += 1
                if kind == "question" and item.get("answered") == "no":
                    group["unanswered"] += 1
                if len(group["examples"]) < MAX_EXAMPLES:
                    group["examples"].append({
                        "memo_id": row.get("memo_id"), "observed_at": row.get("observed_at"), "rep": rep,
                        "turns": _exchange(kind, item), "after": item.get("after"),
                    })
                text, origin = _draft(kind, item)
                # A colleague's words that worked beat a written line; the newest of each kind is kept.
                if text and (group["draft"] is None or (origin == "colleague" and group["draft_from"] != "colleague")):
                    group["draft"], group["draft_from"] = text[:TEXT_MAX], origin
                group["why"] = group["why"] or item.get("why")
                group["use_when"] = group["use_when"] or item.get("use_when")
    shown = []
    for group in groups.values():
        decision = decided.get(group["key"])
        if decision and not _comes_back(decision, group["count"]):
            continue
        if group["kind"] == "opportunity" and len(group["memo_ids"]) < OPPORTUNITY_MIN_CALLS:
            continue
        shown.append(group)
    return sorted(shown, key=lambda g: (-_score(g), -(datetime.fromisoformat(g["last_at"]).timestamp() if g["last_at"] else 0), g["title"]))


def _comes_back(decision: dict, count: int) -> bool:
    return decision.get("decision") == "dismissed" and decision.get("reason") == "isolated" and count >= int(decision.get("count_at") or 0) + ISOLATED_AGAIN


def reading_criteria(decisions: dict[str, dict]) -> dict:
    """What the head of sales' decisions teach the reading of the next calls -> {ignored: [topics], covered: [{topic, answer}]}:
    what they said does not apply is never proposed again, and what an answer already covers is read as covered by it."""
    ignored: list[str] = []
    covered: list[dict] = []
    for decision in decisions.values():
        topic = str(decision.get("topic") or "").strip()
        if not topic or decision.get("decision") != "dismissed":
            continue
        if decision.get("reason") == "not_applicable" and topic not in ignored:
            ignored.append(topic)
        elif decision.get("reason") == "covered" and decision.get("covered_by"):
            covered.append({"topic": topic, "answer": str(decision["covered_by"])})
    return {"ignored": ignored[:60], "covered": covered[:60]}


# --- the decisions store --------------------------------------------------------------------------------------------


class DecisionStore(Protocol):
    def all(self, company_id: str) -> dict[str, dict]:
        """Every decision of the company by key; {} when the table is not there yet."""

    def save(self, company_id: str, row: dict) -> dict:
        """One decision per key: a second one replaces it. SuggestionsUnavailable before the migration."""

    def delete(self, company_id: str, key: str) -> None: ...


class InMemoryDecisionStore:
    """TEST FAKE."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def all(self, company_id):
        return {key: row for (company, key), row in self.rows.items() if company == company_id}

    def save(self, company_id, row):
        saved = {**row, "company_id": company_id, "decided_at": _now()}
        self.rows[(company_id, row["key"])] = saved
        return saved

    def delete(self, company_id, key):
        self.rows.pop((company_id, key), None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_missing_table(exc: Exception) -> bool:
    text = str(exc).lower()
    return TABLE in text and any(marker in text for marker in _MISSING_MARKERS)


class SqlDecisionStore:
    """Production: the `playbook_suggestion_decisions` table, through the Supabase table API with the service role."""

    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase

    def _run(self, build: Callable[[Any], Any]) -> list[dict]:
        try:
            return list(getattr(build(self.supabase).execute(), "data", None) or [])
        except Exception as exc:
            if _is_missing_table(exc):
                raise SuggestionsUnavailable() from exc
            raise

    def all(self, company_id):
        try:
            rows = self._run(lambda db: db.table(TABLE).select("*").eq("company_id", company_id))
        except SuggestionsUnavailable:
            return {}
        return {str(row["key"]): row for row in rows}

    def save(self, company_id, row):
        made = {**row, "company_id": company_id, "decided_at": _now()}
        saved = self._run(lambda db: db.table(TABLE).upsert(made, on_conflict="company_id,key"))
        return saved[0] if saved else made

    def delete(self, company_id, key):
        self._run(lambda db: db.table(TABLE).delete().eq("company_id", company_id).eq("key", key))


_store: Optional[DecisionStore] = None


def set_decision_store(store: Optional[DecisionStore]) -> None:
    """Tests install an InMemoryDecisionStore; None goes back to the database."""
    global _store
    _store = store


def get_decision_store(supabase: Any) -> DecisionStore:
    return _store if _store is not None else SqlDecisionStore(supabase)


# --- deciding -------------------------------------------------------------------------------------------------------


def _clean(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def _client_words(suggestion: dict) -> str:
    """How the client put it, from the newest example: what they meant when it was read, else their words."""
    for example in suggestion.get("examples") or []:
        for turn in example.get("turns") or []:
            if turn.get("who") == "client":
                return str(turn.get("said") or turn.get("quote") or "")
    return ""


def add_answer(content: dict, suggestion: dict, text: str) -> dict:
    """The playbook content with the head of sales' answer for an objection or a question of the team's own: named by the
    suggestion's title (never the client's first words), the client's own way of saying it as how they say it.
    ValueError: text_required, guidance_too_long, too_many_custom_objections, already_in_playbook."""
    from app.services.playbooks.structured import CUSTOM_CATEGORY, MAX_CUSTOM_OBJECTIONS, MAX_GUIDANCE, MAX_OBJECTION_LABEL, MAX_TRIGGER, clip_text, slug

    body = " ".join(str(text or "").split())
    if not body:
        raise ValueError("text_required")
    if len(body) > MAX_GUIDANCE:
        raise ValueError("guidance_too_long")
    objections = [dict(o) for o in content.get("objections") or []]
    customs = [o for o in objections if o.get("category") == CUSTOM_CATEGORY]
    if len(customs) >= MAX_CUSTOM_OBJECTIONS:
        raise ValueError("too_many_custom_objections")
    label = clip_text(suggestion["title"], MAX_OBJECTION_LABEL)
    if any(str(o.get("label") or "").strip().casefold() == label.casefold() for o in customs):
        raise ValueError("already_in_playbook")
    trigger = clip_text(_client_words(suggestion) or suggestion["title"], MAX_TRIGGER)
    objections.append({"category": CUSTOM_CATEGORY, "id": slug(label, "custom"), "label": label, "trigger": trigger, "guidance": body})
    return {**content, "objections": objections}


def add_situation(conduct: Optional[dict], suggestion: dict, text: str) -> dict:
    """«Cómo trabajamos» with a situation for what worked or an opening let pass: when it applies (the reading's «when to
    use it again», else what the client said) and what to do (the head of sales' words).
    ValueError: text_required, too_many_situations, already_in_playbook."""
    from app.services.playbooks.conduct import MAX_SITUATIONS, empty, normalize

    body = _clean(text, TEXT_MAX)
    if not body:
        raise ValueError("text_required")
    current = dict(conduct or empty())
    situations = [dict(s) for s in current.get("situations") or []]
    if len(situations) >= MAX_SITUATIONS:
        raise ValueError("too_many_situations")
    name = _clean(suggestion["title"], 160)
    if any(str(s.get("name") or "").strip().casefold() == name.casefold() for s in situations):
        raise ValueError("already_in_playbook")
    when = _clean(suggestion.get("use_when") or _client_words(suggestion), 600)
    example = ""
    if suggestion["kind"] == "worked":
        rep = next((t for e in suggestion.get("examples") or [] for t in e.get("turns") or [] if t.get("who") == "rep"), None)
        example = _clean((rep or {}).get("quote"), 600)
    situations.append({"name": name, "when": when, "do": body, "example": example, "avoid": ""})
    return normalize({**current, "situations": situations}) or {}


def find(suggestions: list[dict], key: str) -> dict:
    for suggestion in suggestions:
        if suggestion["key"] == key:
            return suggestion
    raise SuggestionError("suggestion_not_found")


# --- names and drafts -----------------------------------------------------------------------------------------------


def display_name(name: Any) -> str:
    """A member with no name in their profile shows as an email: «daniel.clavero@movertis.com» reads «Daniel Clavero»."""
    text = " ".join(str(name or "").split())
    if "@" not in text:
        return text
    local = text.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
    return " ".join(part[:1].upper() + part[1:] for part in local.split() if part)


DRAFT_MAX_WORDS = 45
_DRAFT_SYSTEM = (
    "You write what a salesperson of the company would answer, right then in the call, to what the client said. Spoken, "
    "first person, in Spanish, at most 45 words, in a natural register. It must actually answer it with facts from "
    "material or playbook_answers, and you list those facts in `facts`, each copied word for word from them (a short "
    "phrase, not a paraphrase). Never invent a price, a feature, a date, a customer, a number or a condition. When they "
    "do not hold what the answer needs, or you would only be able to dodge it (\"depende\", \"lo miro y te digo\"), "
    "write nothing. The material also holds instructions to the team (\"no inventar descuentos\", \"no prometer\"): they "
    "guide you, they are never something to tell the client. Return only this JSON: {\"text\": \"...\", \"facts\": [\"...\"]} or {\"text\": null, \"facts\": []}."
)


def _fold(text: Any) -> str:
    return " ".join(str(text or "").casefold().split())


def _grounded(facts: Any, sources: list[str]) -> bool:
    """Every fact the draft names is in the company's own text, word for word (case and spacing aside), and there is one."""
    folded = [_fold(source) for source in sources if source]
    quoted = [_fold(fact) for fact in facts or [] if _fold(fact)] if isinstance(facts, list) else []
    return bool(quoted) and all(len(fact) >= 8 and any(fact in source for source in folded) for fact in quoted)


async def write_draft(suggestion: dict, *, material: dict, answers: list[dict], company_name: Optional[str], llm: Any) -> Optional[str]:
    """«Completar con Vocify» for an objection or a question that came with no draft: an answer written from the
    company's own material and playbook only, or None when they do not hold it (then the head of sales writes it). The
    facts it rests on must be found word for word in that text, or it is not shown."""
    import json

    from app.config import settings

    shown_answers = [{k: a.get(k) for k in ("label", "trigger", "answer") if a.get(k)} for a in answers][:30]
    payload = {
        "company_name": company_name,
        "kind": suggestion["kind"],
        "topic": suggestion["title"],
        "client_said": _client_words(suggestion),
        "material": material,
        "playbook_answers": shown_answers,
    }
    raw = await llm.chat_json(
        [{"role": "system", "content": _DRAFT_SYSTEM}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        model=settings.INTELLIGENCE_MODEL, temperature=0.1, timeout=45.0,
    )
    if not isinstance(raw, dict):
        return None
    text = " ".join(str(raw.get("text") or "").split())
    sources = [str(v) for v in (material or {}).values()] + [str(a.get(k) or "") for a in shown_answers for k in ("answer", "trigger")]
    if not text or len(text.split()) > DRAFT_MAX_WORDS * 2 or not _grounded(raw.get("facts"), sources):
        return None
    return text[:TEXT_MAX]
