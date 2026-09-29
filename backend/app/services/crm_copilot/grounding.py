"""Keep the answer honest: numbers must come from tools, citations must exist, coverage is code."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

_EVIDENCE_TOKEN = re.compile(r"\s?\[((?:ev|pb)-[A-Za-z0-9_-]+)\]")
# A bracketed token with letters and digits ("[m19]", "[c-42]") is an internal id the model copied, not a citation.
_STRAY_ID = re.compile(r"\s?\[(?=[^\]\s]*\d)(?=[^\]\s]*[A-Za-z])[A-Za-z0-9_-]{1,40}\]")
_NUMBER = re.compile(r"(?<![A-Za-z]-)\d+(?:[.,]\d+)*(?:\s?[kKM]\b)?%?")  # "p-99" is an identifier, not a quantity
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# The model counts list items ("3 puntos"). Rejecting every small integer would reject honest answers.
_FREE_INTEGER_MAX = 10
_SEVERITY = {"unavailable": 3, "forbidden": 2, "partial": 1}
_SUFFIX = {"k": 1_000, "m": 1_000_000}


def _canon(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _readings(token: str, *, ambiguous: bool) -> list[str]:
    """What a written number can mean. "1.234" is 1,234 in Spanish and 1.234 in English: an answer may use
    either, but a tool result is always plain JSON, so only the decimal reading applies to facts."""
    body = token.rstrip("%")
    mult = 1
    if body and body[-1] in "kKM":
        mult = _SUFFIX[body[-1].lower()]
        body = body[:-1].rstrip()
    both = "." in body and "," in body
    last = max(body.rfind("."), body.rfind(","))
    try:
        if both:
            decimal_mark = body[last]
            body = body.replace("," if decimal_mark == "." else ".", "").replace(decimal_mark, ".")
            values = [Decimal(body)]
        elif len(re.findall(r"[.,]", body)) > 1:
            values = [Decimal(re.sub(r"[.,]", "", body))]
        elif last >= 0:
            values = [Decimal(body.replace(",", "."))]
            head, tail = body[:last], body[last + 1 :]
            if ambiguous and len(tail) == 3 and head.isdigit() and len(head) <= 3:
                values.append(Decimal(head + tail))
        else:
            values = [Decimal(body)]
    except InvalidOperation:
        return []
    return [_canon(v * mult) for v in values]


def _numbers(text: str) -> set[str]:
    return {r for m in _NUMBER.finditer(text) for r in _readings(m.group(), ambiguous=False)}


def unverified_numbers(answer: str, facts: str, question: str) -> list[str]:
    """Numbers in the answer that no tool result (or the user's own question) contains."""
    allowed = _numbers(facts) | _numbers(question)
    bad: list[str] = []
    for match in _NUMBER.finditer(_EVIDENCE_TOKEN.sub("", answer)):
        token = match.group()
        readings = _readings(token, ambiguous=True)
        if not readings or set(readings) & allowed:
            continue
        primary = readings[0]
        if "." not in primary and not token.endswith("%") and int(primary) <= _FREE_INTEGER_MAX:
            continue
        if token not in bad:
            bad.append(token)
    return bad


def resolve_evidence(answer: str, evidence: list[dict]) -> tuple[str, list[dict]]:
    """Number the citations that exist in this turn's evidence; drop the ones that do not."""
    known = {item["id"]: item for item in evidence if item.get("id")}
    order: list[str] = []

    def swap(match: re.Match) -> str:
        ev_id = match.group(1)
        if ev_id not in known:
            return ""
        if ev_id not in order:
            order.append(ev_id)
        return f" [{order.index(ev_id) + 1}]" if match.group().startswith(" ") else f"[{order.index(ev_id) + 1}]"

    resolved = _EVIDENCE_TOKEN.sub(swap, answer)
    return _STRAY_ID.sub("", resolved).strip(), [known[i] for i in order]


_OFFER = re.compile(
    r"^¿?\s*(quieres|quiere|te (gustaría|interesa|ayudo|puedo)|necesitas|necesita|puedo|do you want|would you like|want me|shall i|should i|can i|need me|need anything)\b"
    r"|^(si (quieres|quiere|te interesa|lo necesitas|necesitas)|if you (want|like|need))\b[^.!?]*\b(puedo|puedes pedirme|te (lo )?(preparo|ayudo|miro|busco|saco|paso)|i can|i could|i'll|i will)\b"
    r"|^(let me know|dime si|avísame)\b",
    re.I,
)


def strip_trailing_offer(answer: str) -> str:
    """Drop a closing "¿Quieres que…?" or "Si quieres, puedo…" the user did not ask for. A lone sentence stays."""
    text = answer.rstrip()
    starts = [m.end() for m in re.finditer(r"(?<=[.!?])\s+|\n+", text)]
    if not starts:
        return answer
    last = text[starts[-1] :].strip()
    if not _OFFER.match(last):
        return answer
    return text[: starts[-1]].rstrip()


def drop_sentences_with(answer: str, bad: list[str]) -> str:
    """Last resort after a failed rewrite: keep what is verified, remove what is not."""
    kept = [s for s in _SENTENCE_END.split(answer) if not any(token in s for token in bad)]
    return " ".join(kept).strip()


def coverage_note(envelopes: list[dict]) -> Optional[dict]:
    """The weakest read of the turn, as data, plus the period when the tool chose it. The UI words it; the model never does."""
    worst: Optional[dict] = None
    for env in envelopes:
        level = env.get("coverage")
        if level not in _SEVERITY:
            continue
        if worst is None or _SEVERITY[level] > _SEVERITY[worst["level"]]:
            worst = {"level": level}
            for key in ("n", "n_analysed", "unit"):
                if env.get(key) is not None:
                    worst[key] = env[key]
        elif level == worst["level"]:
            for key in ("n", "n_analysed", "unit"):
                if key not in worst and env.get(key) is not None:
                    worst[key] = env[key]
    days = next((env["period_days"] for env in envelopes if env.get("period_defaulted") and env.get("period_days")), None)
    if days and worst is None:
        return {"level": "period", "period_days": days}
    if days and worst is not None and worst["level"] not in ("forbidden", "unavailable"):
        worst["period_days"] = days
    return worst
