"""Deterministic guard against generic AI filler in what Vocify writes for a rep.

The prompts already forbid these phrases; this makes it a rule the output cannot slip
past. It never rewrites content: it finds known filler sentences, and callers either ask
the model again (follow-up) or drop the sentence (chat openers/closers).
"""

from __future__ import annotations

import re
import unicodedata

# Email filler and clichés (es/en). Each is a phrase a rep would never write themselves.
_EMAIL_FILLER = (
    r"espero que (te|le|os) encuentres? bien",
    r"espero que (est[eé]s|est[eé]is|este correo)",
    r"como (hablamos|comentamos) (antes|anteriormente)",
    r"quedo a (tu|su|vuestra) (entera |total )?disposici[oó]n",
    r"a (tu|su|vuestra) (entera |total )?disposici[oó]n",
    r"no (dudes|dude|dud[eé]is) en",
    r"(una )?gran oportunidad",
    r"sinergias?",
    r"valor a[nñ]adido",
    r"soluci[oó]n integral",
    r"\b(al|a) (siguiente|otro) nivel\b",
    r"sin m[aá]s dilaci[oó]n",
    r"gracias de antemano",
    r"estar[eé] encantad[oa]",
    r"encantad[oa] de (poder )?ayudar",
    r"cualquier (duda|pregunta|consulta)",
    r"i hope (this|my) (email|message|note) finds you",
    r"hope (you'?re|you are) (doing )?well",
    r"(don'?t|do not) hesitate to",
    r"feel free to (reach out|contact)",
    r"let me know if you have any questions",
    r"looking forward to hearing from you",
    r"great opportunity",
    r"synerg(y|ies)",
    r"circle back",
    r"touch base",
    r"at your earliest convenience",
    r"\bnext level\b",
    r"game[- ]?changer",
    r"just (checking|wanted to check) in",
)

# Chat opener: only a standalone interjection is removed ("¡Claro! Marina…" keeps
# "Marina…"). Never before a comma: "Claro, S.L. tiene 2 deals" names a company.
_CHAT_OPENER = re.compile(
    r"^\s*(¡|!)?\s*(claro( que s[ií])?|por supuesto|desde luego|buena pregunta|excelente pregunta"
    r"|sure|of course|great question|good question|certainly)\s*[!.]+\s*",
    re.IGNORECASE,
)
# Chat closers: offers of more help. Only dropped as the answer's closing sentence, where
# they carry nothing; the same words earlier in an answer may be content.
_CHAT_CLOSER = (
    r"^si (necesitas|quieres) (algo m[aá]s|cualquier otra cosa|m[aá]s (ayuda|informaci[oó]n))",
    r"^(estoy|quedo) (aqu[ií] )?para (lo que necesites|ayudarte)",
    r"^let me know if (you need|there'?s) (anything|something) else",
    r"^(happy|glad) to help",
)

_EMAIL_RE = [re.compile(p, re.IGNORECASE) for p in _EMAIL_FILLER]
_CHAT_RE = [re.compile(p, re.IGNORECASE) for p in _CHAT_CLOSER]
_SENTENCE = re.compile(r"[^.!?\n]*[.!?]+|[^.!?\n]+", re.UNICODE)


def _fold(text: str) -> str:
    """One Unicode form for matching (patterns spell both accented and plain letters)."""
    return unicodedata.normalize("NFC", text or "")


def email_filler(text: str) -> list[str]:
    """The filler phrases found in a follow-up (subject or body), as written."""
    found: list[str] = []
    for pattern in _EMAIL_RE:
        match = pattern.search(_fold(text))
        if not match:
            continue
        phrase = match.group(0).strip()
        if any(phrase.lower() in other.lower() for other in found):
            continue  # already covered by a longer match ("quedo a tu disposición")
        found = [other for other in found if other.lower() not in phrase.lower()]
        found.append(phrase)
    return found


def _sentences(line: str) -> list[str]:
    return [piece for piece in _SENTENCE.findall(line) if piece.strip()]


def drop_sentences(text: str, patterns: list[re.Pattern]) -> str:
    """Removes each sentence that contains a filler phrase; keeps line breaks and every
    other sentence exactly as written. A line left empty by it is removed too."""
    out_lines: list[str] = []
    for line in (text or "").split("\n"):
        pieces = _sentences(line)
        if not pieces:
            out_lines.append(line)
            continue
        kept = [piece for piece in pieces if not any(p.search(piece.strip()) for p in patterns)]
        if not kept and line.strip():
            continue
        out_lines.append("".join(kept).strip() if len(kept) != len(pieces) else line)
    cleaned = "\n".join(out_lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def strip_email_filler(text: str) -> str:
    return drop_sentences(text, _EMAIL_RE)


def strip_chat_filler(text: str) -> str:
    """For Ask answers: the opener interjection and a closing offer of help go; every
    content sentence stays as written. An answer that would end up empty is returned as
    it was."""
    original = (text or "").strip()
    cleaned = _CHAT_OPENER.sub("", original, count=1).strip()
    lines = cleaned.split("\n")
    while lines:
        pieces = _sentences(lines[-1])
        if not pieces or not any(p.search(pieces[-1].strip()) for p in _CHAT_RE):
            break
        rest = "".join(pieces[:-1]).strip()
        if rest:
            lines[-1] = rest
            break
        lines.pop()
    cleaned = "\n".join(lines).strip()
    return cleaned or original


def word_count(text: str) -> int:
    return len((text or "").split())
