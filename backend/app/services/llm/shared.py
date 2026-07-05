"""Shared LLM utilities: JSON extraction, amount parsing, message conversion."""

import json
import logging
import re
from typing import Any, Optional

from app.logging_config import DOMAIN_LLM, log_domain

logger = logging.getLogger(__name__)


def extract_json(content: str) -> dict:
    """
    Extract JSON from LLM response. Handles markdown blocks, preamble text,
    and uses json_repair for malformed JSON (common with LLM output).
    """
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", content, re.DOTALL)
    if match:
        candidate = match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            content = candidate

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = content[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            fixed = re.sub(r",\s*}", "}", candidate)
            fixed = re.sub(r",\s*]", "]", fixed)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
            try:
                import json_repair

                parsed = json_repair.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

    try:
        import json_repair

        parsed = json_repair.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    raise ValueError("Failed to parse JSON from LLM response")


def parse_amount(value: Any) -> Optional[float]:
    """Extract numeric value from amount. Handles '500€', '500 euros', '500,000', etc."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"[\s€$£]|euros?|dollars?|usd|eur", "", s, flags=re.I)
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def to_gemini_contents(messages: list[dict]) -> tuple[Optional[str], list[dict]]:
    """
    Split OpenAI-style messages into (system_instruction, contents) for Gemini.
    System messages become system_instruction; user/assistant map to user/model.
    """
    system_parts = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
    system_instruction = "\n\n".join(p for p in system_parts if p) or None

    contents: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        text = str(m.get("content", ""))
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": text}]})

    return system_instruction, contents


def log_json_parsed(parsed: dict) -> None:
    logger.debug(
        "LLM JSON parsed",
        extra=log_domain(
            DOMAIN_LLM,
            "json_parsed",
            keys=list(parsed.keys()) if isinstance(parsed, dict) else [],
        ),
    )


def log_json_failed(error: str, content: str) -> None:
    logger.warning(
        "LLM JSON extraction failed",
        extra=log_domain(
            DOMAIN_LLM,
            "json_failed",
            error=error,
            content_preview=content[:200] if content else "",
        ),
    )
