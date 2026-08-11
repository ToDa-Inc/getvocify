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

logger = logging.getLogger(__name__)
from app.services.llm import LLMClient
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
            values = [
                o.get("value", o.get("label", "")) if isinstance(o, dict) else o
                for o in options
            ]
            if value not in values:
                v_lower = value.strip().lower()
                for v in values:
                    if str(v).lower() == v_lower:
                        return v
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


class ExtractionService:
    """Service for extracting structured CRM data from transcripts via LLM."""

    def __init__(self) -> None:
        self.llm = LLMClient()
    
    def _build_prompt(
        self,
        transcript: str,
        field_specs: Optional[list[dict]] = None,
        glossary_text: str = "",
        source_context: str = "voice_memo",
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
                "Person spoken with, by their actual name. If not mentioned, return null — "
                "never write a placeholder like 'Unknown' or 'Desconocido'.",
            ),
            "contactEmail": ("string | null", "Email if mentioned."),
            "contactPhone": ("string | null", "Phone if mentioned."),
            "summary": (
                "string",
                "Call/meeting summary for a CRM note: 3–5 sentences covering (1) who spoke and context, "
                "(2) what was discussed / outcome, (3) any concrete numbers or decisions stated. "
                "Ground ONLY in the transcript — do not invent. Same language as the transcript.",
            ),
            "painPoints": ("string[]", "Pain points discussed."),
            "nextSteps": (
                "string[]",
                "Concrete follow-up tasks ONLY when a speaker explicitly commits. "
                "Use concise HubSpot task titles (3-8 words): verb + what to do. "
                "NO dates, times, weekdays, or scheduling ('martes', '18:00', 'mañana'). "
                "Good: 'Llamada de seguimiento', 'Enviar propuesta comercial'. "
                "Bad: 'Hablar el martes a las 18:00'. Empty array if none were committed.",
            ),
            "nextStepSchedules": (
                "string[]",
                "Parallel to nextSteps: when each action happens as stated in the transcript "
                "(e.g. 'martes 18:00', 'próxima semana'). Empty string if no timing mentioned.",
            ),
            "competitors": ("string[]", "Competing vendors/products being evaluated."),
            "objections": ("string[]", "Objections raised."),
            "decisionMakers": ("string[]", "Decision makers involved."),
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
                "### CONTACT FIELDS (nested under contact_properties – only if explicitly stated)"
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
                "### COMPANY FIELDS (nested under company_properties – only if explicitly stated)"
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
        if source_context == "meeting_transcript":
            source_hint = """
### SOURCE CONTEXT
This transcript is from a meeting recording (e.g. Zoom, Google Meet, Fireflies, Otter).
It may include speaker labels ("John:", "Sarah:"), timestamps, or action-item formatting.
Extract semantic content as usual—ignore formatting artifacts. Use speaker labels to disambiguate if helpful.
**summary**: CRM-ready note (who, outcome, key facts stated). **nextSteps**: only explicit commitments → task-ready strings; prefer [] over vague fluff. Never invent.
"""
        elif source_context == "hubspot_call":
            source_hint = """
### SOURCE CONTEXT — OUTBOUND/INBOUND SALES CALL
This transcript is from a short phone or VoIP call logged in HubSpot CRM.
It was transcribed by Speechmatics with speaker diarization enabled.

Speaker labels:
- **S1** = typically the sales rep (the Vocify user who owns this account).
- **S2** = typically the prospect or customer.
- If more than 2 speakers appear, treat S1 as the rep and all others as the customer side.

Key characteristics:
- Typically 2–15 minutes. Many calls are brief check-ins with little extractable data.
- Automated transcription — expect phonetic errors, filler words, and cut-off sentences.
- Apply glossary corrections where applicable. Treat transcription artifacts as noise.

Extraction discipline:
- **Conservative**: extract only what is explicitly stated. Implied or inferred values → `null`.
- **No hallucination**: never infer company names, deal sizes, or dates from context alone.
- **This transcript only**: ignore any CRM deal fields, prior notes, or other calls — extract solely from the text below.
- **Short/inconclusive calls**: most fields will be `null` — that is correct and expected.
- **Summary**: write a CRM-ready note summary (outcome + key points stated). Still no invention.
- **Next steps → HubSpot tasks**: each item must be a concrete, assignable action someone committed to
  (send X, schedule call, share doc, confirm Y). Titles contain only what to do; put any owner, date,
  time, or deadline in the parallel `nextStepSchedules` item. Reject vague fluff: "seguir en contacto", "mantener el follow-up", "hablar pronto",
  "cerrar el trato", "quedamos pendientes". If nothing concrete was agreed → `nextSteps: []`.
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

        return f"""You are a world-class CRM analyst. Your task is to extract structured data from a sales call transcript.
{source_hint}
{glossary_section}

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

{schema_text}

### EXTRACTION RULES:
1. **Conservative**: Extract only what is explicitly mentioned **in this transcript**. If missing or ambiguous, set to `null`. Do not invent data. Do not use prior CRM knowledge or other calls.
2. **Strict types**: Output MUST match schema exactly. `number` → numeric only (e.g. 500, not "500€"). `enumeration` → exact value from allowed list. `date` → YYYY-MM-DD only.
3. **Language**: All text fields MUST use the SAME language as the transcript. Never translate.
4. **summary**: CRM note quality — who + context, discussion/outcome, concrete facts stated. 3–5 sentences. No filler.
5. **nextSteps**: Only explicit commitments → task-ready strings ("[Who] [verb] [object] [when if said]").
   Prefer empty array over vague items. Do NOT invent follow-ups the speakers did not agree to.
6. **Format**: Return JSON in this structure:

{json_structure}

7. **Confidence**: Provide overall (0-1) and per-field scores.

Return ONLY valid JSON. No preamble, no conversational text."""

    async def extract(
        self,
        transcript: str,
        field_specs: Optional[list[dict]] = None,
        glossary_text: str = "",
        source_context: str = "voice_memo",
    ) -> MemoExtraction:
        """
        Extract structured CRM data from transcript.

        Args:
            transcript: The transcript text
            field_specs: Optional list of curated field specifications
            glossary_text: Optional text describing custom vocabulary for correction
            source_context: 'voice_memo' (default), 'meeting_transcript', or 'hubspot_call'

        Returns:
            MemoExtraction with extracted data and confidence scores
        """
        prompt = self._build_prompt(
            transcript, field_specs, glossary_text, source_context=source_context
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
        
        messages = [
            {"role": "system", "content": "You are a precise CRM data extraction engine. Output valid JSON only. Rules: (1) closedate = null unless explicit calendar date in transcript—'next Tuesday' / 'martes que viene' = null. (2) Numbers EXACT as stated: 'un euro por empleado' = 1, never 2. (3) competitors = only company names explicitly said—do not infer or guess. (4) All text in transcript language. (5) summary = factual CRM call note (3–5 sentences); never invent. (6) nextSteps = only explicit committed tasks; use short titles without dates/times, and put timing in parallel nextStepSchedules (empty string when absent). Prefer [] over vague fluff."},
            {"role": "user", "content": prompt},
        ]
        try:
            t0 = time.perf_counter()
            extracted = await self.llm.chat_json(messages, temperature=0.0)
            # Post-process: coerce to schema types (number, enum value, etc.)
            extracted = _normalize_raw_extraction(extracted, field_specs)

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
            
            # companyName: explicit only; fallback from dealname only when it looks like "X Deal"
            company = _clean_extracted_name(extracted.get("companyName"))
            if not company and extracted.get("dealname"):
                dn = str(extracted.get("dealname", ""))
                if dn.rstrip().lower().endswith(" deal"):
                    company = _clean_extracted_name(dn.rsplit(" ", 1)[0].strip())
            # contactName, contactEmail, contactPhone: explicit extraction
            contact = _clean_extracted_name(extracted.get("contactName"))
            contact_email = extracted.get("contactEmail") or None
            contact_phone = extracted.get("contactPhone") or None
            # amount: ensure numeric (schema type number)
            deal_amount = extracted.get("amount")
            if deal_amount is not None and not isinstance(deal_amount, (int, float)):
                deal_amount = _parse_amount(deal_amount)
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
            logger.exception(
                "❌ Extraction failed",
                extra=log_domain(DOMAIN_EXTRACTION, "extract_failed", error=str(e), transcript_len=len(transcript or "")),
            )
            raise Exception(f"Extraction failed: {str(e)}") from e


