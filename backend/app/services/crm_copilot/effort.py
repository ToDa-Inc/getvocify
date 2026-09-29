"""How hard a question is, decided before the model runs, so reasoning is spent where it pays.

A lookup ("connection rate in August") is answered by one tool call and a sentence: low effort is as accurate and
faster. Analysis (compare, combine sources, why, what should I do) benefits from thinking. Clear cases are decided
here for free; only the ambiguous middle goes to Jev, the repo's typed classifier, with a short timeout and a safe
default (low) when it is unavailable or unsure.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

LOW, HIGH = "low", "high"
SHORT_WORDS = 10
LONG_WORDS = 25
JEV_TIMEOUT_SEC = 1.5

_HIGH = re.compile(
    r"\b(compar\w*|versus|vs\.?|frente a|respecto (a|de)|evoluci\w+|tendencia|trend|"
    r"por qu[eé]|why|c[oó]mo (deber[ií]a|puedo|mejoro|abordo|respondo|manejo)|how (should|can|do) i|how to|"
    r"qu[eé] (debo|hago|priorizo|har[ií]as)|what should|estrategia|strategy|plan de|recomiend\w*|recommend\w*|aconsej\w*|"
    r"analiza\w*|analy[sz]e|diagn[oó]stic\w*|resumen general|datos generales|overview|c[oó]mo va(mos)?|how (are|is) we|"
    r"mejorar|improve|coaching|entren\w+|prior[ií]z\w*|prioriti[sz]e|prep[aá]rame|prepare me|patr[oó]n(es)?|pattern|"
    r"qu[eé] (est[aá]|estamos) (fallando|haciendo mal)|cuello de botella|bottleneck)\b",
    re.I,
)
_ALSO = re.compile(r"\b(y adem[aá]s|adem[aá]s|and also|and then|y luego|despu[eé]s de eso|as well as)\b", re.I)

EFFORT_QUESTION = {
    "question": "ask_effort",
    "allowed": ["lookup", "analysis"],
    "on_missing": "unknown",
    "instructions": (
        "lookup: asks for one figure, one record or one list that a single query answers. "
        "analysis: compares periods or people, combines call data with CRM data, asks why or how, or asks for advice, "
        "prioritisation or a plan. If unsure choose unknown."
    ),
}


def heuristic_effort(question: str) -> Optional[str]:
    """LOW or HIGH when the wording settles it, None when it does not."""
    text = (question or "").strip()
    words = len(text.split())
    if _HIGH.search(text) or _ALSO.search(text) or text.count("?") >= 2 or words >= LONG_WORDS:
        return HIGH
    if words <= SHORT_WORDS:
        return LOW
    return None


async def choose_effort(question: str, *, jev: Any = None) -> str:
    settled = heuristic_effort(question)
    if settled:
        return settled
    try:
        if jev is None:
            from app.services.llm.jev import JevClient

            jev = JevClient(timeout=JEV_TIMEOUT_SEC)
        if not getattr(jev, "is_available", True):
            return LOW
        result = await jev.classify_questions({"question": question[:600]}, [EFFORT_QUESTION])
        return HIGH if (result.get("answers") or {}).get("ask_effort") == "analysis" else LOW
    except Exception as exc:  # noqa: BLE001 - routing must never fail a question
        logger.info("effort routing fell back to low: %s", exc)
        return LOW
