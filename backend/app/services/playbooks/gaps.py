"""What Vocify still has to ask the Head of Sales to complete the playbook.

No fixed form: a short list built from three sources, in this order.
  real      a question or objection prospects raised in live calls that got no approved answer (the live-help log:
            `is_objection` true and no `source_id`), most repeated first;
  conflict  a fact two pieces of material give with different figures (a price, a plan);
  topic     the typical questions every prospect ends up asking (price, integrations, security, set-up time,
            support, limits, contract, who decides, competition) that no own question of the team covers yet.
Answering a gap becomes an own objection (category `custom`) of the playbook, which live help already reads.

Pure apart from `recent_suggest_events`, which reads the log and gives nothing when the read fails.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

LIVE_EVENTS_TABLE = "live_assist_events"
MAX_GAPS = 10
MIN_REAL_CHARS = 12
EXAMPLE_CHARS = 160

# key -> (words that show an own question already covers it, the typical question in Spanish, in English).
TOPICS: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("pricing", ("precio", "precios", "tarifa", "tarifas", "plan", "planes", "cuesta", "coste", "price", "pricing", "cost"),
     "¿Cuánto cuesta?", "How much does it cost?"),
    ("integrations", ("integra", "integracion", "integraciones", "conecta", "api", "integration", "integrations", "integrates", "connects"),
     "¿Se integra con nuestras herramientas?", "Does it integrate with our tools?"),
    ("security", ("seguridad", "datos", "rgpd", "gdpr", "privacidad", "servidores", "cifrado", "security", "privacy", "servers", "encryption", "data"),
     "¿Dónde se guardan nuestros datos y qué seguridad tenéis?", "Where is our data stored and how secure is it?"),
    ("onboarding", ("implantacion", "implementacion", "onboarding", "tarda", "plazo", "plazos", "setup", "implementation"),
     "¿Cuánto se tarda en ponerlo en marcha?", "How long does it take to get started?"),
    ("support", ("soporte", "asistencia", "support", "help"),
     "¿Qué soporte tenéis?", "What support do you offer?"),
    ("limits", ("limite", "limites", "maximo", "usuarios", "capacidad", "limit", "limits", "maximum", "seats"),
     "¿Tiene límites de usuarios o de uso?", "Are there limits on users or usage?"),
    ("contract", ("contrato", "permanencia", "renovacion", "cancelar", "baja", "contract", "renewal", "cancel", "commitment"),
     "¿Hay permanencia? ¿Cómo se renueva o se cancela?", "Is there a commitment? How do I renew or cancel?"),
    ("decision", ("decide", "decisor", "decisores", "aprobacion", "approval", "decision"),
     "¿Quién suele decidir la compra en vuestros clientes?", "Who usually decides the purchase at your customers?"),
    ("competition", ("competencia", "competidor", "competidores", "diferencia", "diferenciamos", "competitor", "competitors", "difference"),
     "¿En qué os diferenciáis de la competencia?", "How are you different from the competition?"),
)

_FIELD_NAMES = {
    "es": {"icp": "a quién vendéis", "bad_fit": "a quién no vendéis", "value_short": "vuestra propuesta de valor",
           "value_long": "vuestra propuesta de valor", "pricing": "los precios", "notes": "las notas"},
    "en": {"icp": "who you sell to", "bad_fit": "who you do not sell to", "value_short": "your value story",
           "value_long": "your value story", "pricing": "pricing", "notes": "the notes"},
}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

_ANSWER_REQUEST = (
    'The prospect asks or says: "{example}". The manager answers below. Add (or update) the company\'s own objection '
    "for it (category custom): label = a 2 to 6 word name of the question, trigger = how the prospect says it, "
    "guidance = the manager's answer in the manager's own words, adding nothing the manager did not say."
)
_CONFLICT_REQUEST = (
    'The material disagrees about {field}. Saved so far: "{old}". New: "{new}". The manager says below which is right: '
    "keep exactly that version in the company notes, changing nothing else."
)


@dataclass(frozen=True)
class Gap:
    """One thing to ask. `question` is what the Head of Sales reads (in the company language); `request` is the
    instruction for the model that applies the answer; `seen` how many real cards hit it; `example` the prospect's
    own words when there are any; `motion_key` the call type it came up in."""

    key: str
    kind: str
    question: str
    request: str
    seen: int
    example: Optional[str]
    motion_key: Optional[str]

    def as_dict(self) -> dict:
        return asdict(self)


def gap_from_dict(data: dict) -> Gap:
    return Gap(
        key=str(data["key"]), kind=str(data["kind"]), question=str(data["question"]), request=str(data["request"]),
        seen=int(data.get("seen") or 0), example=data.get("example"), motion_key=data.get("motion_key"),
    )


def _fold(text: Any) -> str:
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _lang(lang: str) -> str:
    return "en" if str(lang or "").lower().startswith("en") else "es"


def _covered(keywords: tuple[str, ...], entries: list[dict]) -> bool:
    words: set[str] = set()
    for entry in entries:
        if entry.get("category") != "custom":
            continue
        words.update(_fold(" ".join(str(entry.get(k) or "") for k in ("label", "trigger", "guidance"))).split())
    return any(keyword in words for keyword in keywords)


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _topic_gaps(entries: list[dict], lang: str) -> list[Gap]:
    out = []
    for key, keywords, es, en in TOPICS:
        if _covered(keywords, entries):
            continue
        example = en if lang == "en" else es
        question = (
            f"A customer asks “{example}” What do you answer?" if lang == "en"
            else f"Un cliente pregunta «{example}» ¿Qué respondéis?"
        )
        out.append(Gap(f"topic:{key}", "topic", question, _ANSWER_REQUEST.format(example=example), 0, example, None))
    return out


def _real_gaps(events: list[dict], lang: str) -> list[Gap]:
    groups: dict[str, list[dict]] = {}
    for item in events:
        turn = " ".join(str(item.get("latest_turn") or "").split())
        if not item.get("is_objection") or item.get("source_id") or len(turn) < MIN_REAL_CHARS:
            continue
        groups.setdefault(_fold(turn)[:80], []).append({**item, "latest_turn": turn})
    out = []
    for folded, rows in groups.items():
        example = _clip(rows[0]["latest_turn"], EXAMPLE_CHARS)
        motion = Counter(r.get("sales_motion_key") for r in rows if r.get("sales_motion_key")).most_common(1)
        question = (
            f"A customer said “{example}” What do you answer?" if lang == "en"
            else f"Un cliente dijo «{example}» ¿Qué respondéis?"
        )
        digest = hashlib.sha1(folded.encode("utf-8")).hexdigest()[:10]
        out.append(Gap(f"real:{digest}", "real", question, _ANSWER_REQUEST.format(example=example), len(rows), example, motion[0][0] if motion else None))
    return sorted(out, key=lambda g: (-g.seen, g.example or ""))


def detect_conflicts(existing: dict, found: dict, lang: str) -> list[Gap]:
    """Facts in `found` (a new piece of material) that disagree with `existing` (what is saved): both have the text
    and the figures in them differ. Texts without figures are never a conflict."""
    lang = _lang(lang)
    out = []
    for field, names in _FIELD_NAMES[lang].items():
        old, new = str((existing or {}).get(field) or "").strip(), str((found or {}).get(field) or "").strip()
        if not old or not new:
            continue
        old_numbers, new_numbers = set(_NUMBER.findall(old)), set(_NUMBER.findall(new))
        if not old_numbers or not new_numbers or old_numbers == new_numbers:
            continue
        a, b = _clip(old, 120), _clip(new, 120)
        question = (
            f"Your material does not agree about {names}: “{a}” versus “{b}”. Which one is right?" if lang == "en"
            else f"Tu material no coincide sobre {names}: «{a}» frente a «{b}». ¿Cuál es el correcto?"
        )
        out.append(Gap(f"conflict:{field}", "conflict", question, _CONFLICT_REQUEST.format(field=field, old=a, new=b), 0, None, None))
    return out


def build_gaps(
    *, entries: list[dict], knowledge: dict, events: list[dict], lang: str, limit: int = MAX_GAPS,
    conflicts: Optional[list[Gap]] = None,
) -> list[Gap]:
    """Up to `limit` gaps, most useful first: real questions (most repeated first), then the given conflicts, then
    the typical topics nobody covered. `knowledge` is accepted for callers that have it; topics only look at the
    team's own questions because only those reach a live card."""
    del knowledge
    lang = _lang(lang)
    gaps = _real_gaps(events, lang) + list(conflicts or []) + _topic_gaps(entries, lang)
    return gaps[:limit]


def recent_suggest_events(supabase: Any, company_id: str, *, days: int = 28, limit: int = 500) -> list[dict]:
    """The company's live-help cards of the last `days`, newest first. [] when the log cannot be read."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            supabase.table(LIVE_EVENTS_TABLE)
            .select("id,created_at,sales_motion_key,latest_turn,objection_type,entry_id,is_objection,source_id,say_this,capture_id")
            .eq("company_id", company_id)
            .eq("kind", "suggest")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        return []
    return list(getattr(result, "data", None) or [])
