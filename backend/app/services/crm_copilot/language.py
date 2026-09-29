"""Which language a question is in, decided in code so the reply language never depends on the model."""

from __future__ import annotations

import re
from typing import Optional

_ES = set(
    "que qué el la los las de del un una unos unas es en y con para por mi tu tus mis cómo como cuál cual cuáles cuántas cuántos "
    "cuántos quién quien este esta hola hay se lo al pero más mas está están fue han hizo hice tengo tienen qué dónde cuándo "
    "dame dime muéstrame cuáles equipo llamadas agosto semana mes ayer hoy".split()
)
_EN = set(
    "the a an is are was were of and to in for with my our how what which who whom this that did you your have has had do does "
    "show tell me give how many much last week month today yesterday calls deals team from about on at by".split()
)
_WORD = re.compile(r"[a-záéíóúüñ¿]+")


def reply_language(text: str) -> Optional[str]:
    """"es" or "en", or None when the question is too short or too mixed to say."""
    lowered = (text or "").lower()
    words = _WORD.findall(lowered)
    es = sum(w.strip("¿") in _ES for w in words) + 2 * sum(ch in lowered for ch in "¿¡ñ") + sum(ch in lowered for ch in "áéíóú")
    en = sum(w in _EN for w in words)
    if es == en or max(es, en) < 2:
        return None
    return "es" if es > en else "en"


_HINTS = {"es": "(Responde en español.)", "en": "(Answer in English.)"}


def answer_hint(language: Optional[str]) -> Optional[str]:
    """Appended to the last user turn of the request, never stored: the last words a model reads outweigh a rule in the system prompt."""
    return _HINTS.get(language or "")
