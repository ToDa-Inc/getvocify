"""
Intent resolution: rules first, LLM fallback for complex utterances.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.services.llm import LLMClient

logger = logging.getLogger(__name__)

# Rule-based patterns (normalized to lowercase for matching)
APPROVE_PATTERNS = frozenset({
    "1", "approve", "yes", "ok", "okay", "sí", "si", "vale", "go", "go ahead",
    "confirm", "confirmed", "do it", "do it.", "proceed", "correcto", "correct",
})
ADD_PATTERNS = frozenset({
    "2", "add", "edit", "add fields", "edit fields", "añadir", "editar",
    "change", "modify", "add field", "edit field",
})
REJECT_PATTERNS = frozenset({
    "reject", "no", "nope", "wrong", "incorrect", "cancel",
})


@dataclass
class ResolvedIntent:
    """Parsed intent from user message."""

    intent: str  # approve | add_fields | reject | crm_update | unclear
    memo_id: Optional[str] = None
    params: Optional[dict] = None  # For crm_update: property, value, etc.
    confidence: float = 1.0
    by_rules: bool = True  # True if matched by rules, False if by LLM


def _normalize(text: str) -> str:
    """Normalize for rule matching: lowercase, strip, collapse whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def resolve_intent_by_rules(
    text: str,
    state: Optional[str],
    pending_memo_id: Optional[str],
) -> Optional[ResolvedIntent]:
    """
    Rule-based intent resolution.
    Returns ResolvedIntent if rules match, else None (fallback to LLM).
    """
    if not text or not text.strip():
        return None

    normalized = _normalize(text)
    if not normalized:
        return None

    # Exact match
    if normalized in APPROVE_PATTERNS:
        if state != "waiting_approval" or not pending_memo_id:
            return ResolvedIntent(intent="unclear", by_rules=True, confidence=0.5)
        return ResolvedIntent(
            intent="approve",
            memo_id=pending_memo_id,
            by_rules=True,
            confidence=1.0,
        )

    if normalized in ADD_PATTERNS:
        if state != "waiting_approval" or not pending_memo_id:
            return ResolvedIntent(intent="unclear", by_rules=True, confidence=0.5)
        return ResolvedIntent(
            intent="add_fields",
            memo_id=pending_memo_id,
            by_rules=True,
            confidence=1.0,
        )

    if normalized in REJECT_PATTERNS:
        if state != "waiting_approval" or not pending_memo_id:
            return ResolvedIntent(intent="unclear", by_rules=True, confidence=0.5)
        return ResolvedIntent(
            intent="reject",
            memo_id=pending_memo_id,
            by_rules=True,
            confidence=1.0,
        )

    # Legacy: approve:uuid or add:uuid (keep for backwards compatibility)
    if normalized.startswith("approve:"):
        memo_id = normalized[8:].strip()
        if memo_id:
            return ResolvedIntent(intent="approve", memo_id=memo_id, by_rules=True, confidence=1.0)
    if normalized.startswith("add:"):
        memo_id = normalized[4:].strip()
        if memo_id:
            return ResolvedIntent(intent="add_fields", memo_id=memo_id, by_rules=True, confidence=1.0)

    return None


class IntentService:
    """
    Intent resolution: rules first, LLM fallback.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient()

    async def resolve(
        self,
        text: str,
        state: Optional[str],
        pending_memo_id: Optional[str],
        messages: Optional[list[dict]] = None,
        memo_summary: Optional[str] = None,
    ) -> ResolvedIntent:
        """
        Resolve user intent from text.
        Uses rules first; calls LLM only when rules do not match.
        """
        rules_result = resolve_intent_by_rules(text, state, pending_memo_id)
        if rules_result is not None:
            return rules_result

        # LLM fallback for complex utterances
        return await self._resolve_by_llm(
            text=text,
            state=state,
            pending_memo_id=pending_memo_id,
            messages=messages or [],
            memo_summary=memo_summary or "",
        )

    async def _resolve_by_llm(
        self,
        text: str,
        state: Optional[str],
        pending_memo_id: Optional[str],
        messages: list[dict],
        memo_summary: str,
    ) -> ResolvedIntent:
        """Call LLM to interpret intent. Returns unclear on failure."""
        try:
            ctx = "\n".join(
                f"{m.get('direction', '?')}: {m.get('content', '')[:100]}" for m in messages[-10:]
            )
            system = """You analyze WhatsApp replies in a voice-memo-to-CRM workflow.
The user received an extraction summary and can: approve, add/edit fields, reject, or give CRM instructions.
Reply with JSON only: {"intent": "approve"|"add_fields"|"reject"|"crm_update"|"unclear", "memo_id": "uuid or null", "params": {}, "confidence": 0.0-1.0}
- approve: user wants to approve the extraction and push to CRM
- add_fields: user wants to add or edit fields before approving
- reject: user wants to reject/cancel
- crm_update: user gives instructions like "add deal amount 50k" or "add this to HubSpot"
- unclear: cannot determine intent
Current state: """ + (state or "idle")
            if pending_memo_id:
                system += f"\nPending memo_id: {pending_memo_id}"
            if memo_summary:
                system += f"\nMemo summary: {memo_summary[:300]}"
            user_content = f"Conversation:\n{ctx}\n\nUser reply: {text}"
            parsed = await self.llm.chat_json(
                [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
                temperature=0,
            )
            intent = parsed.get("intent", "unclear")
            memo_id = parsed.get("memo_id") or pending_memo_id
            params = parsed.get("params") or {}
            conf = float(parsed.get("confidence", 0.5))
            return ResolvedIntent(
                intent=intent,
                memo_id=memo_id,
                params=params if params else None,
                confidence=conf,
                by_rules=False,
            )
        except Exception as e:
            logger.warning("LLM intent resolution failed: %s", e)
            return ResolvedIntent(intent="unclear", by_rules=False, confidence=0.0)
