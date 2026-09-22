"""TypeSafe Jev System One client (via OpenRouter Decisions / System One API).

Fast, structured classification with calibrated probabilities for CRM enumerations
and language triage. Returns typed choices instead of generating prose.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.config import settings
from app.logging_config import DOMAIN_LLM, log_domain

logger = logging.getLogger(__name__)

OPENROUTER_SYSTEMONE_URL = "https://openrouter.ai/api/v1/systemone"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
DEFAULT_TIMEOUT_SEC = 4.0
MIN_CONFIDENCE_THRESHOLD = 0.50
MAX_STATE_CHARS = 16000


class JevClient:
    """System One client for fast parallel classification decisions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key = (settings.OPENROUTER_API_KEY or "").strip() if api_key is None else api_key.strip()
        self.model = (model or getattr(settings, "JEV_MODEL", None) or DEFAULT_JEV_MODEL).strip()
        self.timeout = timeout or getattr(settings, "JEV_TIMEOUT_SEC", None) or DEFAULT_TIMEOUT_SEC

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and getattr(settings, "USE_JEV_CLASSIFIER", True))

    async def _post_systemone(
        self,
        state: dict[str, Any],
        questions: dict[str, dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Call OpenRouter System One endpoint. Returns raw answers dict or None on error."""
        if not self.is_available:
            return None
        t0 = time.perf_counter()
        payload = {
            "model": self.model,
            "state": state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.FRONTEND_URL,
            "X-Title": "Vocify",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(OPENROUTER_SYSTEMONE_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                answers = data.get("answers") or {}
                logger.info(
                    "Jev System One call success",
                    extra=log_domain(
                        DOMAIN_LLM,
                        "jev_success",
                        model=data.get("model") or self.model,
                        duration_ms=round(elapsed_ms, 2),
                        questions_count=len(questions),
                        answers_count=len(answers),
                    ),
                )
                return answers
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Jev System One call skipped/failed: %s",
                e,
                extra=log_domain(
                    DOMAIN_LLM,
                    "jev_failed",
                    model=self.model,
                    duration_ms=round(elapsed_ms, 2),
                    error=str(e),
                ),
            )
            return None

    async def classify_enums(
        self,
        transcript: str,
        enum_specs: list[dict],
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
    ) -> dict[str, Any]:
        """Classify CRM dropdown and checkbox fields from transcript in a single Jev pass.

        Returns patch dict structured for apply_enumeration_patch:
        {
            "field_name": "option_value",
            "contact_properties": {"field_name": "option_value"},
            "company_properties": {"field_name": "option_value"},
        }
        """
        if not transcript or not transcript.strip() or not enum_specs:
            return {}

        questions: dict[str, dict[str, Any]] = {}
        spec_map: dict[str, dict] = {}

        for spec in enum_specs:
            name = spec.get("name")
            if not name:
                continue
            options = spec.get("options") or []
            if not options:
                continue

            obj = spec.get("object_type") or "deals"
            q_id = f"{obj}__{name}"
            spec_map[q_id] = spec

            criteria: dict[str, str] = {}
            for o in options[:250]:
                if isinstance(o, dict):
                    v = str(o.get("value", ""))
                    lbl = str(o.get("label") or v)
                else:
                    v = str(o)
                    lbl = str(o)
                if v:
                    criteria[v] = lbl
            criteria["not_stated"] = "The topic was not mentioned or no option fits."

            label = spec.get("label") or name
            desc = (spec.get("description") or "").strip()
            desc_part = f" ({desc})" if desc else ""
            instructions = (
                f"Which option for `{name}` ({label}){desc_part} best matches what the prospect described in `transcript`? "
                "Select 'not_stated' if the topic never came up or was not answered. Do not guess."
            )
            questions[q_id] = {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }

        if not questions:
            return {}

        state = {"transcript": transcript[:MAX_STATE_CHARS]}
        answers = await self._post_systemone(state, questions)
        if not answers:
            return {}

        patch: dict[str, Any] = {
            "contact_properties": {},
            "company_properties": {},
            "deals": {},
        }

        for q_id, ans in answers.items():
            if not isinstance(ans, dict):
                continue
            choice = ans.get("choice")
            conf = float(ans.get("confidence") or 0.0)
            if not choice or choice == "not_stated" or conf < min_confidence:
                continue

            spec = spec_map.get(q_id)
            if not spec:
                continue

            name = spec["name"]
            obj = spec.get("object_type") or "deals"

            if obj == "contacts":
                patch["contact_properties"][name] = choice
            elif obj == "companies":
                patch["company_properties"][name] = choice
            else:
                patch["deals"][name] = choice
                patch[name] = choice

        return patch

    async def classify_questions(
        self,
        state: dict[str, Any],
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Public classifier. A missing, invalid, or low-confidence answer stays on_missing, never false."""
        meta: dict[str, dict[str, Any]] = {}
        payload: dict[str, dict[str, Any]] = {}
        for spec in questions:
            name = str(spec.get("question") or "").strip()
            if not name:
                continue
            allowed = [str(choice) for choice in (spec.get("allowed") or ["unknown"])]
            on_missing = str(spec.get("on_missing") or "unknown")
            meta[name] = {"allowed": allowed, "on_missing": on_missing}
            payload[name] = {
                "type": "choice",
                "instructions": spec.get("instructions")
                or f"Choose one of {', '.join(allowed)} for {name}. If unsure, choose {on_missing}. Do not guess.",
                "criteria": {choice: choice for choice in allowed},
            }

        def unknown_map() -> dict[str, str]:
            return {name: spec["on_missing"] for name, spec in meta.items()}

        answers = await self._post_systemone(state, payload) if payload else None
        if not answers:
            return {"status": "unavailable", "answers": unknown_map()}

        out: dict[str, str] = {}
        any_unknown = False
        for name, spec in meta.items():
            raw = answers.get(name) if isinstance(answers, dict) else None
            choice = raw.get("choice") if isinstance(raw, dict) else None
            try:
                confidence = float(raw.get("confidence") or 0.0) if isinstance(raw, dict) else 0.0
            except (TypeError, ValueError):
                confidence = 0.0
            if choice not in spec["allowed"] or confidence < MIN_CONFIDENCE_THRESHOLD:
                out[name] = spec["on_missing"]
                any_unknown = True
            else:
                out[name] = str(choice)
        return {"status": "partial" if any_unknown else "ready", "answers": out}

    async def detect_language(
        self,
        snippet: str,
        allowed: list[str],
        min_confidence: float = 0.50,
    ) -> Optional[str]:
        """Pick one language code from allowed list (e.g. ['es', 'ca', 'en'])."""
        if not snippet or not snippet.strip() or len(allowed) <= 1:
            return allowed[0] if allowed else None

        criteria: dict[str, str] = {}
        for code in allowed:
            c = code.lower().strip()
            if c == "es":
                criteria["es"] = "Español / Castellano."
            elif c == "ca":
                criteria["ca"] = "Catalán / Valencià (ej. 'tens', 'aquesta', 'més que', 'vacances', 'dolenta')."
            elif c == "en":
                criteria["en"] = "English."
            elif c == "fr":
                criteria["fr"] = "Français."
            elif c == "pt":
                criteria["pt"] = "Português."
            elif c == "it":
                criteria["it"] = "Italiano."
            elif c == "de":
                criteria["de"] = "Deutsch."
            else:
                criteria[c] = f"Language code: {c}"

        questions = {
            "spoken_language": {
                "type": "choice",
                "instructions": "¿En qué idioma se habla principalmente en `snippet`? Elige una opción de las permitidas.",
                "criteria": criteria,
            }
        }

        state = {"snippet": snippet[:4000]}
        answers = await self._post_systemone(state, questions)
        if not answers:
            return None

        ans = answers.get("spoken_language") or {}
        choice = ans.get("choice")
        conf = float(ans.get("confidence") or 0.0)
        if choice and choice in criteria and conf >= min_confidence:
            return choice
        return None
