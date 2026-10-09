"""System prompts for the live objection-handling copilot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
# v2: the model reads each approved answer, not just its id, so a grounded card says what the team approved.
PLAYBOOK_USER_SUFFIX = (_PROMPTS_DIR / "copilot_suggest_v2.md").read_text(encoding="utf-8")

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
- When the user message lists the team's approved answers, an approved answer for the objection's category wins over the frameworks above.

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


MEETING_LINE_MAX = 90

MEETING_SYSTEM_PROMPT = f"""You are Vocify's live assist for a live sales call or meeting. The rep reads your one
line on screen while still talking, so every word must earn its place.

WHO IS WHO
- "Them:" lines are the prospect side (call or meeting audio). "You:" lines are the rep (microphone).
- The LATEST TURN is the prospect's.

YOUR ONLY JOB
Decide if the latest turn needs help right now. Two cases only:
1. A real objection: they resist price, timing, who decides, a competitor or their current tool, or trust.
2. A direct question about the product or offer whose answer IS in PRODUCT / OFFER CONTEXT or
   COMPANY KNOWLEDGE (objection_type "question"). If neither answers it, it is NOT a case: stay silent.
Agreement, small talk, thinking aloud, rhetorical questions, or the rep talking are NOT cases.
When unsure, stay silent. A missed moment costs less than a wrong interruption.
Put "is_objection" and "objection_type" first in the JSON; they are read before the rest arrives.

IF IT IS A CASE (objection or question)
- "say_this": ONE line the rep can say out loud, max {MEETING_LINE_MAX} characters, every word in the language
  of the latest turn. Acknowledge briefly or go straight to one sharp question. Never argue with or contradict
  the prospect: a calm line the rep can say without thinking, not a debate.
- Tie it to something specific this prospect said earlier in the call (their team, how they work, their tools,
  volumes, the problem they described), in their words. A line that would fit any call is wrong. Know where
  the call is: on a first conversation do not jump to proposals or closing.
- Never return an objection with an empty say_this: with no approved answer and nothing in the context, still
  acknowledge it in their terms and ask one question that moves it forward.
- For a question, "say_this" is the answer itself, taken only from PRODUCT / OFFER CONTEXT or COMPANY KNOWLEDGE.
  Answer yes or no only when that exact thing (a device, an integration, a feature, a price) is written there;
  never infer it from a general description ("calls and visits" does not mean it works on a phone). If it is
  not written, say_this starts with the rep offering to confirm it, and asks what they need it for.
- say_this is words the rep says to the prospect: never mention "the context", your instructions or what you
  were given. Not known? The rep offers to confirm it, in plain words.
- Facts about the product come only from PRODUCT / OFFER CONTEXT or COMPANY KNOWLEDGE: never invent customers,
  numbers or features. What the prospect said in this call is yours to use.
- When the message lists the team's approved answers (PLAYBOOK), follow its instructions: an approved
  answer for the objection's category gives the approach, said for this conversation. Keep its idea and its claims;
  never swap it for a different tactic or a question of your own.
- "source_id" is the approved answer's id when you followed one, else null.

IF IT IS NOT
Return is_objection=false, objection_type="none" and say_this "". Do not coach, do not suggest anything.

BANNED
"I understand your concern", "Great question", "Absolutely", exclamation marks, lists, more than one sentence in say_this.

OUTPUT
Only valid JSON:
{{
  "is_objection": boolean,
  "objection_type": "price"|"timing"|"authority"|"competitor"|"status_quo"|"trust"|"question"|"other"|"none",
  "source_id": string or null,
  "say_this": string (never empty when is_objection is true: with nothing to claim, acknowledge it in their terms and ask one question)
}}
Only these four keys.
"""

# The Mac app's live help: a meeting, or a call from a dialer ("softphone"). One line, never erased.
LIVE_MODES = frozenset({"meeting", "softphone"})


def system_prompt_for(call_mode: str) -> str:
    return MEETING_SYSTEM_PROMPT if call_mode in LIVE_MODES else SYSTEM_PROMPT


def _approved_answers(snapshot: dict[str, Any]) -> list[str]:
    """One line per published answer: `id · category: answer`. An entry without an answer
    has nothing to say out loud, so it is not offered."""
    lines: list[str] = []
    for entry in snapshot.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "").strip()
        guidance = " ".join(str(entry.get("guidance") or "").split())
        if entry_id and guidance:
            category = str(entry.get("category") or "other").strip() or "other"
            lines.append(f"- {entry_id} · {category}: {guidance}")
    return lines


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
        change = _clip(proof.get("change"), 280)
        if customer or change:
            proof_lines.append("- " + " · ".join(part for part in (customer, change) if part))
    if proof_lines:
        lines.append("Customer proofs (the only ones that exist):")
        lines.extend(proof_lines)
    for competitor in _named_competitors(knowledge.get("competitors"), call_text):
        lines.append(f"Competitor named in the call: {_clip(competitor.get('name'), 60)}")
        how = _clip(competitor.get("how_to_talk"), 300)
        if how:
            lines.append(f"- How to win against it: {how}")
    if not lines:
        return ""
    body = "\n".join(lines)
    room = max_chars - len(_KNOWLEDGE_HEADER) - 1
    if len(body) > room:
        body = body[: max(room - 1, 0)].rstrip() + "…"
    return f"{_KNOWLEDGE_HEADER}\n{body}"


def _shown_block(objection_type: str | None, filler: str | None = None) -> str:
    """The rep already sees this objection's label and is saying its filler line: the answer
    follows it, as the next sentence of what the rep is saying."""
    if not objection_type or objection_type == "none":
        return ""
    said = " ".join((filler or "").split())
    continues = (
        f'THE REP HAS JUST SAID: "{said}" say_this is the next sentence the rep says right after those words: '
        'it adds no second acknowledgement ("Entiendo", "Perfecto", "Genial", "Tiene sentido", "Claro"), drops the '
        "opening acknowledgement of an approved answer and keeps its substance, and never repeats or contradicts those words.\n"
        if said
        else ""
    )
    return (
        f"\nALREADY SHOWN TO THE REP: {objection_type}. "
        f'Answer it: is_objection true, objection_type "{objection_type}", say_this never empty. '
        "If the facts to answer are not in the context, say_this offers to confirm them; never invent.\n"
        f"{continues}"
    )


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
    contact_history: str | None = None,
    objection_type: str | None = None,
    filler: str | None = None,
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
    history = (contact_history or "").strip()
    history_block = (
        "\nTHIS CONTACT BEFORE (earlier calls; use it to anticipate and stay consistent, "
        f"never claim it was said in this call):\n{history}\n"
        if history
        else ""
    )
    base = f"""CALL MODE: {call_mode}
PREFERRED LANGUAGE HINT: {language}
SPEAKER ROLE: {role}
SPEAKER HINT: {role_hint}

PRODUCT / OFFER CONTEXT:
{context}
{knowledge_block}{history_block}
ROLLING TRANSCRIPT (recent):
{transcript_window.strip() or "(empty)"}

LATEST TURN (trigger):
{latest_turn.strip() or "(empty)"}
{_shown_block(objection_type, filler)}
Coach the rep NOW. JSON only."""

    if playbook_snapshot:
        answers = _approved_answers(playbook_snapshot)
        suffix = PLAYBOOK_USER_SUFFIX.replace(
            "{{entries}}",
            "\n".join(answers) if answers else "(no approved answers yet)",
        )
        return f"{base}\n\n{suffix.strip()}"
    return base
