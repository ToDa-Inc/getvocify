"""
CRM extraction service using LLM.
"""

from __future__ import annotations

import logging
import re
import time

from app.models.memo import MemoExtraction
from app.logging_config import log_domain, DOMAIN_EXTRACTION
from app.metrics import record_extraction_duration, inc_pipeline_error
from app.services.extraction_policy import (
    apply_fill_policies,
    classify_fill_policy,
    fill_policy_instruction,
    format_existing_values_block,
)
from app.services.transcript_turns import (
    prospect_name_from_existing,
    speaker_prompt_legend,
)

logger = logging.getLogger(__name__)
import asyncio
from app.services.llm import JevClient, LLMClient
from app.services.llm.lead_status import (
    LEAD_STATUS_RULES,
    generative_lead_status_to_drop,
    is_lead_status_field,
    lead_status_field_instruction,
)
from typing import Any, Optional


_PLACEHOLDER_VALUES = frozenset({
    "desconocida", "desconocido", "desconocidos", "desconocidas",
    "unknown", "n/a", "na", "none", "null",
    "no especificado", "no especificada", "not specified",
    "no mencionado", "no mencionada", "not mentioned", "no se menciona",
    "sin especificar", "no disponible", "not available",
    "ninguna", "ninguno", "no aplica", "-",
})


def _clean_extracted_name(value: Optional[str]) -> Optional[str]:
    """
    Treat LLM placeholder text ('Desconocida', 'Unknown', 'N/A', ...) as no value.

    LLMs occasionally answer an unresolvable field with a placeholder word instead
    of returning null. Left unchecked, that word becomes a "real" company/contact
    name: it gets used as the deal name, gets written to HubSpot, and worse, gets
    used to *match* future memos onto that same placeholder deal (e.g. a stray
    "Desconocida Deal" silently becoming a magnet for every ambiguous memo). This
    is a defense-in-depth filter, independent of the prompt instructing the LLM
    not to do this - it must hold even if the LLM doesn't comply.
    """
    if not value or not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in _PLACEHOLDER_VALUES:
        return None
    return stripped


def _parse_amount(value: any) -> Optional[float]:
    """Extract numeric value from amount. Handles '500€', '500 euros', '500,000', etc."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # Remove currency symbols and common suffixes
    s = re.sub(r"[\s€$£]|euros?|dollars?|usd|eur", "", s, flags=re.I)
    # Normalize thousands separators
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_raw_extraction(
    extracted: dict, field_specs: Optional[list[dict]] = None
) -> dict:
    """Coerce LLM output to match HubSpot schema types (number, enum value, date)."""
    if not extracted:
        return extracted
    out = dict(extracted)
    spec_map = {
        (s.get("object_type") or "deals", s["name"]): s
        for s in (field_specs or [])
        if s.get("name")
    }
    # Backward-compat: also index by bare name for deal fields
    for s in field_specs or []:
        if s.get("name") and (s.get("object_type") or "deals") == "deals":
            spec_map.setdefault(("deals", s["name"]), s)
            spec_map.setdefault((None, s["name"]), s)

    def _coerce(obj_type: Optional[str], key: str, value: Any) -> Any:
        if value is None:
            return value
        spec = spec_map.get((obj_type or "deals", key)) or spec_map.get((None, key))
        if not spec:
            return value
        field_type = spec.get("type", "string")
        options = spec.get("options", [])
        if field_type == "number":
            parsed = _parse_amount(value)
            return parsed if parsed is not None else value
        if options and isinstance(value, str):
            raw = value.strip()
            raw_l = raw.lower()
            for o in options:
                if isinstance(o, dict):
                    val = o.get("value")
                    lab = o.get("label")
                    if val is not None and raw == val:
                        return val
                    if val is not None and str(val).lower() == raw_l:
                        return val
                    if lab is not None and str(lab).lower() == raw_l:
                        return val
                elif str(o).lower() == raw_l:
                    return o
            return value
        return value

    for key, value in list(out.items()):
        if key in ("contact_properties", "company_properties") and isinstance(value, dict):
            obj = "contacts" if key == "contact_properties" else "companies"
            out[key] = {k: _coerce(obj, k, v) for k, v in value.items()}
            continue
        if key == "line_items" and isinstance(value, list):
            coerced_items = []
            for item in value:
                if isinstance(item, dict):
                    coerced_items.append({k: _coerce("line_items", k, v) for k, v in item.items()})
                else:
                    coerced_items.append(item)
            out[key] = coerced_items
            continue
        out[key] = _coerce("deals", key, value)

    return out


_SPOKEN_NUMBER_WORDS = {
    1: ("uno", "una", "un", "one"),
    2: ("dos", "two"),
    3: ("tres", "three"),
    4: ("cuatro", "four"),
    5: ("cinco", "five"),
    6: ("seis", "six"),
    7: ("siete", "seven"),
    8: ("ocho", "eight"),
    9: ("nueve", "nine"),
    10: ("diez", "ten"),
    11: ("once", "eleven"),
    12: ("doce", "twelve"),
    15: ("quince", "fifteen"),
    20: ("veinte", "twenty"),
    30: ("treinta", "thirty"),
    40: ("cuarenta", "forty"),
    50: ("cincuenta", "fifty"),
}


def number_was_spoken(value: Any, transcript: str) -> bool:
    """True when the extracted number (digits or small word) appears in the transcript."""
    if value is None or not transcript:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    if n != n:  # NaN
        return False
    as_int = int(n) if n == int(n) else None
    if as_int is not None:
        if re.search(rf"(?<!\d){as_int}(?!\d)", transcript):
            return True
        blob = transcript.lower()
        for word in _SPOKEN_NUMBER_WORDS.get(as_int, ()):
            if re.search(rf"\b{re.escape(word)}\b", blob):
                return True
        return False
    rendered = str(value).rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    return bool(re.search(rf"(?<!\d){re.escape(rendered)}(?!\d)", transcript))


def drop_unspoken_numbers(
    extracted: dict,
    transcript: str,
    field_specs: Optional[list[dict]] = None,
) -> dict:
    """Clear numeric CRM fields whose value was not actually said."""
    if not extracted or not transcript:
        return extracted
    number_keys: set[tuple[str, str]] = set()
    for spec in field_specs or []:
        name = spec.get("name")
        if not name or spec.get("type") != "number":
            continue
        obj = spec.get("object_type") or "deals"
        number_keys.add((obj, name))

    out = dict(extracted)
    if isinstance(out.get("contact_properties"), dict):
        out["contact_properties"] = dict(out["contact_properties"])
    if isinstance(out.get("company_properties"), dict):
        out["company_properties"] = dict(out["company_properties"])

    def _maybe_clear(bag: dict, key: str) -> None:
        if key not in bag or bag[key] is None:
            return
        if not number_was_spoken(bag[key], transcript):
            bag[key] = None

    for obj, key in number_keys:
        if obj == "contacts":
            bag = out.get("contact_properties")
            if isinstance(bag, dict):
                _maybe_clear(bag, key)
        elif obj == "companies":
            bag = out.get("company_properties")
            if isinstance(bag, dict):
                _maybe_clear(bag, key)
        else:
            _maybe_clear(out, key)
    return out


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _bag_for_object(extracted: dict, object_type: str) -> dict:
    if object_type == "contacts":
        bag = extracted.get("contact_properties")
        if not isinstance(bag, dict):
            bag = {}
            extracted["contact_properties"] = bag
        return bag
    if object_type == "companies":
        bag = extracted.get("company_properties")
        if not isinstance(bag, dict):
            bag = {}
            extracted["company_properties"] = bag
        return bag
    return extracted


def pending_enumeration_specs(
    extracted: dict,
    field_specs: Optional[list[dict]] = None,
    existing_values: Optional[dict] = None,
) -> list[dict]:
    """Enabled enumerations still empty after the main pass (and empty on the record)."""
    existing_values = existing_values or {}
    pending: list[dict] = []
    for spec in field_specs or []:
        if spec.get("type") != "enumeration" or not spec.get("name"):
            continue
        policy = classify_fill_policy(spec)
        if policy in {"strategy", "identity"}:
            continue
        obj = spec.get("object_type") or "deals"
        existing_bag = existing_values.get(obj) if isinstance(existing_values.get(obj), dict) else {}
        if _value_present((existing_bag or {}).get(spec["name"])):
            continue
        bag = _bag_for_object(extracted, obj)
        if _value_present(bag.get(spec["name"])):
            continue
        pending.append(spec)
    return pending


def apply_enumeration_patch(extracted: dict, patch: dict, specs: list[dict]) -> dict:
    """Merge a second-pass enum JSON object into deal / contact / company bags."""
    if not isinstance(patch, dict) or not specs:
        return extracted
    out = dict(extracted)
    if isinstance(out.get("contact_properties"), dict):
        out["contact_properties"] = dict(out["contact_properties"])
    if isinstance(out.get("company_properties"), dict):
        out["company_properties"] = dict(out["company_properties"])
    allowed = {(s.get("object_type") or "deals", s["name"]) for s in specs if s.get("name")}
    nested_contacts = patch.get("contact_properties") if isinstance(patch.get("contact_properties"), dict) else {}
    nested_companies = patch.get("company_properties") if isinstance(patch.get("company_properties"), dict) else {}
    nested_deals = patch.get("deals") if isinstance(patch.get("deals"), dict) else {}
    nested_contacts_obj = patch.get("contacts") if isinstance(patch.get("contacts"), dict) else {}
    nested_companies_obj = patch.get("companies") if isinstance(patch.get("companies"), dict) else {}

    def _lookup(obj: str, name: str):
        candidates = []
        if obj == "contacts":
            candidates.extend([nested_contacts.get(name), nested_contacts_obj.get(name)])
        elif obj == "companies":
            candidates.extend([nested_companies.get(name), nested_companies_obj.get(name)])
        else:
            candidates.append(nested_deals.get(name))
        candidates.extend([
            patch.get(name),
            patch.get(f"{obj}.{name}"),
        ])
        for value in candidates:
            if _value_present(value):
                return value
        return None

    for obj, name in allowed:
        value = _lookup(obj, name)
        if not _value_present(value):
            continue
        if isinstance(value, str) and value.strip().lower() == "unknown":
            continue
        bag = _bag_for_object(out, obj)
        bag[name] = value
    return out


def drop_abstained_fields(
    extracted: dict,
    names: list[str],
    specs: Optional[list[dict]] = None,
) -> dict:
    """Jev declined these fields. Do not keep the generative guess."""
    wanted = {n for n in names if n}
    if not extracted or not wanted:
        return extracted
    out = dict(extracted)
    if isinstance(out.get("contact_properties"), dict):
        out["contact_properties"] = dict(out["contact_properties"])
    if isinstance(out.get("company_properties"), dict):
        out["company_properties"] = dict(out["company_properties"])
    for spec in specs or []:
        name = spec.get("name")
        if name not in wanted:
            continue
        bag = _bag_for_object(out, spec.get("object_type") or "deals")
        if name in bag:
            bag[name] = None
        if name in out and spec.get("object_type") not in (None, "deals"):
            out[name] = None
    return out


def _enumeration_followup_prompt(transcript: str, specs: list[dict]) -> str:
    lines = []
    for spec in specs:
        obj = spec.get("object_type") or "deals"
        name = spec["name"]
        label = spec.get("label") or name
        options = spec.get("options") or []
        opt_txt = ", ".join(
            f'"{(o.get("value") if isinstance(o, dict) else o)}"={(o.get("label") if isinstance(o, dict) else o)}'
            for o in options
        )
        lines.append(f'- {obj}.{name} ({label}). Options: {opt_txt or "(none)"}')
    fields = "\n".join(lines)
    lead_rules = ""
    if any(is_lead_status_field(spec) for spec in specs):
        lead_rules = f"\nLEAD STATUS:\n{LEAD_STATUS_RULES}\n"
    return f"""The first CRM pass left these enabled enumerations empty.
Fill each from the transcript. Map described reality to the closest option — the speaker will not say the internal value.
Null only if that topic never came up. Never write "unknown" unless they said they do not know (prefer null).
Do not invent numbers. Do not fill pre-call / talk-track fields.

HOW TO MAP (use these even when they never say the option label):
- Sell through a distributor / channel / partners; store reps are not their employees → vocify_sales_motion = partner_channel
- Distributor's people do store visits: still partner_channel, not field_sales (field_sales is the prospect's own sales team)
- They set commercial policy but contracts, tools, or budget go through someone else; they can intro that person → vocify_is_decision_maker = influencer AND vocify_talking_to_decision_maker = influencer_with_path
- Mild interest in the product without a hard no or a signed next-step purchase → vocify_fit = moderate
- They log visits in "their program" but never named HubSpot/Salesforce/etc → crm_utilizado = null
- They did not answer hunting vs farming → vocify_team_new_business = null
- They did not answer whether deals close after a first visit → vocify_decisions_after_contact = null
{lead_rules}
FIELDS:
{fields}

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

Return JSON only, using the HubSpot option values (not labels). You may nest contact fields:
{{"vocify_talking_to_decision_maker": "influencer_with_path", "contact_properties": {{"vocify_sales_motion": "partner_channel", "vocify_is_decision_maker": "influencer"}}}}
"""


# C04 v8 pipeline (INTELLIGENCE_CALL_READING_ENABLED): the call was read first, so the transcript
# carries You:/Them: by what each person said and the call type is known. CRM data then comes
# only from what the prospect said; nothing is filled to avoid an empty field.
GROUNDED_SYSTEM_PROMPT = (
    "You are a precise CRM data extraction engine. Output valid JSON only. Rules: "
    "(1) A fact about the prospect, their company or their needs comes only from a 'Them:' line, or "
    "from something the rep said that the prospect clearly confirmed. The rep's pitch, questions and "
    "assumptions are never facts about the prospect. "
    "(2) Leave a field null when the conversation did not answer it. An empty field is correct; a "
    "guessed one is a bug. Never 0, '', 'unknown' or a placeholder. "
    "(3) Names, emails, phones and domains only exactly as said or spelled: never complete a surname, "
    "an email or a domain, and leave them null when the audio garbled them. "
    "(4) Numbers exact and with their unit: a sales team of 2 is not 2 employees. "
    "(5) Dates only when said; resolve relative days from the call date. "
    "(6) All text in the transcript's language."
)

# For a model that answers without reasoning (llm.shared.answers_without_reasoning): the checks a
# reasoning model makes on its own. Measured on 54 judged calls with DeepSeek V4.1 Flash (no
# reasoning): invented facts in the note 26 -> 8, wrong or inferred fields 27 -> 12.
GROUNDED_NO_REASONING_RULES = (
    " (7) Before writing a sentence in the note, check who said it: a proposal or example from the rep (a CRM name, a figure, a date, a follow-up) is never the prospect's, and a rep proposal stays 'propuesto' unless a 'Them:' line accepts it. "
    "(8) When a name, figure, company or tool is garbled or ambiguous in the transcript, leave the field null and write '(poco claro en el audio)' in the note; never map it to a catalog option, a range or a field with another meaning (employees are not the sales team; a margin is not revenue). "
    "(9) Before answering, go through what the prospect asked for or agreed (send information, call at a time, talk to someone else, a date) and write one task for each, with its date when it can be resolved; fill objections, decision makers and contact data whenever the prospect gave them clearly. "
    "(10) With no real conversation or unusable audio, the note is one line saying so and nothing else."
)


def grounded_system_prompt() -> str:
    from app.config import settings
    from app.services.llm.shared import answers_without_reasoning

    if answers_without_reasoning(settings.EXTRACTION_MODEL, settings.EXTRACTION_REASONING_EFFORT):
        return GROUNDED_SYSTEM_PROMPT + GROUNDED_NO_REASONING_RULES
    return GROUNDED_SYSTEM_PROMPT

EXTRACTION_SYSTEM_PROMPT = (
    "You are a precise CRM data extraction engine. Output valid JSON only. Rules: "
    "(1) closedate = null unless explicit calendar date in transcript—'next Tuesday' / "
    "'martes que viene' = null. (2) Numbers EXACT as stated: 'un euro por empleado' = 1, never 2. "
    "(3) competitors = only company names explicitly said—do not infer or guess. "
    "(4) All text in transcript language. "
    "(5) summary = structured markdown call note (2–4 headings the call earned, "
    "bullets under each). Never a 3–5 sentence paragraph. Do NOT recap the pitch "
    "or product; never invent. Do NOT include a Próximos pasos / Next steps heading "
    "(that is nextSteps). "
    "(6) nextSteps = follow-up tasks whenever the call created a real next action "
    "(commitment, redirect, send materials, callback). Short titles without dates/times; "
    "put timing in parallel nextStepSchedules as ISO YYYY-MM-DD when resolvable, else the "
    "spoken phrase, else empty string. Prefer [] only when nothing actionable was said. "
    "(7) Do not overwrite identity, pre-call, or account-research fields that already have CURRENT VALUES. "
    "(8) Sales-motion / fit fields describe the prospect's company, never how we ran this call. "
    "(9) Enabled CRM enumerations and discovery fields with no CURRENT VALUE must be filled when the "
    "transcript answers them. Map the described reality to the closest allowed option — the speaker "
    "does not need to say the option label. Numbers, amounts, and dates stay exact or null."
)


USER_NOTES_MAX_CHARS = 8000


def user_notes_block(user_notes: Optional[str]) -> str:
    """The rep's own notes steer the summary; the transcript stays the source of truth."""
    notes = (user_notes or "").strip()[:USER_NOTES_MAX_CHARS]
    if not notes:
        return ""
    return f"""
### REP'S OWN NOTES (typed by the rep during the meeting)
\"\"\"
{notes}
\"\"\"
- These are what the rep cares about. The **summary** must cover every point in them, keeping their wording where it fits, and add the specifics from the transcript.
- Facts the rep typed (names, numbers, dates) count as stated and may fill CRM fields.
- If a note contradicts the transcript, follow the transcript. Never invent beyond notes + transcript.
"""


def build_extraction_prompt(
    transcript: str,
    field_specs: Optional[list[dict]] = None,
    glossary_text: str = "",
    source_context: str = "voice_memo",
    product_context: str = "",
    existing_values: Optional[dict] = None,
    call_date: Optional[str] = None,
    user_notes: Optional[str] = None,
) -> str:
    """Build the extraction user prompt without constructing an LLM client."""
    return ExtractionService._build_prompt(
        None,  # type: ignore[arg-type]
        transcript,
        field_specs,
        glossary_text,
        source_context,
        product_context,
        existing_values,
        call_date,
        user_notes=user_notes,
    )



_CALL_TYPE_ES = {
    "cold_first_contact": "primera conversación con este prospecto",
    "follow_up": "seguimiento de un contacto anterior",
    "meeting_confirmation": "confirmación de una reunión ya agendada",
    "meeting_reschedule": "reagendar una reunión",
    "discovery_meeting": "reunión agendada",
    "bad_moment": "el prospecto no podía hablar",
    "gatekeeper": "solo habló con recepción o un asistente",
    "wrong_person": "no era la persona adecuada",
    "dictated_note": "nota dictada por el comercial",
    "other": "otra",
}
# The call reading says nothing was said worth a CRM write: one line, no fields, no tasks.
NO_CRM_CALL_TYPES = frozenset({"no_conversation", "not_a_sales_call"})
# Past this length a "no conversation" reading may be wrong: the CRM pass still runs, in short-note
# mode, so a real call is never left without its note.
NO_CRM_MAX_CHARS = 400
# Where the deal stands is the rep's to declare after the call (with lead status), not inferred.
REP_DECLARED_FIELDS = frozenset({"dealstage"})
SHORT_NOTE_CALL_TYPES = frozenset({"bad_moment", "gatekeeper", "wrong_person"})


_ROLE_TOKENS = frozenset({"you", "them", "rep", "prospect", "s1", "s2"})
_PLACEHOLDER = re.compile(r"^(?:desconocid[oa]s?|unknown|n/?a|no especificad[oa]|sin especificar|ninguno|none|null)\b", re.I)
_EMAIL = re.compile(r"^[^@\s]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$", re.I)
_DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", re.I)


def grounded_cleanup(extracted: dict) -> dict:
    """What the grounded prompt asks for and a model still slips on, enforced: no transcript role
    token ("Them") as a person, no all-empty schedule list."""
    out = dict(extracted or {})

    def is_role(value) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        return text.strip(".:").lower() in _ROLE_TOKENS or bool(_PLACEHOLDER.match(text)) or "desconocid" in text.lower()

    def bad_identity(key: str, value) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        if "email" in key.lower():
            return not _EMAIL.match(value.strip())  # a garbled address is worse than none
        if "domain" in key.lower():
            return not _DOMAIN.match(value.strip().removeprefix("www."))
        return False

    for key in ("contactName", "companyName"):
        if is_role(out.get(key)):
            out[key] = None
    if bad_identity("contactEmail", out.get("contactEmail")):
        out["contactEmail"] = None
    if isinstance(out.get("decisionMakers"), list):
        out["decisionMakers"] = [v for v in out["decisionMakers"] if not is_role(v)]
    for nested in ("contact_properties", "company_properties"):
        props = out.get(nested)
        if isinstance(props, dict):
            out[nested] = {k: (None if is_role(v) or bad_identity(k, v) else v) for k, v in props.items()}
    schedules = out.get("nextStepSchedules")
    if isinstance(schedules, list) and not any(str(v or "").strip() for v in schedules):
        out["nextStepSchedules"] = []
    _mirror_identity(out)
    return out


def _mirror_identity(out: dict) -> None:
    """The contact's name and the company's name the pass already wrote at the top level also
    fill the CRM's own empty name fields, when the schema asked for them."""
    contact = out.get("contact_properties")
    name = str(out.get("contactName") or "").strip()
    if isinstance(contact, dict) and name:
        first, _, last = name.partition(" ")
        if "firstname" in contact and not contact.get("firstname"):
            contact["firstname"] = first
        if "lastname" in contact and not contact.get("lastname") and last:
            contact["lastname"] = last
    company = out.get("company_properties")
    company_name = str(out.get("companyName") or "").strip()
    if isinstance(company, dict) and company_name and "name" in company and not company.get("name"):
        company["name"] = company_name


# Fields the grounded pass may fill without a prospect quote: the note, the tasks, and who the
# contact is (identity is checked as spoken by grounded_cleanup instead).
_NO_EVIDENCE_NEEDED = frozenset({
    "summary", "nextSteps", "nextStepSchedules", "next_step_schedules", "confidence", "evidence",
    "contactName", "contactEmail", "contactPhone", "companyName", "customerPresent", "dealname",
    "contact_properties.firstname", "contact_properties.lastname", "contact_properties.email",
    "contact_properties.phone", "contact_properties.mobilephone", "company_properties.name",
    "company_properties.domain", "company_properties.website", "description",
})


# A prospect's answer that confirms what the salesperson just said ("sois de Shopify, ¿verdad?" "Sí.").
_YES = re.compile(r"^(?:si|sí|exacto|exactamente|correcto|eso es|asi es|efectivamente|claro|yes|right|exactly|correct)\b")
# "Sí, más o menos" confirms nothing.
_HEDGE = re.compile(r"\b(?:mas o menos|no del todo|no exactamente|no se|en parte|sort of|kind of|not exactly)\b")


_YES_WORDS = frozenset({"si", "exacto", "exactamente", "correcto", "claro", "efectivamente", "eso", "es",
                        "asi", "vale", "yes", "right", "exactly", "correct"})


def _plain_yes(reply: str) -> bool:
    return bool(_YES.match(reply)) and not _HEDGE.search(reply[:60])


def _fold_text(text) -> str:
    from app.services.intelligence.extract import _fold

    return _fold(str(text or ""))[0]


def _bare_yes(quote: str) -> bool:
    """Nothing but a yes ("Sí, sí, correcto.", "Sí, más o menos [a lo que preguntó]"): it says
    nothing on its own, unlike "Sí, HubSpot"."""
    from app.services.intelligence.extract import _fold

    words = _fold(re.sub(r"\[[^\]]*\]", " ", str(quote or "")))[0].split()
    rest = " ".join(word for word in words if word not in _YES_WORDS)
    return bool(words) and words[0] in _YES_WORDS and (not rest or bool(_HEDGE.fullmatch(rest)))


def _quote_parts(quote: str) -> list[str]:
    """A model's quote cut back to the stretches it copied: no "[...]" notes, no role marks, and
    split where it joined two places with an ellipsis."""
    text = re.sub(r"\[[^\]]*\]", "|", str(quote or ""))
    text = re.sub(r"\b(?:You|Them)\s*:", "|", text)
    parts = re.split(r"\.{3,}|…|\|", text)
    return [part.strip(" ,;") for part in parts if part.strip(" ,;.")]


def _prospect_said(quote: str, turns: list[tuple[str, str]]) -> bool:
    """The quote is the prospect's: most of it falls in a "Them:" turn (a sentence the audio split
    across two turns still counts), or it is the salesperson's sentence the prospect answered
    with a plain yes."""
    from app.services.intelligence.extract import _fold

    folded_quote, _ = _fold(" ".join(quote.split()))
    if len(folded_quote.split()) < 3:
        return False
    texts = [" ".join(text.split()) for _, text in turns]
    flat = " ".join(texts)
    owner: list[int] = []
    for index, text in enumerate(texts):
        owner.extend([index] * (len(text) + 1))
    folded, where = _fold(flat)
    at = folded.find(folded_quote)
    if at < 0:
        return False
    span = [owner[where[i]] for i in range(at, at + len(folded_quote)) if folded[i] != " "]
    if sum(turns[i][0] == "Them" for i in span) * 2 > len(span):
        return True
    last = span[-1]
    if turns[last][0] != "You" or last + 1 >= len(turns) or turns[last + 1][0] != "Them":
        return False
    asked = "?" in flat[where[at]:sum(len(t) + 1 for t in texts[:last + 1])]
    return asked and _plain_yes(_fold(texts[last + 1])[0])


def _answered(value, quote: str, turns: list[tuple[str, str]]) -> bool:
    """A short answer the model quoted alone ("Sí.", "10.") backs the field only next to the
    question it answered: a yes to a salesperson question that carries the value's own words, or
    the value itself said as the answer to a question."""
    from app.services.intelligence.extract import _fold

    answer = _fold(" ".join(str(quote or "").split()))[0]
    if not answer:
        return False
    for index in range(1, len(turns)):
        (asker, question), (who, reply) = turns[index - 1], turns[index]
        if asker != "You" or who != "Them" or "?" not in question:
            continue
        said = _fold(reply)[0]
        if not said.startswith(answer):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if answer.split()[0] == f"{value:g}":
                return True
        elif isinstance(value, str) and _plain_yes(said):
            words = [w for w in _fold(value)[0].split() if len(w) > 3]
            asked = _fold(question)[0]
            if words and sum(w in asked for w in words) * 10 >= len(words) * 7:
                return True
    return False


# Words that put someone in a decision ("lo decide mi socio", "tengo que hablarlo con mi jefe").
_DECIDES = re.compile(
    r"decid|decis|aprob|aprueb|firm|socio|socia|jefe|jefa|director|responsable|dueno|duena|"
    r"consultarlo|hablarlo con|approv|decide|sign off|boss|partner|owner"
)


def require_prospect_evidence(extracted: dict, transcript: str, *, roles_marked: bool = True) -> dict:
    """Every CRM fact the grounded pass fills needs the prospect's own words behind it: its
    `evidence` quote must be found (ignoring case, accents and punctuation) in a "Them:" turn, or be
    the salesperson's question the prospect answered yes to. A field without one is emptied; what
    only the salesperson said never becomes the prospect's."""
    from app.services.intelligence.extract import _locate, _turns

    out = dict(extracted or {})
    raw_evidence = out.pop("evidence", None)
    # Paths come back as "objections", "objections[0]", "objections.0" or "company_properties.crm":
    # group every quote under its field path, without list indexes.
    evidence: dict[str, list] = {}
    for key, value in (raw_evidence.items() if isinstance(raw_evidence, dict) else []):
        path = re.sub(r"\[\d+\]|\.\d+(?=\.|$)", "", str(key)).strip(". ")
        evidence.setdefault(path, []).extend(value if isinstance(value, list) else [value])
    turns = _turns(transcript) if roles_marked else None
    prospect_text = (
        " ".join(" ".join(text.split()) for who, text in turns if who == "Them") if turns else transcript
    )

    def said(text) -> bool:
        if not isinstance(text, str):
            return False
        if _bare_yes(text):
            return False  # it proves something only next to its question (_answered)
        if len(text.split()) >= 2 and _locate(text, prospect_text):
            return True
        # Long enough stretches of it carry the quote; short bits ("Sí.") prove nothing on their own.
        parts = [part for part in _quote_parts(text) if len(part.split()) >= 3]
        if not parts:
            return False
        if turns:
            return all(_prospect_said(part, turns) for part in parts)
        return all(_locate(part, prospect_text) for part in parts)

    def backed(path: str, value=None) -> bool:
        quotes = evidence.get(path) or evidence.get(path.split(".")[-1]) or []
        return any(said(q) or (turns and _answered(value, q, turns)) for q in quotes)

    def empty(value) -> bool:
        return value in (None, "", [], {})

    for key in list(out):
        value = out[key]
        if key in _NO_EVIDENCE_NEEDED or empty(value):
            continue
        if isinstance(value, dict) and key in ("contact_properties", "company_properties"):
            out[key] = {
                k: (v if empty(v) or f"{key}.{k}" in _NO_EVIDENCE_NEEDED or backed(f"{key}.{k}", v) else None)
                for k, v in value.items()
            }
        elif isinstance(value, (dict, list)) and key == "line_items":
            out[key] = value if backed(key) else []
        elif not backed(key, value):
            if isinstance(value, list):
                # An item the prospect said in so many words ("no me interesa") backs itself.
                out[key] = [item for item in value if said(item)]
            else:
                out[key] = None
    # Being on the call or founding the company does not put someone in the decision: the quote has to.
    if out.get("decisionMakers"):
        quotes = [q for q in evidence.get("decisionMakers") or [] if said(q) or (turns and _answered(None, q, turns))]
        if not any(_DECIDES.search(_fold_text(q)) for q in quotes):
            out["decisionMakers"] = []
    return out


def _grounded_source_hint(call_reading: dict) -> str:
    kind = str(call_reading.get("call_type") or "other")
    marked = call_reading.get("roles_marked", True)
    roles = (
        'Each line starts with "You:" (the salesperson, the Vocify user) or "Them:" (the prospect '
        "or anyone on their side). Those roles were worked out from what each person says: trust them."
        if marked else
        "The transcript has no speaker marks: tell who speaks from what is said. A dictated note is "
        "the salesperson telling what happened in an earlier conversation."
    )
    short = (
        "\nThis call never became a sales conversation: the note is 1–3 bullets with what happened (why "
        "they could not talk, what they asked for). Still fill the contact's name and company when they "
        "said or confirmed them, and any email or referral they gave. A callback or anything else agreed "
        "goes in nextSteps with what was said about when (\"a las 12:30\", \"el lunes\"). Never leave "
        "the note empty when someone answered."
        if kind in SHORT_NOTE_CALL_TYPES | NO_CRM_CALL_TYPES else ""
    )
    seller = str(call_reading.get("rep_company") or "").strip()
    seller_line = (
        f"\nThe salesperson sells for {seller}: that company, its people and its prices are never the prospect's data."
        if seller else ""
    )
    return f"""
### THIS CALL
Type: {_CALL_TYPE_ES.get(kind, kind)} ({kind}). Furthest point reached: {call_reading.get("phase_reached") or "unknown"}.
{roles}{seller_line}{short}
"""


def _grounded_rules(json_structure: str) -> str:
    return f"""### EXTRACTION RULES:
1. **Only what the prospect said**: a CRM field is filled only when a "Them:" line answers it (or the
   prospect clearly confirmed what the salesperson said). The salesperson's pitch, examples, prices and
   assumptions are never facts about the prospect. When the conversation did not answer a field, null.
2. **Strict types**: Output MUST match schema exactly. `number` → numeric only (500, not "500€"), in the
   field's own unit (a sales team of 2 is not numberofemployees 2). `enumeration` → exact allowed value.
   `date` → YYYY-MM-DD only. Never 0, "", "unknown" or a placeholder for "not said".
3. **Enumerations and lists**: choose an option only when the prospect clearly described it; a vague
   hint, the salesperson's own framing or a topic that never came up is null.
   - pains / painPoints: only a difficulty, cost or frustration the prospect says THEY have, in words
     that name it as a problem ("nos cuesta", "perdemos", "no llegamos", "es un lío"). How they work
     today (referrals, a channel, a tool, "el 80% nos viene por boca a boca") is not a pain, nor is a
     problem the salesperson described and the prospect only heard; if they say it is not a problem, null.
   - objections: the prospect's reasons not to move forward. "Estoy en una reunión" or "no soy yo" are
     not objections (they go in the note).
   - products/services offered: what the prospect says their company sells, never the salesperson's
     reading of it, nor partners or tools they use.
   - competitors: only alternatives to what the salesperson sells that the prospect names.
   - An option only when its name or a clear synonym was said: "Drive" is not Pipedrive, "Excel" or
     "no tenemos CRM" is not any CRM option. A catch-all option ("Otros", "Other", "Interno") only
     when they named a tool that is not in the list; "lo hacemos internamente" or "tenemos nuestro
     sistema" without naming it is null.
   - Numbers whose unit was not said (thousands? clients? employees?) stay null, and so does a range
     ("entre 1 y 2 millones"): never pick one end of it. A different thing is not the field's thing
     (an ERP is not a CRM; "solo estoy yo" is not a headcount of the company unless they say so).
   - products/services offered is never the prospect's sector ("foodtech") or the contact's own job.
4. **People and identity**: names, emails, phones and domains exactly as said or spelled; never complete
   a surname, email or domain, null when garbled. When the prospect's name was said, fill it in every
   name field the schema has for the contact (contactName and the contact's first/last name fields).
   The contact is the prospect on the call: the salesperson is never the contact, and a person or
   address they were referred to goes in the note and tasks, not in the contact fields. If the
   prospect no longer works at the company the salesperson called about, do not write that company
   as theirs. The company is the one the prospect works for, said in that sense ("soy de X", "en X
   hacemos"); a shop they are in, a client, a supplier or a brand they mention is not their company,
   and an email or domain is never built from it. decisionMakers only when someone's role in the
   decision was said ("lo decide mi socio", "yo decido", "lo tengo que hablar con mi jefe"); being
   on the call, a founder, or joining a meeting is not enough. Identity fields with a CURRENT VALUE →
   null if the spoken person is different.
5. **summary**: the CRM note a colleague reads before the next touch. Same language as the transcript.
   Markdown. First line: `**Resultado:** <how the call ended, decision first, max 20 words>`.
   Then only headings that carry concrete facts the prospect gave: their situation, figures with units,
   tools, who decides, objections in their words, history with us, the agreed meeting with day and
   time, and what the prospect said THEY will do ("reenviará el correo a su socia"). Every bullet a
   fact (numbers, dates, times, names, roles); no heading without facts, no "se habló de", never the
   salesperson's pitch, never next steps (that is nextSteps). Do not dress the outcome up ("tras
   superar fuertes objeciones"): say what was agreed, as tentatively as it was agreed. A meeting is
   "agreed" only when the prospect said yes to it; one the salesperson proposed and the prospect did
   not confirm is "propuesta, sin confirmar". Keep the prospect's hedges ("creo que", "puede que",
   "más adelante"): a maybe is not a yes, and "no tenemos ese problema" is not "no le interesa".
   Never leave out what the next touch needs: an email or phone they dictated, who calls or writes to
   whom and when, a condition they set ("si bajáis el precio", "después de Black Friday"), a price
   they asked about or accepted, figures with their unit exactly as said (441 comerciales is not 441
   empleados), and what they said they will do (and who does it: "te envío la invitación" is the
   salesperson's task, not the prospect's).
   No line without a fact: never "apertura exitosa", "se presentó", "confirma que se llama X",
   "se habló de", and never repeat the Resultado below it. A short call or a plain no is the
   Resultado line plus at most two bullets. Words the audio garbled are not facts: leave them out.
6. **nextSteps**: only actions the SALESPERSON (or their team) must do, promised or agreed in this
   call: send X, prepare the proposal, send the calendar invite, call back (also when the salesperson
   said "te vuelvo a llamar" without a day), contact the person they were referred to. Never the prospect's own actions (those go in the note) and never "Reunión"
   as a task. Short task titles without dates; timing goes in nextStepSchedules, one item per task: the
   words that were said for that action, copied as said ("mañana", "el viernes", "en tres meses",
   "a partir del 15 de enero"), or YYYY-MM-DD only when a full date was said. Never compute a date and
   never use the call date. "" when no day was said for that task. [] when nothing was agreed.
6b. **Deal amounts and line items**: only a price or volume the prospect accepted or proposed; a price the
   salesperson quoted and the prospect rejected or did not answer goes in the note, never in a field.
7. **contactEmail**: only a real address spoken or spelled; never invented.
7a. **customerPresent**: true only if someone outside the salesperson's team spoke or is clearly the
   counterpart (a prospect, customer or partner); false only when everyone speaking is on the same team
   (a team meeting, an internal brief); null if unsure, and null for a note the salesperson dictates alone.
7b. **Fields agree with the note**: whatever the note states about the agreed meeting or callback day,
   the objection, the company's name, its revenue or a pain the prospect owned also goes in its
   field (nextStepSchedules, objections, the company and contact fields); a field never contradicts the note.
7c. **evidence**: for every field you fill except the note, the tasks, their schedules and the
   contact's own name, email, phone and company name, add to "evidence" the prospect's exact words
   that back it, copied from a "Them:" line: {{"field path": "exact words"}}, with the same path as
   the field ("painPoints", "company_properties.annualrevenue", "dealstage"…). A field with no
   prospect words to back it is not filled: what only the salesperson said never counts.
8. **Format**: Return JSON in this structure:

{json_structure}
Add one more top-level key: "evidence": {{"field path": "the prospect's exact words"}}.

9. **Confidence**: Provide overall (0-1) and per-field scores."""


class ExtractionService:
    """Service for extracting structured CRM data from transcripts via LLM."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        jev_client: Optional[JevClient] = None,
    ) -> None:
        self.llm = llm_client or LLMClient()
        self.jev = jev_client or JevClient()
    
    def _build_prompt(
        self,
        transcript: str,
        field_specs: Optional[list[dict]] = None,
        glossary_text: str = "",
        source_context: str = "voice_memo",
        product_context: str = "",
        existing_values: Optional[dict] = None,
        call_date: Optional[str] = None,
        call_reading: Optional[dict] = None,
        user_notes: Optional[str] = None,
    ) -> str:
        """Build the extraction prompt dynamically based on HubSpot CRM schema.
        
        Schema-driven: field descriptions from HubSpot are the primary semantic source.
        Standard meeting-intelligence fields are included only when not in schema.
        source_context: 'voice_memo' (default), 'meeting_transcript', or 'hubspot_call'.
        """
        schema_field_names = {s["name"] for s in (field_specs or []) if s.get("name")}

        # Meeting-intelligence fields: minimal, generic. Exclude any covered by schema.
        all_standard = {
            "companyName": (
                "string | null",
                "Prospect/client company (the company being sold to). Do NOT use broker, "
                "insurer (aseguradora), or intermediary names — e.g. 'el bróker es Aon' means "
                "Aon is the broker, not the prospect company. If no company is mentioned or it "
                "cannot be determined, return null — never write a placeholder like 'Unknown', "
                "'Desconocida', 'N/A', or similar.",
            ),
            "contactName": (
                "string | null",
                "Person spoken with on this call, by their actual name. If not mentioned, return null — "
                "never write a placeholder like 'Unknown' or 'Desconocido'. This is meeting intelligence, "
                "not a CRM identity overwrite: if CURRENT VALUE firstname is a different person, still "
                "record who spoke here, but leave contact_properties.firstname null.",
            ),
            "contactEmail": (
                "string | null",
                "Email only if the prospect actually said or spelled a real address. "
                "Phone and/or name are enough to create a CRM contact — never invent, guess, "
                "or fabricate an email, and never use placeholder domains "
                "(lead.vocify, lead.getvocify, example.com). If not mentioned, return null.",
            ),
            "contactPhone": ("string | null", "Phone if mentioned. Enough on its own to create a contact."),
            "summary": (
                "string",
                "Structured call note in the transcript language. Markdown only: "
                "2–4 headings the call actually earned (`# Contexto`, `# Perfil`, `# Decisión`, …) — "
                "do not use a fixed template; omit a heading with nothing in it. "
                "Under each heading: 1–4 bullets (`- `). One nested level (`  - `) allowed. "
                "Bold proper names (`**Aritzel Expuru**`). "
                "Prefer CURRENT CRM VALUES / glossary when a spoken name is a phonetic near-match. "
                "Do NOT include a Próximos pasos / Next steps heading — that is nextSteps. "
                "Do NOT recap the pitch or product. Do NOT write 3–5 sentences of prose. "
                "Ground ONLY in the transcript — never invent.",
            ),
            "painPoints": ("string[]", "Pain points discussed."),
            "nextSteps": (
                "string[]",
                "Follow-up tasks whenever the call created a real next action: a commitment, "
                "a redirect to another person, sending materials, or a scheduled callback. "
                "Fill this when there is an opportunity to follow up — not only when someone "
                "said 'I promise'. Use concise HubSpot task titles (3-8 words): verb + what to do. "
                "NO dates, times, weekdays, or scheduling ('martes', '18:00', 'mañana'). "
                "Good: 'Llamada de seguimiento', 'Contactar a Aritzel Expuru', 'Enviar propuesta comercial'. "
                "Bad: 'Hablar el martes a las 18:00'. Empty array only if nothing actionable came out of the call.",
            ),
            "nextStepSchedules": (
                "string[]",
                "Parallel to nextSteps: when each action happens. Prefer ISO YYYY-MM-DD when the day "
                "can be resolved from the transcript (mañana, next Tuesday, el 20 de agosto). "
                "Otherwise the spoken phrase (e.g. 'martes 18:00'). Empty string if no timing mentioned.",
            ),
            "competitors": ("string[]", "Competing vendors/products being evaluated."),
            "objections": ("string[]", "Objections raised."),
            "decisionMakers": ("string[]", "Decision makers involved."),
            "customerPresent": ("boolean | null", "Whether anyone outside the rep's team took part."),
        }
        standard_fields = {k: v for k, v in all_standard.items() if k not in schema_field_names}

        # Group schema fields by CRM object so the LLM writes the right bags
        specs_by_object: dict[str, list[dict]] = {}
        for spec in field_specs or []:
            obj = spec.get("object_type") or "deals"
            specs_by_object.setdefault(obj, []).append(spec)

        object_labels = {
            "deals": "DEAL",
            "contacts": "CONTACT",
            "companies": "COMPANY",
            "line_items": "LINE ITEM",
        }

        def _describe_spec(spec: dict) -> tuple[str, str]:
            field_name = spec["name"]
            label = spec["label"]
            field_type = spec.get("type", "string")
            desc = (spec.get("description") or "").strip()
            options = spec.get("options", [])
            parts = []
            if desc:
                parts.append(f'"{field_name}" ({label}): {desc}')
            else:
                parts.append(f'"{field_name}" ({label})')
            if options:
                values = []
                labels = []
                for o in options:
                    if isinstance(o, dict):
                        values.append(o.get("value", o.get("label", "")))
                        labels.append(o.get("label", o.get("value", "")))
                    elif isinstance(o, str):
                        values.append(o)
                        labels.append(o)
                if values:
                    mapping = ", ".join(f'"{l}"→"{v}"' for l, v in zip(labels, values))
                    parts.append(f"Output one of: {values}. Map: {mapping}.")
                    json_type = f'"{field_name}": "{values[0]}" | null  // one of {values}'
                else:
                    parts.append(f"Type: {field_type}.")
                    json_type = f'"{field_name}": string | null'
            elif field_type == "number":
                parts.append("Type: number. Output numeric value only. NO currency symbols or units.")
                json_type = f'"{field_name}": number | null'
            elif field_type in ("datetime", "date"):
                parts.append("Type: date. Output ISO YYYY-MM-DD only.")
                json_type = f'"{field_name}": "YYYY-MM-DD" | null'
            elif field_type == "bool":
                parts.append("Type: boolean. Output true or false only.")
                json_type = f'"{field_name}": boolean | null'
            else:
                parts.append(f"Type: {field_type}.")
                json_type = f'"{field_name}": string | null'
            policy = classify_fill_policy(spec)
            parts.append(fill_policy_instruction(policy))
            lead_rules = lead_status_field_instruction(spec)
            if lead_rules:
                parts.append(lead_rules)
            obj = spec.get("object_type") or "deals"
            current = ((existing_values or {}).get(obj) or {}).get(field_name)
            if current is not None and str(current).strip():
                parts.append(f"CURRENT VALUE: {current}.")
            return " ".join(parts), json_type

        schema_description: list[str] = []
        json_structure_parts: list[str] = []

        if specs_by_object.get("deals"):
            schema_description.append("### DEAL FIELDS (top-level JSON keys – HubSpot deal properties)")
            for spec in specs_by_object["deals"]:
                line, jt = _describe_spec(spec)
                schema_description.append(f"- {line}")
                json_structure_parts.append(f"  {jt},")

        if specs_by_object.get("contacts"):
            schema_description.append(
                "### CONTACT FIELDS (nested under contact_properties — fill when the call answers them)"
            )
            contact_inner = []
            for spec in specs_by_object["contacts"]:
                line, jt = _describe_spec(spec)
                schema_description.append(f"- {line}")
                contact_inner.append(f"    {jt}")
            json_structure_parts.append(
                '  "contact_properties": {\n' + ",\n".join(contact_inner) + "\n  } | null,"
            )

        if specs_by_object.get("companies"):
            schema_description.append(
                "### COMPANY FIELDS (nested under company_properties — fill when the call answers them)"
            )
            company_inner = []
            for spec in specs_by_object["companies"]:
                line, jt = _describe_spec(spec)
                schema_description.append(f"- {line}")
                company_inner.append(f"    {jt}")
            json_structure_parts.append(
                '  "company_properties": {\n' + ",\n".join(company_inner) + "\n  } | null,"
            )

        if specs_by_object.get("line_items"):
            schema_description.append(
                "### LINE ITEMS (array under line_items – only products/services explicitly sold; prefer [] if unsure)"
            )
            li_inner = []
            for spec in specs_by_object["line_items"]:
                line, jt = _describe_spec(spec)
                schema_description.append(f"- {line}")
                li_inner.append(f"    {jt}")
            json_structure_parts.append(
                '  "line_items": [\n    {\n' + ",\n".join(li_inner) + "\n    }\n  ],"
            )

        # Build the expected JSON structure with schema-aligned types
        json_structure = "{\n"
        for part in json_structure_parts:
            json_structure += f"{part}\n"
        for field, (type_str, _) in standard_fields.items():
            json_structure += f'  "{field}": {type_str},\n'
        json_structure += '  "confidence": { "overall": number (0-1), "fields": { "fieldName": number (0-1) } }\n'
        json_structure += "}"

        schema_text = "\n".join(schema_description) if schema_description else ""
        del object_labels  # kept for readability of grouping above

        # Source-specific context hints to guide the LLM
        source_hint = ""
        if call_reading:
            source_hint = _grounded_source_hint(call_reading)
        elif source_context == "meeting_transcript":
            source_hint = """
### SOURCE CONTEXT
This transcript is from a meeting recording (e.g. Zoom, Google Meet, Fireflies, Otter).
It may include speaker labels ("John:", "Sarah:"), timestamps, or action-item formatting.
Extract semantic content as usual—ignore formatting artifacts. Use speaker labels to disambiguate if helpful.
A speaker labelled "You" is the sales rep (the Vocify user); other names are the customer side. Attribute what was said to who said it.
**summary**: structured markdown (headings + bullets). Do NOT recap the pitch. Do NOT include next steps in the note. **nextSteps**: fill when the call created a real follow-up; prefer [] only if nothing actionable. Never invent.
"""
        elif source_context == "hubspot_call":
            source_hint = """
### SOURCE CONTEXT — OUTBOUND/INBOUND SALES CALL
This transcript is from a short phone or VoIP call logged in HubSpot CRM.
It was transcribed by Speechmatics with speaker diarization enabled.

Speaker labels:
- **You** = the sales rep (the Vocify user who owns this account). Lines Vocify already named keep this label.
- Any other name (e.g. "Pablo:") = the prospect or customer side.
- Unnamed labels: **S1** = typically the sales rep, **S2** = typically the prospect or customer.
- If more than 2 speakers appear, treat You/S1 as the rep and all others as the customer side.
- Attribute what was said to who said it: never write that the customer did something the rep said (a delay, an emergency, a request to pause).

Key characteristics:
- Typically 2–15 minutes. Many calls are brief check-ins with little extractable data.
- Automated transcription — expect phonetic errors, filler words, and cut-off sentences.
- Apply glossary corrections where applicable. Treat transcription artifacts as noise.

Extraction discipline:
- **Numbers / money / dates**: only if stated. Do not invent a headcount, amount, or close date.
- **Enabled CRM fields**: fill every enabled field the prospect answered. For enumerations, pick the closest allowed option from what they described — they will not say the internal value. Null only when that topic never came up. Examples: one distributor / channel partners / they do not employ the store reps → partner_channel (even if the distributor's people visit stores — that is still partner_channel, not field_sales); they set commercial policy but send contracts or tool-buying to someone else → influencer / influencer_with_path (whichever the field allows); spelled company domain → domain. Do not guess a named CRM vendor from "nuestro programa".
- **No hallucination**: never invent company names, deal sizes, or dates. Mapping a described motion onto an enum is required, not optional. ICP cutoffs in HubSpot descriptions are not a reason to leave the field empty.
- **Transcript + CURRENT CRM VALUES**: do not invent from other calls. If CURRENT VALUE is set, prefer `null` over an inferred replacement.
- **Short calls**: unused fields stay null. Do not leave answered discovery questions empty.
- **Summary**: structured markdown call note (2–4 earned headings + bullets). Do NOT recap the pitch. Do NOT include Próximos pasos — that is nextSteps. Still no invention.
- **Their company vs our motion**: sales-motion / fit / ICP fields describe the PROSPECT's world, never how we ran this outreach.
- **Next steps → HubSpot tasks**: fill whenever the call created a real follow-up opportunity
  (send X, schedule call, share doc, contact another person, callback). Titles contain only what to do; put any owner, date,
  time, or deadline in the parallel `nextStepSchedules` item (ISO YYYY-MM-DD when the day is resolvable). Reject vague fluff: "seguir en contacto", "mantener el follow-up", "hablar pronto",
  "cerrar el trato", "quedamos pendientes". Empty array only if nothing actionable came out of the call.
- **Sentiment/outcome**: base these on what was actually said, not on tone assumptions.
"""
        
        # STRUCTURED GLOSSARY Logic with Phonetic Physics
        glossary_section = ""
        if glossary_text:
            glossary_section = f"""
### GROUND TRUTH GLOSSARY (User-Specific Terms)
{glossary_text}

### DYNAMIC PHONETIC CORRECTION RULES:
You must perform "Sound-Alike Matching" for every word in the Glossary above. 
The transcript often contains "Phonetic Collisions" where English business terms are misheard as Spanish words.

Apply these Collision Patterns to the Glossary items:
1. **Acronym Collision**: Acronyms (like FTES, CRM, ROI) are often heard as Spanish-sounding fragments (FT is, Se erre eme, Erre oi) or similar-sounding acronyms (FPS, FTS).
2. **Vowel Flattening**: English "ee" or "ea" sounds (Deal, fee) are often transcribed as Spanish "i" (Dil, fi).
3. **Consonant Softening**: Terminal "k", "t", or "d" sounds (50k, Target) are often dropped or replaced by "s", "sh", or "ch" (50 cash, Targe).
4. **Entity Priority**: If a transcript phrase sounds like a word in the Glossary, ALWAYS prioritize the Glossary term.
"""

        product_text = (product_context or "").strip() or "(none provided)"
        product_section = f"""
### PRODUCT / OFFER CONTEXT (reference only)
Use this to understand the call and to correct product-name transcription errors.
Do NOT copy this into summary, description, or other CRM fields. Do NOT recap the pitch.
{product_text}
"""
        existing_block = format_existing_values_block(existing_values)
        speaker_block = "" if call_reading else speaker_prompt_legend(
            transcript,
            prospect_name_from_existing(existing_values),
        )
        from app.services.relative_dates import call_date_header, parse_iso_date

        date_block = call_date_header(parse_iso_date(call_date) if call_date else None)
        notes_block = user_notes_block(user_notes)

        if call_reading:
            rules_block = _grounded_rules(json_structure)
        else:
            rules_block = f"""### EXTRACTION RULES:
1. **Do not invent**: names, emails, amounts, headcount, and dates must be spoken (or spelled). Do not use prior CRM knowledge or other calls.
2. **Strict types**: Output MUST match schema exactly. `number` → numeric only (e.g. 500, not "500€"). `enumeration` → exact value from allowed list. `date` → YYYY-MM-DD only.
3. **Language**: All text fields MUST use the SAME language as the transcript. Never translate.
4. **summary**: Structured markdown — 2–4 headings the call earned, bullets under each. Same language as the transcript. Do NOT recap the pitch. Do NOT include Próximos pasos / Next steps (that is nextSteps). Not a paragraph.
5. **nextSteps**: Fill whenever the call created a real follow-up (commitment, redirect, send materials, callback). Task-ready titles without dates; timing goes in nextStepSchedules.
   Prefer empty array over vague items. Do NOT invent follow-ups the speakers did not agree to.
5b. **CRM fields**: Honor each field's fill policy. Pre-call / talk-track fields → null. Identity fields with a CURRENT VALUE → null if the spoken person is different. Account fit/motion fields describe the prospect, not our outreach. When CURRENT VALUE is empty and the call answered the field, you MUST set it — including mapping a description onto the closest enumeration option. ICP thresholds in a field description (e.g. "3+ reps") are scoring hints only — still store the real answer.
5c. **contactEmail**: Only if a real address was spoken or spelled. Phone and/or name are enough to create a CRM contact. Never invent, guess, or fabricate an email (no lead.vocify / example.com placeholders). If not mentioned, null.
5d. **Enumerations**: prefer the best-matching option over null. Use an `unknown` option only if they said they do not know. If the topic never came up, null.
5e. **customerPresent**: true only if someone outside the rep's team spoke or is clearly the counterpart (a prospect, customer or partner). false only when everyone speaking is on the same team (a team meeting, an internal brief). null if unsure, and null for a note the rep dictates alone.
6. **Format**: Return JSON in this structure:

{json_structure}

7. **Confidence**: Provide overall (0-1) and per-field scores.
"""
        return f"""You are a world-class CRM analyst. Your task is to extract structured data from a sales call transcript.
{source_hint}
{date_block}
{speaker_block}
{product_section}
{existing_block}
{glossary_section}
{notes_block}
TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

{schema_text}

{rules_block}

Return ONLY valid JSON. No preamble, no conversational text."""

    async def extract(
        self,
        transcript: str,
        field_specs: Optional[list[dict]] = None,
        glossary_text: str = "",
        source_context: str = "voice_memo",
        product_context: str = "",
        existing_values: Optional[dict] = None,
        call_date: Optional[str] = None,
        call_reading: Optional[dict] = None,
        user_notes: Optional[str] = None,
    ) -> MemoExtraction:
        """
        Extract structured CRM data from transcript.

        Args:
            transcript: The transcript text
            field_specs: Optional list of curated field specifications
            glossary_text: Optional text describing custom vocabulary for correction
            source_context: 'voice_memo' (default), 'meeting_transcript', or 'hubspot_call'
            product_context: Seller offer/ICP text — reference only, never copied into CRM notes
            existing_values: Current CRM snapshot {contacts|companies|deals: {field: value}}

        Returns:
            MemoExtraction with extracted data and confidence scores
        """
        if call_reading:
            # How the call ended (lead status, meeting booked) is the rep's to declare after the
            # call, never read into the transcript.
            field_specs = [
                spec for spec in (field_specs or [])
                if not is_lead_status_field(spec) and spec.get("name") not in REP_DECLARED_FIELDS
            ]
        prompt = self._build_prompt(
            transcript,
            field_specs,
            glossary_text,
            source_context=source_context,
            product_context=product_context,
            existing_values=existing_values,
            call_date=call_date,
            call_reading=call_reading,
            user_notes=user_notes,
        )
        schema_field_names = [s["name"] for s in (field_specs or []) if isinstance(s.get("name"), str)]
        logger.info(
            "📝 Extraction started",
            extra=log_domain(
                DOMAIN_EXTRACTION,
                "extract_started",
                transcript_len=len(transcript or ""),
                prompt_len=len(prompt),
                has_schema=bool(field_specs),
                has_glossary=bool(glossary_text and glossary_text.strip()),
                has_product_context=bool((product_context or "").strip()),
                schema_field_names=schema_field_names,
            ),
        )
        if not transcript or len(transcript.strip()) < 10:
            logger.info(
                "⚠️ Extraction skipped (transcript too short)",
                extra=log_domain(DOMAIN_EXTRACTION, "extract_skipped", transcript_len=len(transcript or "")),
            )
            return MemoExtraction(
                summary="Transcript too short to extract meaningful data.",
                confidence={"overall": 0.0, "fields": {}}
            )
        
        if (
            call_reading
            and call_reading.get("call_type") in NO_CRM_CALL_TYPES
            and len(" ".join(str(transcript or "").split())) < NO_CRM_MAX_CHARS
        ):
            reason = str(call_reading.get("call_type_reason") or "").strip()
            label = "Sin conversación" if call_reading.get("call_type") == "no_conversation" else "No es una llamada de venta"
            return MemoExtraction(
                summary=f"**Resultado:** {label}." + (f" {reason}" if reason else ""),
                confidence={"overall": 1.0, "fields": {}},
            )
        messages = [
            {"role": "system", "content": grounded_system_prompt() if call_reading else EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            from app.config import settings
            from app.services.pipeline_meta import record_stage, snapshot_prompts

            t0 = time.perf_counter()
            use_jev = (
                not call_reading  # grounded: one pass, no second guess filling enums
                and getattr(settings, "USE_JEV_CLASSIFIER", True)
                and getattr(self, "jev", None) is not None
                and self.jev.is_available
            )
            candidate_enums = [
                s
                for s in (field_specs or [])
                if s.get("type") in ("enumeration", "checkbox", "radio", "select")
                and s.get("name")
                and classify_fill_policy(s) not in {"strategy", "identity"}
            ]

            jev_applied = False
            abstained: list[str] = []
            if use_jev and candidate_enums:
                gemini_coro = self.llm.chat_json(messages, temperature=0.0)
                jev_coro = self.jev.classify_enums(transcript, candidate_enums)
                res_gemini, res_jev = await asyncio.gather(
                    gemini_coro, jev_coro, return_exceptions=True
                )
                if isinstance(res_gemini, Exception):
                    raise res_gemini
                extracted = res_gemini
                if isinstance(res_jev, dict) and res_jev:
                    abstained = [
                        str(name)
                        for name in (res_jev.get("_abstained") or [])
                        if name
                    ]
                    extracted = apply_enumeration_patch(
                        extracted, res_jev, candidate_enums
                    )
                    jev_applied = True
                    logger.info(
                        "Jev enumeration classification applied",
                        extra=log_domain(
                            DOMAIN_EXTRACTION,
                            "jev_enum_applied",
                            fields=list(res_jev.keys()),
                        ),
                    )
                jev_patch = res_jev if isinstance(res_jev, dict) else None
                for name in generative_lead_status_to_drop(field_specs, jev_patch):
                    if name not in abstained:
                        abstained.append(name)
            elif call_reading:
                # One retry on an unparseable or empty reply: a real call must not be left without
                # its note (a model sometimes returns {} on a long call).
                effort = settings.EXTRACTION_REASONING_EFFORT
                try:
                    extracted = await self.llm.chat_json(messages, temperature=0.0, reasoning_effort=effort)
                except ValueError:
                    extracted = None
                if not isinstance(extracted, dict) or not str(extracted.get("summary") or "").strip():
                    extracted = await self.llm.chat_json(messages, temperature=0.0, reasoning_effort=effort)
            else:
                extracted = await self.llm.chat_json(messages, temperature=0.0)
            # Post-process: coerce to schema types (number, enum value, etc.)
            extracted = _normalize_raw_extraction(extracted, field_specs)
            extracted = apply_fill_policies(extracted, field_specs, existing_values)
            extracted = drop_abstained_fields(extracted, abstained, field_specs)
            extracted = drop_unspoken_numbers(extracted, transcript, field_specs)
            if call_reading:
                extracted = grounded_cleanup(require_prospect_evidence(
                    extracted, transcript, roles_marked=call_reading.get("roles_marked", True),
                ))
            abstained_names = set(abstained)
            pending_enums = [
                spec
                for spec in pending_enumeration_specs(
                    extracted, field_specs, existing_values
                )
                if spec.get("name") not in abstained_names
            ]
            if pending_enums and not call_reading:
                try:
                    enum_payload = await self.llm.chat_json(
                        [
                            {
                                "role": "system",
                                "content": (
                                    "You fill leftover CRM enumerations from a sales transcript. "
                                    "JSON only. Closest allowed option, or null."
                                ),
                            },
                            {
                                "role": "user",
                                "content": _enumeration_followup_prompt(transcript, pending_enums),
                            },
                        ],
                        temperature=0.0,
                    )
                    extracted = apply_enumeration_patch(
                        extracted, enum_payload or {}, pending_enums
                    )
                    logger.info(
                        "Enumeration follow-up applied",
                        extra=log_domain(
                            DOMAIN_EXTRACTION,
                            "enum_followup",
                            pending=[s.get("name") for s in pending_enums],
                            payload_keys=list((enum_payload or {}).keys())[:30],
                        ),
                    )
                    extracted = _normalize_raw_extraction(extracted, field_specs)
                    extracted = apply_fill_policies(
                        extracted, field_specs, existing_values
                    )
                except Exception:
                    logger.warning(
                        "Enumeration follow-up skipped",
                        extra=log_domain(DOMAIN_EXTRACTION, "enum_followup_skipped"),
                    )

            # Post-process: clear closeDate if transcript only has relative dates (no explicit calendar date)
            transcript_lower = transcript.lower()
            relative_phrases = [
                "martes que viene", "próxima semana", "next week", "next tuesday",
                "semana que viene", "la semana que viene", "próximo martes",
                "mes que viene", "next month", "mañana", "tomorrow"
            ]
            has_relative = any(p in transcript_lower for p in relative_phrases)
            # Explicit date patterns: "15 de marzo", "march 15", "2025-", "15/03", "15-03"
            has_explicit_date = bool(re.search(
                r"\d{1,2}\s+de\s+\w+|"
                r"\w+\s+\d{1,2}|\d{4}-\d{2}|\d{1,2}/\d{1,2}|\d{1,2}-\d{1,2}",
                transcript,
                re.I
            ))
            if extracted.get("closedate") and has_relative and not has_explicit_date:
                extracted["closedate"] = None
            from app.services.relative_dates import parse_iso_date, resolve_schedules

            extracted["nextStepSchedules"] = resolve_schedules(
                extracted.get("nextStepSchedules") or [],
                parse_iso_date(call_date) if call_date else None,
            )
            
            # companyName: explicit only; fallback from dealname only when it looks like "X Deal"
            company = _clean_extracted_name(extracted.get("companyName"))
            if not company and extracted.get("dealname"):
                dn = str(extracted.get("dealname", ""))
                if dn.rstrip().lower().endswith(" deal"):
                    company = _clean_extracted_name(dn.rsplit(" ", 1)[0].strip())
            # contactName, contactEmail, contactPhone: explicit extraction.
            # Never keep invented placeholder emails — HubSpot/Salesforce do not require email.
            from app.services.hubspot.contact_identity import (
                real_contact_email_or_none,
                strip_invented_emails,
            )

            extracted = strip_invented_emails(extracted)
            contact = _clean_extracted_name(extracted.get("contactName"))
            contact_email = real_contact_email_or_none(extracted.get("contactEmail"))
            contact_phone = extracted.get("contactPhone") or None
            # amount: ensure numeric (schema type number)
            deal_amount = extracted.get("amount")
            if deal_amount is not None and not isinstance(deal_amount, (int, float)):
                deal_amount = _parse_amount(deal_amount)
            # Not a CRM field: kept out of raw_extraction so no provider writes it.
            customer_present = extracted.pop("customerPresent", None)
            result = MemoExtraction(
                companyName=company or None,
                contactName=contact or None,
                contactEmail=contact_email,
                contactPhone=contact_phone,
                dealAmount=deal_amount,
                dealCurrency=extracted.get("deal_currency_code", "EUR"),
                dealStage=extracted.get("dealstage"),
                closeDate=extracted.get("closedate"),
                summary=extracted.get("summary", ""),
                painPoints=extracted.get("painPoints", []),
                nextSteps=extracted.get("nextSteps", []),
                competitors=extracted.get("competitors", []),
                objections=extracted.get("objections", []),
                decisionMakers=extracted.get("decisionMakers", []),
                confidence=extracted.get("confidence", {"overall": 0.5, "fields": {}}),
                raw_extraction=extracted,
                customerPresent=customer_present if isinstance(customer_present, bool) else None,
            )
            conf = result.confidence or {}
            conf_overall = conf.get("overall") if isinstance(conf, dict) else None
            extracted_field_names = [k for k in (extracted.keys() or []) if k != "confidence"]
            # Build human-readable extracted fields for logging (truncate long values)
            extracted_fields_log: dict[str, object] = {}
            for k in extracted_field_names:
                v = extracted.get(k)
                if v is None:
                    extracted_fields_log[k] = None
                elif isinstance(v, list):
                    extracted_fields_log[k] = v[:5] if len(v) <= 5 else v[:5] + [f"...+{len(v) - 5} more"]
                elif isinstance(v, str) and len(v) > 100:
                    extracted_fields_log[k] = v[:100] + "..."
                else:
                    extracted_fields_log[k] = v
            record_extraction_duration(time.perf_counter() - t0)
            call_meta = getattr(self.llm, "last_call_meta", None) or {}
            record_stage(
                "extract",
                t0,
                provider=getattr(settings, "LLM_PROVIDER", None) or "openrouter",
                model=call_meta.get("model") or getattr(settings, "EXTRACTION_MODEL", None),
                prompt_tokens=call_meta.get("prompt_tokens"),
                completion_tokens=call_meta.get("completion_tokens"),
                total_tokens=call_meta.get("total_tokens"),
                jev_applied=jev_applied,
                prompts=snapshot_prompts(messages),
                includes=["summary", "crm_fields", "next_steps"],
                note="One JSON call: CRM note (summary), fields to update, and next steps.",
            )
            logger.info(
                "✅ Extraction complete",
                extra=log_domain(
                    DOMAIN_EXTRACTION,
                    "extract_complete",
                    company_name=company,
                    contact_name=contact,
                    confidence_overall=conf_overall,
                    next_steps_count=len(result.nextSteps or []),
                    extracted_field_names=extracted_field_names,
                    extracted_fields=extracted_fields_log,
                ),
            )
            return result
        except Exception as e:
            inc_pipeline_error(DOMAIN_EXTRACTION, "extract")
            try:
                from app.config import settings
                from app.services.pipeline_meta import record_stage, snapshot_prompts

                call_meta = getattr(self.llm, "last_call_meta", None) or {}
                record_stage(
                    "extract",
                    t0,
                    provider=getattr(settings, "LLM_PROVIDER", None) or "openrouter",
                    model=call_meta.get("model") or getattr(settings, "EXTRACTION_MODEL", None),
                    prompt_tokens=call_meta.get("prompt_tokens"),
                    completion_tokens=call_meta.get("completion_tokens"),
                    prompts=snapshot_prompts(messages),
                    error=str(e)[:500],
                )
            except Exception:
                pass
            logger.exception(
                "❌ Extraction failed",
                extra=log_domain(DOMAIN_EXTRACTION, "extract_failed", error=str(e), transcript_len=len(transcript or "")),
            )
            raise Exception(f"Extraction failed: {str(e)}") from e


