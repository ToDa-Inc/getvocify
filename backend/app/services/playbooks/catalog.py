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
                  "Pregunta cómo lo hacen hoy y repregunta por lo que no les funciona.",
                  "Find the pain",
                  "Asks how they handle it today and follows up on what isn't working."),
            _step("qualify", "Cualificar",
                  "Confirma quién decide y cuándo quieren resolverlo.",
                  "Qualify",
                  "Confirms who decides and when they want to solve it."),
            _step("meeting", "Reunión con día y hora",
                  "Propone un día y una hora concretos para la reunión.",
                  "Meeting with day and time",
                  "Proposes a specific day and time for the meeting."),
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
                  "Pregunta qué le llevó a pedir información.",
                  "What made them ask",
                  "Asks what led them to request information."),
            _step("qualify", "Cualificar",
                  "Confirma quién decide, para cuándo lo necesita y con qué presupuesto cuenta.",
                  "Qualify",
                  "Confirms who decides, when they need it and what budget they have."),
            _step("meeting", "Reunión con día y hora",
                  "Propone un día y una hora concretos para la reunión.",
                  "Meeting with day and time",
                  "Proposes a specific day and time for the meeting."),
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
                  "Pregunta cómo lo hacen hoy y con qué herramientas.",
                  "Current situation",
                  "Asks how they do it today and with which tools."),
            _step("pain_impact", "Dolor e impacto",
                  "Pregunta por el problema y por lo que les cuesta en tiempo o dinero.",
                  "Pain and impact",
                  "Asks about the problem and what it costs them in time or money."),
            _step("decision", "Quién decide y cómo",
                  "Identifica quién decide, quién más interviene y cómo se decide.",
                  "Who decides and how",
                  "Identifies who decides, who else is involved and how the decision is made."),
            _step("next_meeting", "Siguiente reunión",
                  "Propone fecha y hora para la siguiente reunión, demo incluida.",
                  "Next meeting",
                  "Proposes a date and time for the next meeting, demo included."),
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
                  "Responde cada duda del prospecto y comprueba si queda resuelta.",
                  "Handle concerns",
                  "Answers each of the prospect's concerns and checks it is resolved."),
            _step("next_step", "Siguiente paso",
                  "Propone el siguiente paso con fecha: propuesta, prueba o firma.",
                  "Next step",
                  "Proposes the next step with a date: proposal, trial or signature."),
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
                  "Propone una fecha concreta para la decisión o la firma.",
                  "Signing date",
                  "Proposes a concrete date for the decision or signature."),
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


# --- qualification templates (three-layer model, section 15) --------------------------------------
# "What has to come out of the call", pre-filled for the frameworks a Head of Sales names. They are
# offered, never applied on their own: a playbook only holds the criteria the company chose.
# Same shape as a stored criterion; `good` / `bad` are how a good / bad answer sounds.


def _crit(criterion_id: str, es: tuple[str, str, str, str], en: tuple[str, str, str, str]) -> dict:
    def side(values: tuple[str, str, str, str]) -> dict:
        label, why, good, bad = values
        return {"criterion_id": criterion_id, "label": label, "why": why, "good": good, "bad": bad}

    return {"criterion_id": criterion_id, "es": side(es), "en": side(en)}


_BUDGET = _crit(
    "budget",
    ("Presupuesto", "Sin dinero asignado, el interés no se convierte en compra.",
     "Nombra una cifra, un rango o la partida de la que saldría.",
     "«Aún no lo hemos hablado» o esquiva dar un número."),
    ("Budget", "Without money set aside, interest does not turn into a purchase.",
     "Names a figure, a range or the budget line it would come from.",
     "\"We haven't discussed it yet\" or avoids giving a number."),
)
_AUTHORITY = _crit(
    "authority",
    ("Quién decide", "Quien habla no siempre es quien firma.",
     "Nombra a quien decide y cómo se aprueba una compra así.",
     "«Tendría que verlo con alguien» sin nombre ni fecha."),
    ("Who decides", "The person on the call is not always the one who signs.",
     "Names who decides and how a purchase like this gets approved.",
     "\"I'd have to check with someone\" with no name or date."),
)
_NEED = _crit(
    "need",
    ("Necesidad", "Solo compra quien tiene un problema que le cuesta algo.",
     "Cuenta el problema con sus palabras y lo que le cuesta.",
     "«Nos vendría bien» sin un ejemplo ni un coste."),
    ("Need", "Only someone with a problem that costs them something buys.",
     "Describes the problem in their own words and what it costs.",
     "\"It would be nice to have\" with no example or cost."),
)
_TIMELINE = _crit(
    "timeline",
    ("Plazo", "Sin fecha, la oportunidad se enfría.",
     "Da una fecha o un hecho que la marca, como un cierre de trimestre o una renovación.",
     "«Algún día» o «más adelante»."),
    ("Timeline", "Without a date, the opportunity goes cold.",
     "Gives a date, or an event that sets it, like a quarter close or a renewal.",
     "\"Someday\" or \"later on\"."),
)
_METRICS = _crit(
    "metrics",
    ("Métricas", "Sin un número que mejorar no se justifica la compra.",
     "Da el indicador que quiere mover y de cuánto a cuánto.",
     "«Queremos mejorar» sin decir qué indicador."),
    ("Metrics", "Without a number to improve, the purchase is hard to justify.",
     "Gives the indicator they want to move and from what to what.",
     "\"We want to get better\" with no indicator."),
)
_ECONOMIC_BUYER = _crit(
    "economic_buyer",
    ("Comprador económico", "Es quien libera el presupuesto y puede decir sí o no.",
     "Nombra a quien firma y dice si el comercial ya habló con esa persona.",
     "«Lo decide dirección» sin un nombre."),
    ("Economic buyer", "They release the budget and can say yes or no.",
     "Names who signs and says whether the rep has already spoken to them.",
     "\"Management decides\" with no name."),
)
_DECISION_CRITERIA = _crit(
    "decision_criteria",
    ("Criterios de decisión", "Son las reglas con las que va a elegir.",
     "Enumera lo que comparará y qué pesa más.",
     "«Lo que mejor nos encaje» sin concretar."),
    ("Decision criteria", "They are the rules the buyer will choose by.",
     "Lists what they will compare and what weighs most.",
     "\"Whatever fits us best\" with no detail."),
)
_DECISION_PROCESS = _crit(
    "decision_process",
    ("Proceso de decisión", "Cada paso hasta la firma es un sitio donde la compra puede pararse.",
     "Cuenta los pasos, quién interviene en cada uno y en qué fechas.",
     "«Ya os diremos» sin pasos ni fechas."),
    ("Decision process", "Every step to signature is a place the deal can stall.",
     "Walks through the steps, who is involved in each and the dates.",
     "\"We'll let you know\" with no steps or dates."),
)
_PAPER_PROCESS = _crit(
    "paper_process",
    ("Trámites de compra", "Legal, compras o seguridad pueden frenar una compra ya decidida.",
     "Dice qué revisan (contrato, compras, seguridad) y cuánto suele tardar.",
     "«Eso ya lo veremos al final»."),
    ("Paper process", "Legal, procurement or security can stall a purchase that is already decided.",
     "Says what they review (contract, procurement, security) and how long it usually takes.",
     "\"We'll deal with that at the end\"."),
)
_IDENTIFY_PAIN = _crit(
    "identify_pain",
    ("Dolor identificado", "La urgencia nace de un problema concreto, no del producto.",
     "Nombra el problema y quién lo sufre en su día a día.",
     "Habla de mejoras generales, no de un problema."),
    ("Identified pain", "Urgency comes from a specific problem, not from the product.",
     "Names the problem and who suffers it day to day.",
     "Talks about general improvements, not a problem."),
)
_CHAMPION = _crit(
    "champion",
    ("Champion", "Alguien dentro que quiere que salga adelante y mueve la compra.",
     "Una persona concreta se ofrece a presentar o defender la propuesta.",
     "Escucha con interés, pero no se compromete a nada."),
    ("Champion", "Someone inside who wants it to happen and pushes the purchase.",
     "A specific person offers to present or defend the proposal.",
     "Friendly, but commits to nothing."),
)
_COMPETITION = _crit(
    "competition",
    ("Alternativas", "Saber con qué le compara el cliente marca cómo defender la propuesta.",
     "Nombra a quién más mira, o dice cómo lo resuelve hoy (Excel, a mano, otro proveedor).",
     "«No miramos nada más» sin decir cómo lo hace hoy."),
    ("Alternatives", "Knowing what the buyer compares you with sets how to defend the proposal.",
     "Names who else they are looking at, or how they solve it today (Excel, by hand, another vendor).",
     "\"We're not looking at anything else\" without saying how they do it today."),
)

_QUALIFICATION_TEMPLATES: tuple[dict, ...] = (
    {"key": "bant", "label": "BANT", "criteria": (_BUDGET, _AUTHORITY, _NEED, _TIMELINE)},
    {
        "key": "meddic",
        "label": "MEDDIC",
        "criteria": (_METRICS, _ECONOMIC_BUYER, _DECISION_CRITERIA, _DECISION_PROCESS, _IDENTIFY_PAIN, _CHAMPION),
    },
    {
        "key": "meddpicc",
        "label": "MEDDPICC",
        "criteria": (
            _METRICS, _ECONOMIC_BUYER, _DECISION_CRITERIA, _DECISION_PROCESS,
            _PAPER_PROCESS, _IDENTIFY_PAIN, _CHAMPION, _COMPETITION,
        ),
    },
)
QUALIFICATION_TEMPLATE_KEYS: tuple[str, ...] = tuple(entry["key"] for entry in _QUALIFICATION_TEMPLATES)


def qualification_criteria(key: str, lang: str = "es") -> list[dict]:
    """The criteria of one template ("bant" | "meddic" | "meddpicc") in `lang`; [] for any other key."""
    lang = "en" if lang == "en" else "es"
    for entry in _QUALIFICATION_TEMPLATES:
        if entry["key"] == (key or "").strip().lower():
            return [dict(criterion[lang]) for criterion in entry["criteria"]]
    return []


def qualification_templates() -> list[dict]:
    """The payload of GET /playbooks/qualification-templates."""
    return [
        {
            "key": entry["key"],
            "label": entry["label"],
            "criteria": {"es": qualification_criteria(entry["key"], "es"), "en": qualification_criteria(entry["key"], "en")},
        }
        for entry in _QUALIFICATION_TEMPLATES
    ]
