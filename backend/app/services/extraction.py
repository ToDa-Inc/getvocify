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
from typing import Optional


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
    spec_map = {s["name"]: s for s in (field_specs or [])}
    
    for key, value in list(out.items()):
        if value is None:
            continue
        spec = spec_map.get(key)
        if not spec:
            continue
        field_type = spec.get("type", "string")
        options = spec.get("options", [])
        
        if field_type == "number":
            parsed = _parse_amount(value)
            if parsed is not None:
                out[key] = parsed
        elif options and isinstance(value, str):
            # Enum: ensure we have a valid value (deals.py will normalize label→value)
            values = [
                o.get("value", o.get("label", "")) if isinstance(o, dict) else o
                for o in options
            ]
            if value not in values:
                # Try case-insensitive match
                v_lower = value.strip().lower()
                for v in values:
                    if str(v).lower() == v_lower:
                        out[key] = v
                        break
    
    return out


class ExtractionService:
    """Service for extracting structured CRM data from transcripts via LLM."""

    def __init__(self) -> None:
        self.llm = LLMClient()
    
    def _build_prompt(self, transcript: str, field_specs: Optional[list[dict]] = None, glossary_text: str = "") -> str:
        """Build the extraction prompt dynamically based on HubSpot CRM schema.
        
        Schema-driven: field descriptions from HubSpot are the primary semantic source.
        Standard meeting-intelligence fields are included only when not in schema.
        """
        schema_field_names = {s["name"] for s in (field_specs or []) if s.get("name")}

        # Meeting-intelligence fields: minimal, generic. Exclude any covered by schema.
        all_standard = {
            "companyName": ("string", "Prospect/client company."),
            "contactName": ("string", "Person spoken with."),
            "contactEmail": ("string | null", "Email if mentioned."),
            "contactPhone": ("string | null", "Phone if mentioned."),
            "summary": ("string", "2-3 sentence meeting summary."),
            "painPoints": ("string[]", "Pain points discussed."),
            "nextSteps": ("string[]", "Agreed next steps."),
            "competitors": ("string[]", "Competing vendors/products being evaluated."),
            "objections": ("string[]", "Objections raised."),
            "decisionMakers": ("string[]", "Decision makers involved."),
        }
        standard_fields = {k: v for k, v in all_standard.items() if k not in schema_field_names}

        # Build schema-driven instructions: description-first, then type/format
        schema_description = []
        json_field_types = []

        if field_specs:
            schema_description.append("### CRM FIELDS (from HubSpot schema – output MUST match exactly)")
            for spec in field_specs:
                field_name = spec["name"]
                label = spec["label"]
                field_type = spec.get("type", "string")
                desc = (spec.get("description") or "").strip()
                options = spec.get("options", [])

                # Description-first: HubSpot description is the primary semantic guide
                parts = []
                if desc:
                    parts.append(f'"{field_name}" ({label}): {desc}')
                else:
                    parts.append(f'"{field_name}" ({label})')

                # Type/format constraints
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

                schema_description.append("- " + " ".join(parts))
                json_field_types.append(json_type)
        
        # Build the expected JSON structure with schema-aligned types
        json_structure = "{\n"
        for jt in json_field_types:
            json_structure += f"  {jt},\n"
        for field, (type_str, _) in standard_fields.items():
            json_structure += f'  "{field}": {type_str},\n'
        json_structure += '  "confidence": { "overall": number (0-1), "fields": { "fieldName": number (0-1) } }\n'
        json_structure += "}"

        schema_text = "\n".join(schema_description) if schema_description else ""
        
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
2. **Vowel Flattening**: English "ee" or "ea" sounds (Cobee, Deal) are often transcribed as Spanish "i" (Cobi, Dil).
3. **Consonant Softening**: Terminal "k", "t", or "d" sounds (50k, Target, Edenred) are often dropped or replaced by "s", "sh", or "ch" (50 cash, Targe, En red).
4. **Entity Priority**: If a transcript phrase sounds like a word in the Glossary, ALWAYS prioritize the Glossary term.
"""

        return f"""You are a world-class CRM analyst. Your task is to extract structured data from a sales call transcript.

{glossary_section}

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

{schema_text}

### EXTRACTION RULES:
1. **Conservative**: Extract only what is explicitly mentioned. If missing or ambiguous, set to `null`. Do not invent data.
2. **Strict types**: Output MUST match schema exactly. `number` → numeric only (e.g. 500, not "500€"). `enumeration` → exact value from allowed list. `date` → YYYY-MM-DD only.
3. **Language**: All text fields MUST use the SAME language as the transcript. Never translate.
4. **Format**: Return JSON in this structure:

{json_structure}

5. **Confidence**: Provide overall (0-1) and per-field scores.

Return ONLY valid JSON. No preamble, no conversational text."""

    async def extract(self, transcript: str, field_specs: Optional[list[dict]] = None, glossary_text: str = "") -> MemoExtraction:
        """
        Extract structured CRM data from transcript
        
        Args:
            transcript: The transcript text from Deepgram
            field_specs: Optional list of curated field specifications
            glossary_text: Optional text describing custom vocabulary for correction
            
        Returns:
            MemoExtraction with extracted data and confidence scores
        """
        prompt = self._build_prompt(transcript, field_specs, glossary_text)
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
            {"role": "system", "content": "You are a precise CRM data extraction engine. Output valid JSON only. Rules: (1) closedate = null unless explicit calendar date in transcript—'next Tuesday' / 'martes que viene' = null. (2) Numbers EXACT as stated: 'un euro por empleado' = 1, never 2. (3) competitors = only company names explicitly said—do not infer or guess. (4) All text in transcript language."},
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
            company = extracted.get("companyName")
            if not company and extracted.get("dealname"):
                dn = str(extracted.get("dealname", ""))
                if dn.rstrip().lower().endswith(" deal"):
                    company = dn.rsplit(" ", 1)[0].strip()
            # contactName, contactEmail, contactPhone: explicit extraction
            contact = extracted.get("contactName")
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


