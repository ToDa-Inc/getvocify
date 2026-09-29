"""The catalog of call types, with a default rule and a starter template each (playbooks v2, T7).

Pure and DB-free. A company's own types are not here: they carry a rule of their own
(validated by `validate_applies_to`) and no template. The template steps are the ones the
editor used to hold in `src/lib/playbook-editor.ts`; the front now asks `GET /playbooks/catalog`.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

ROLES = ("sdr", "ae", "any")
CHANNELS = ("call", "meeting", "visit")
CONTACTS = ("new", "contacted", "inbound", "any")

MAX_STAGES = 50
MAX_STAGE_ID = 100


class RuleError(ValueError):
    """Raised for an `applies_to` that does not fit the schema. The API answers 422 bad_rule."""

    code = "bad_rule"


def _step(step_id: str, label_es: str, criterion_es: str, label_en: str, criterion_en: str) -> dict:
    return {
        "step_id": step_id,
        "es": {"step_id": step_id, "label": label_es, "criterion": criterion_es},
        "en": {"step_id": step_id, "label": label_en, "criterion": criterion_en},
    }


_TYPES: tuple[dict, ...] = (
    {
        "key": "discovery",
        "role": "sdr",
        "goal": "meeting_booked",
        "label": {"es": "Llamada en frío", "en": "Cold call"},
        "applies_to": {"role": "sdr", "channels": ["call"], "contact": "any", "deal_stages": []},
        "steps": (
            _step("opening", "Apertura con permiso",
                  "Se presenta y pide unos segundos antes de contar nada.",
                  "Opening with permission",
                  "Introduces themselves and asks for a few seconds before pitching."),
            _step("reason", "Motivo concreto",
                  "Conecta la llamada con algo del prospecto: su sector, su rol o algo que hizo.",
                  "Specific reason",
                  "Ties the call to something about the prospect: their industry, role or something they did."),
            _step("pain", "Descubrir el dolor",
                  "El prospecto nombra un problema concreto con sus palabras.",
                  "Find the pain",
                  "The prospect names a concrete problem in their own words."),
            _step("qualify", "Cualificar",
                  "Confirma quién decide y cuándo quieren resolverlo.",
                  "Qualify",
                  "Confirms who decides and when they want to solve it."),
            _step("meeting", "Reunión con día y hora",
                  "Propone un día y una hora y el prospecto acepta.",
                  "Meeting with day and time",
                  "Proposes a day and time and the prospect accepts."),
        ),
    },
    {
        "key": "inbound",
        "role": "sdr",
        "goal": "meeting_booked",
        "label": {"es": "Lead inbound", "en": "Inbound lead"},
        "applies_to": {"role": "sdr", "channels": ["call"], "contact": "inbound", "deal_stages": []},
        "steps": (
            _step("reference", "Referencia a su solicitud",
                  "Menciona lo que el lead pidió o rellenó antes de hacer ninguna pregunta.",
                  "Reference to their request",
                  "Mentions what the lead asked for or filled in before asking any question."),
            _step("trigger", "Qué le hizo pedir info",
                  "Pregunta qué le llevó a pedir información y el lead lo cuenta.",
                  "What made them ask",
                  "Asks what led them to request information and the lead explains it."),
            _step("qualify", "Cualificar",
                  "Confirma quién decide, para cuándo lo necesita y con qué presupuesto cuenta.",
                  "Qualify",
                  "Confirms who decides, when they need it and what budget they have."),
            _step("meeting", "Reunión con día y hora",
                  "Propone un día y una hora y el lead acepta.",
                  "Meeting with day and time",
                  "Proposes a day and time and the lead accepts."),
        ),
    },
    {
        "key": "ae_discovery",
        "role": "ae",
        "goal": "demo_booked",
        "label": {"es": "Discovery", "en": "Discovery"},
        # With no CRM stages it only matches the first meeting of a deal: contact "new" = no
        # earlier memo on that deal or contact.
        "applies_to": {"role": "ae", "channels": ["meeting", "visit", "call"], "contact": "new", "deal_stages": []},
        "steps": (
            _step("agenda", "Agenda",
                  "Abre con la agenda y lo que se quiere saber al final de la reunión.",
                  "Agenda",
                  "Opens with the agenda and what should be clear by the end of the meeting."),
            _step("current", "Situación actual",
                  "El prospecto explica cómo lo hace hoy y con qué herramientas.",
                  "Current situation",
                  "The prospect explains how they do it today and with which tools."),
            _step("pain_impact", "Dolor e impacto",
                  "El prospecto nombra el problema y lo que le cuesta en tiempo o dinero.",
                  "Pain and impact",
                  "The prospect names the problem and what it costs in time or money."),
            _step("decision", "Quién decide y cómo",
                  "Identifica quién decide, quién más interviene y cómo se decide.",
                  "Who decides and how",
                  "Identifies who decides, who else is involved and how the decision is made."),
            _step("next_meeting", "Siguiente reunión",
                  "Acuerdan la fecha y la hora de la siguiente reunión, demo incluida.",
                  "Next meeting",
                  "They agree the date and time of the next meeting, demo included."),
        ),
    },
    {
        "key": "closing",
        "role": "ae",
        "goal": "proposal_and_close",
        "label": {"es": "Demo y cierre", "en": "Demo and close"},
        "applies_to": {"role": "ae", "channels": ["meeting", "visit"], "contact": "any", "deal_stages": []},
        "steps": (
            _step("agenda", "Agenda y objetivo",
                  "Abre con la agenda y con lo que se quiere decidir al final de la reunión.",
                  "Agenda and goal",
                  "Opens with the agenda and what should be decided by the end of the meeting."),
            _step("recap_pain", "Repasar el dolor",
                  "Confirma con el prospecto el problema que se habló antes.",
                  "Recap the pain",
                  "Confirms with the prospect the problem discussed before."),
            _step("demo", "Demo enfocada",
                  "Enseña solo lo que resuelve el problema confirmado.",
                  "Focused demo",
                  "Shows only what solves the confirmed problem."),
            _step("objections", "Resolver dudas",
                  "Responde las dudas del prospecto hasta que quedan resueltas o claras.",
                  "Handle concerns",
                  "Answers the prospect's concerns until they are resolved or clear."),
            _step("next_step", "Siguiente paso",
                  "Acuerdan el siguiente paso con fecha: propuesta, prueba o firma.",
                  "Next step",
                  "They agree the next step with a date: proposal, trial or signature."),
        ),
    },
    {
        "key": "negotiation",
        "role": "ae",
        "goal": "close_date",
        "label": {"es": "Propuesta y negociación", "en": "Proposal and negotiation"},
        # Only matches when the company picked CRM stages: without them it would swallow every meeting.
        "applies_to": {"role": "ae", "channels": ["meeting", "visit", "call"], "contact": "any", "deal_stages": []},
        "requires_stages": True,
        "steps": (
            _step("recap_proposal", "Repasar la propuesta",
                  "Repasa con el prospecto lo que incluye la propuesta y su precio.",
                  "Review the proposal",
                  "Walks the prospect through what the proposal includes and its price."),
            _step("decision_makers", "Validar decisores",
                  "Confirma quién más tiene que aprobar y qué necesita cada uno.",
                  "Validate decision makers",
                  "Confirms who else has to approve and what each of them needs."),
            _step("price_terms", "Objeciones de precio y términos",
                  "Responde a las dudas de precio y condiciones sin ceder antes de entender el motivo.",
                  "Price and terms objections",
                  "Answers price and terms concerns without conceding before understanding the reason."),
            _step("close_date", "Fecha de firma",
                  "Acuerdan una fecha concreta para la decisión o la firma.",
                  "Signing date",
                  "They agree a concrete date for the decision or signature."),
        ),
    },
)

_BY_KEY = {entry["key"]: entry for entry in _TYPES}
CATALOG_KEYS: tuple[str, ...] = tuple(entry["key"] for entry in _TYPES)


def is_catalog(key: Optional[str]) -> bool:
    return (key or "").strip() in _BY_KEY


def catalog_order(key: Optional[str]) -> tuple[int, str]:
    """Sort key: catalog types first (in catalog order), then anything else by key."""
    name = (key or "").strip()
    if name in _BY_KEY:
        return (CATALOG_KEYS.index(name), name)
    return (len(CATALOG_KEYS), name)


def catalog_role(key: Optional[str]) -> Optional[str]:
    entry = _BY_KEY.get((key or "").strip())
    return entry["role"] if entry else None


def catalog_goal(key: Optional[str]) -> Optional[str]:
    entry = _BY_KEY.get((key or "").strip())
    return entry["goal"] if entry else None


def catalog_label(key: Optional[str], lang: str = "es") -> Optional[str]:
    entry = _BY_KEY.get((key or "").strip())
    if not entry:
        return None
    return entry["label"].get(lang) or entry["label"]["es"]


def default_applies_to(key: Optional[str]) -> Optional[dict]:
    """A fresh copy of the catalog's default rule, or None for a type outside the catalog."""
    entry = _BY_KEY.get((key or "").strip())
    return deepcopy(entry["applies_to"]) if entry else None


def requires_stages(key: Optional[str]) -> bool:
    """A type that only applies once the company picked CRM stages for it (negotiation)."""
    entry = _BY_KEY.get((key or "").strip())
    return bool(entry and entry.get("requires_stages"))


def template_steps(key: Optional[str], lang: str = "es") -> list[dict]:
    entry = _BY_KEY.get((key or "").strip())
    if not entry:
        return []
    return [dict(step[lang if lang in ("es", "en") else "es"]) for step in entry["steps"]]


def catalog_types() -> list[dict]:
    """The payload of GET /playbooks/catalog."""
    return [
        {
            "key": entry["key"],
            "role": entry["role"],
            "goal": entry["goal"],
            "applies_to": deepcopy(entry["applies_to"]),
            "label": dict(entry["label"]),
            "template": {"es": template_steps(entry["key"], "es"), "en": template_steps(entry["key"], "en")},
        }
        for entry in _TYPES
    ]


def _stage_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise RuleError("deal_stages")
    text = str(value).strip()
    if not text or len(text) > MAX_STAGE_ID:
        raise RuleError("deal_stages")
    return text


def validate_applies_to(raw: Any) -> dict:
    """The rule in its stored shape. Missing optional fields take their "any" value; anything
    that is not in the schema (unknown key, wrong type, unknown value) raises RuleError."""
    if not isinstance(raw, dict) or not raw:
        raise RuleError("shape")
    extra = set(raw) - {"role", "channels", "contact", "deal_stages"}
    if extra:
        raise RuleError("unknown_field")
    role = raw.get("role", "any")
    if role not in ROLES:
        raise RuleError("role")
    channels_raw = raw.get("channels", [])
    if not isinstance(channels_raw, list) or any(c not in CHANNELS for c in channels_raw):
        raise RuleError("channels")
    channels = list(dict.fromkeys(channels_raw))
    contact = raw.get("contact", "any")
    if contact not in CONTACTS:
        raise RuleError("contact")
    stages_raw = raw.get("deal_stages", [])
    if not isinstance(stages_raw, list) or len(stages_raw) > MAX_STAGES:
        raise RuleError("deal_stages")
    stages = list(dict.fromkeys(_stage_id(item) for item in stages_raw))
    return {"role": role, "channels": channels, "contact": contact, "deal_stages": stages}


def effective_applies_to(key: Optional[str], stored: Any) -> Optional[dict]:
    """The rule a type routes with: the one saved for the company if it is valid, else the
    catalog default, else None (a legacy custom type with no rule is never routed to)."""
    if stored:
        try:
            return validate_applies_to(stored)
        except RuleError:
            pass
    return default_applies_to(key)
