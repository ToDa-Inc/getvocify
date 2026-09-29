"""System prompts for the live objection-handling copilot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PLAYBOOK_USER_SUFFIX = (_PROMPTS_DIR / "copilot_suggest_v1.md").read_text(encoding="utf-8")

SYSTEM_PROMPT = """You are Vocify Call Copilot — a silent real-time sales coach for cold / outbound phone calls.

CONTEXT OF USE
- The rep is on a live sales call. You only help the REP via on-screen text.
- The prospect must NEVER hear you. Never ask the rep to read robotically.
- CALL MODE in the user message is how audio was captured:
  - speakerphone: one mixed laptop mic; both voices may be in the same stream.
  - meeting / softphone: source-labeled. "Them:" is the remote/tab (prospect). "You:" is the rep mic.
- When SPEAKER ROLE is provided, trust it. Otherwise prefer treating the LATEST TURN as the prospect.

YOUR JOB
1. Detect whether the latest turn is an objection, hesitation, brush-off, or question.
2. If yes, give the rep the best next words to say out loud — short, natural, confident.
3. If not an objection, still help lightly: one sharp next question or bridge (set is_objection=false).

OBJECTION PLAYBOOK (use the lightest framework that fits)
Core loop: Acknowledge → Isolate → Reframe with proof/value → Advance with a question.
- Price / budget: Never defend price first. Acknowledge → isolate ("is it the investment, or the timing of cash?") → reframe ROI / cost of inaction → soft close or next step.
- Timing / "call me later": Acknowledge → create a micro-yes now ("fair — before I go, what would need to be true in 30 days for this to matter?") → book a concrete callback.
- Authority / "not the decision maker": Acknowledge → ask who else + what they care about → offer a 2-minute joint summary / ask for intro.
- Competitor / status quo: Acknowledge → differentiate on the one job-to-be-done they just implied → ask what is broken in the current way.
- Trust / "send info": Acknowledge → ask what specifically they'd want in a note → give ONE concrete proof point → propose a short next call.
- "Not interested" brush-off: Stay calm → pattern interrupt with a curious, non-needy question about their current process — one sentence only.

RULES
- Match the prospect's language (Spanish or English). If mixed, prefer the latest turn's language.
- "say_this" must be speakable in under ~12 seconds. Max 3 short sentences. No bullet lists inside say_this.
- No corporate fluff, no "I understand your concern as an AI", no over-apologizing.
- Never invent customer logos or fake metrics. Use only product_context or the COMPANY KNOWLEDGE block when citing proof.
- Prefer questions that advance the call over monologues.
- If the latest turn is the rep talking / filler / noise, set is_objection=false and keep coaching light.
- Unless a published playbook was provided in the user message, set evidence_refs to [] and source_id to null.

OUTPUT
Return ONLY valid JSON with this exact shape:
{
  "is_objection": boolean,
  "objection_type": "price"|"timing"|"authority"|"competitor"|"status_quo"|"trust"|"other"|"none",
  "urgency": "low"|"medium"|"high",
  "say_this": string,
  "why_it_works": string,
  "next_question": string,
  "dont_say": string,
  "evidence_refs": array of strings,
  "source_id": string or null
}
"""


def _published_entry_ids(snapshot: dict[str, Any]) -> list[str]:
    entries = snapshot.get("entries") or []
    ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "").strip()
        if entry_id:
            ids.append(entry_id)
    return ids


COMPANY_KNOWLEDGE_MAX_CHARS = 2400
_KNOWLEDGE_HEADER = (
    "COMPANY KNOWLEDGE (from the company's own playbook. This is the ONLY proof you may cite: "
    "customers, numbers and differentiators. If it is not written here, do not claim it.)"
)


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(limit - 1, 0)].rstrip() + "…"


def _named_competitors(competitors: Any, text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    named: list[dict[str, Any]] = []
    for item in competitors if isinstance(competitors, list) else []:
        name = _clip(item.get("name"), 60) if isinstance(item, dict) else ""
        if name and name.lower() in lowered:
            named.append(item)
    return named[:2]


def format_company_knowledge(
    knowledge: Optional[dict[str, Any]],
    *,
    call_text: str = "",
    max_chars: int = COMPANY_KNOWLEDGE_MAX_CHARS,
) -> str:
    """The company's knowledge as a bounded prompt block: short value line, differentiators, up to
    three customer proofs and, only for a competitor named in `call_text`, how to talk about it
    and what not to say. Empty string when there is nothing to say. Never longer than max_chars."""
    if not isinstance(knowledge, dict) or not knowledge:
        return ""
    lines: list[str] = []
    value = _clip(knowledge.get("value_short"), 300)
    if value:
        lines.append(f"Value in one line: {value}")
    differentiators = [_clip(item, 160) for item in (knowledge.get("differentiators") or [])]
    differentiators = [item for item in differentiators if item][:5]
    if differentiators:
        lines.append("Differentiators:")
        lines.extend(f"- {item}" for item in differentiators)
    proof_lines = []
    for proof in [item for item in (knowledge.get("proofs") or []) if isinstance(item, dict)][:3]:
        customer = _clip(proof.get("customer"), 60)
        change = _clip(
            " ".join(part for part in (_clip(proof.get("situation"), 140), _clip(proof.get("change"), 140)) if part),
            280,
        )
        number = _clip(proof.get("number"), 60)
        if customer or change or number:
            proof_lines.append("- " + " · ".join(part for part in (customer, change, number) if part))
    if proof_lines:
        lines.append("Customer proofs (the only ones that exist):")
        lines.extend(proof_lines)
    for competitor in _named_competitors(knowledge.get("competitors"), call_text):
        lines.append(f"Competitor named in the call: {_clip(competitor.get('name'), 60)}")
        how = _clip(competitor.get("how_to_talk"), 300)
        if how:
            lines.append(f"- How to talk about it: {how}")
        landmines = _clip(competitor.get("landmines"), 300)
        if landmines:
            lines.append(f"- Do not say: {landmines}")
    if not lines:
        return ""
    body = "\n".join(lines)
    room = max_chars - len(_KNOWLEDGE_HEADER) - 1
    if len(body) > room:
        body = body[: max(room - 1, 0)].rstrip() + "…"
    return f"{_KNOWLEDGE_HEADER}\n{body}"


def build_user_prompt(
    *,
    transcript_window: str,
    latest_turn: str,
    product_context: str | None,
    language: str,
    call_mode: str,
    speaker_role: str = "unknown",
    playbook_snapshot: Optional[dict[str, Any]] = None,
    company_knowledge: Optional[dict[str, Any]] = None,
) -> str:
    context = (product_context or "").strip() or "(none provided — stay generic and ask discovery questions)"
    role = (speaker_role or "unknown").strip().lower()
    if role not in {"prospect", "rep", "unknown"}:
        role = "unknown"
    role_hint = {
        "prospect": "This turn is attributed to the PROSPECT. Coach a reply.",
        "rep": "This turn is attributed to the REP. Keep coaching light; do not invent a prospect objection.",
        "unknown": "Speaker unknown — treat as prospect unless the wording is clearly the rep.",
    }[role]
    knowledge = format_company_knowledge(company_knowledge, call_text=f"{transcript_window}\n{latest_turn}")
    knowledge_block = f"\n{knowledge}\n" if knowledge else ""
    base = f"""CALL MODE: {call_mode}
PREFERRED LANGUAGE HINT: {language}
SPEAKER ROLE: {role}
SPEAKER HINT: {role_hint}

PRODUCT / OFFER CONTEXT:
{context}
{knowledge_block}
ROLLING TRANSCRIPT (recent):
{transcript_window.strip() or "(empty)"}

LATEST TURN (trigger):
{latest_turn.strip() or "(empty)"}

Coach the rep NOW. JSON only."""

    if playbook_snapshot:
        entry_ids = _published_entry_ids(playbook_snapshot)
        suffix = PLAYBOOK_USER_SUFFIX.replace(
            "{{entry_ids}}",
            ", ".join(entry_ids) if entry_ids else "(none)",
        )
        return f"{base}\n\n{suffix.strip()}"
    return base
