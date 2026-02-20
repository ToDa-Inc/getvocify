"""
CRM extraction service using LLM.
"""

from __future__ import annotations

import re
from app.models.memo import MemoExtraction
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
        """Build the extraction prompt dynamically based on HubSpot CRM schema."""
        
        # Default fields that are always extracted for meeting intelligence
        # All text fields must use the SAME language as the transcript
        standard_fields = {
            "companyName": "string (company/client name)",
            "contactName": "string (ONLY the person's name you spoke with)",
            "contactEmail": "string | null (email if mentioned)",
            "contactPhone": "string | null (phone if mentioned)",
            "summary": "string (2-3 sentences, same language as transcript)",
            "painPoints": "string[] (same language as transcript)",
            "nextSteps": "string[] (same language as transcript)",
            "competitors": "string[] (same language as transcript)",
            "objections": "string[] (same language as transcript)",
            "decisionMakers": "string[] (same language as transcript)",
        }
        
        # Build schema-driven field descriptions and JSON types from CRM schema
        schema_description = []
        json_field_types = []
        
        if field_specs:
            schema_description.append("### CRM FIELDS (from HubSpot schema – output MUST match exactly)")
            for spec in field_specs:
                field_name = spec["name"]
                label = spec["label"]
                field_type = spec.get("type", "string")
                desc = spec.get("description", "")
                options = spec.get("options", [])
                
                # Per-type instructions for strict output format
                if options:
                    # Enum: LLM must output the EXACT value (HubSpot API expects value, not label)
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
                        spec_str = f'- "{field_name}" ({label}): MUST output one of these EXACT values: {values}. Map from transcript using: {mapping}. '
                        json_type = f'"{field_name}": "{values[0]}" | null  // one of {values}'
                    else:
                        spec_str = f'- "{field_name}" ({label}): Type: {field_type}. '
                        json_type = f'"{field_name}": string | null'
                elif field_type == "number":
                    spec_str = f'- "{field_name}" ({label}): Type: number. Output ONLY the numeric value. NO currency symbols (€, $, etc.), NO units. "500 euros" or "500€" → 500. '
                    json_type = f'"{field_name}": number | null'
                elif field_type in ("datetime", "date"):
                    spec_str = f'- "{field_name}" ({label}): Type: date. Output ISO format YYYY-MM-DD only. '
                    json_type = f'"{field_name}": "YYYY-MM-DD" | null'
                elif field_type == "bool":
                    spec_str = f'- "{field_name}" ({label}): Type: boolean. Output true or false only. '
                    json_type = f'"{field_name}": boolean | null'
                else:
                    spec_str = f'- "{field_name}" ({label}): Type: {field_type}. '
                    json_type = f'"{field_name}": string | null'
                
                if desc:
                    spec_str += f"Description: {desc}"
                
                schema_description.append(spec_str)
                json_field_types.append(json_type)
        
        # Build the expected JSON structure with schema-aligned types
        json_structure = "{\n"
        for jt in json_field_types:
            json_structure += f"  {jt},\n"
        for field, desc in standard_fields.items():
            json_structure += f'  "{field}": {desc},\n'
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
1. **Conservative Extraction**: Only extract data that is explicitly mentioned. If missing or ambiguous, set the field to `null`.
2. **contactName = PERSON, companyName = COMPANY (CRITICAL)**: "Andrés de Coca Stress" → contactName="Andrés", companyName="Coca Stress". Never put the company in contactName.
3. **STRICT TYPES – Do NOT invent formats**: Output MUST match HubSpot schema exactly. For `number`: output 500, never "500€" or "500 euros". For `enumeration`: output the exact value from the allowed list, not a label or synonym. For `date`: output YYYY-MM-DD only.
4. **LANGUAGE – CRITICAL**: All text fields (summary, painPoints, nextSteps, competitors, objections, decisionMakers, description, hs_next_step) MUST be written in the SAME language as the transcript. If the transcript is in Spanish, output in Spanish. If in English, output in English. Never translate to another language.
5. **Format**: Return the data in the following JSON format:

{json_structure}

6. **Summary**: Provide a concise 2-3 sentence summary of the meeting (in transcript language).
7. **Confidence**: Provide an overall confidence score (0-1) and individual scores for each extracted field.

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
        if not transcript or len(transcript.strip()) < 10:
            # Return empty extraction for very short transcripts
            return MemoExtraction(
                summary="Transcript too short to extract meaningful data.",
                confidence={"overall": 0.0, "fields": {}}
            )
        
        prompt = self._build_prompt(transcript, field_specs, glossary_text)
        messages = [
            {"role": "system", "content": "You are a precise CRM data extraction engine. You always output valid JSON following the requested schema. All text fields (summary, nextSteps, painPoints, etc.) must be in the SAME language as the transcript—never translate."},
            {"role": "user", "content": prompt},
        ]
        try:
            extracted = await self.llm.chat_json(messages, temperature=0.0)
            # Post-process: coerce to schema types (number, enum value, etc.)
            extracted = _normalize_raw_extraction(extracted, field_specs)
            
            # companyName: explicit field first, fallback to dealname if it looks like "X Deal"
            company = extracted.get("companyName")
            if not company and extracted.get("dealname"):
                dn = str(extracted.get("dealname", ""))
                if " deal" in dn.lower():
                    company = dn.replace(" Deal", "").replace(" deal", "").strip()
                else:
                    company = dn
            # contactName, contactEmail, contactPhone: explicit extraction
            contact = extracted.get("contactName")
            contact_email = extracted.get("contactEmail") or None
            contact_phone = extracted.get("contactPhone") or None
            # amount: ensure numeric (schema type number)
            deal_amount = extracted.get("amount")
            if deal_amount is not None and not isinstance(deal_amount, (int, float)):
                deal_amount = _parse_amount(deal_amount)
            return MemoExtraction(
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
        except Exception as e:
            raise Exception(f"Extraction failed: {str(e)}") from e


