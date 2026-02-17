"""
OpenRouter LLM extraction service
"""

from __future__ import annotations

import json
import httpx
from app.config import settings
from app.models.memo import MemoExtraction
from typing import Optional


class ExtractionService:
    """Service for extracting structured data using OpenRouter/LLM"""
    
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.EXTRACTION_MODEL
    
    def _build_prompt(self, transcript: str, field_specs: Optional[list[dict]] = None, glossary_text: str = "") -> str:
        """Build the extraction prompt dynamically based on field specifications"""
        
        # Default fields that are always extracted for meeting intelligence
        # companyName and contactName are CRITICAL for deal matching - always extract
        standard_fields = {
            "companyName": "string (company/client name mentioned, e.g. Cobee, Acme Corp)",
            "contactName": "string (name of person spoken to, e.g. Tony, Maria)",
            "contactEmail": "string | null (email if mentioned in transcript)",
            "contactPhone": "string | null (phone if mentioned in transcript)",
            "summary": "string (2-3 sentences about the meeting)",
            "painPoints": "string[]",
            "nextSteps": "string[]",
            "competitors": "string[]",
            "objections": "string[]",
            "decisionMakers": "string[]",
        }
        
        # Build the dynamic schema description
        schema_description = []
        
        if field_specs:
            schema_description.append("### CRM FIELDS TO EXTRACT")
            for spec in field_specs:
                field_name = spec["name"]
                label = spec["label"]
                field_type = spec["type"]
                desc = spec.get("description", "")
                options = spec.get("options", [])
                
                spec_str = f'- "{field_name}" ({label}): '
                if options:
                    spec_str += f"MUST BE one of these exact labels: [{', '.join(options)}]. "
                else:
                    spec_str += f"Type: {field_type}. "
                
                if desc:
                    spec_str += f"Description: {desc}"
                
                schema_description.append(spec_str)
        
        # Build the expected JSON structure for the LLM
        json_structure = "{\n"
        if field_specs:
            for spec in field_specs:
                json_structure += f'  "{spec["name"]}": any | null,\n'
        
        for field, desc in standard_fields.items():
            json_structure += f'  "{field}": {desc},\n'
            
        json_structure += '  "confidence": {\n'
        json_structure += '    "overall": number (0-1),\n'
        json_structure += '    "fields": { "fieldName": number (0-1) }\n'
        json_structure += '  }\n'
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
1. **Conservative Extraction**: Only extract data that is explicitly mentioned. If a piece of information is missing or ambiguous, set the field to `null`.
2. **Enum Mapping**: If a field has a list of allowed options, you MUST choose the one that best matches the transcript. Use the exact label provided.
3. **Format**: Return the data in the following JSON format:

{json_structure}

4. **Summary**: Provide a concise 2-3 sentence summary of the meeting.
5. **Confidence**: Provide an overall confidence score (0-1) and individual scores for each extracted field.

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
        
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    self.OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": settings.FRONTEND_URL,
                        "X-Title": "Vocify CRM Extraction",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a precise CRM data extraction engine. You always output valid JSON following the requested schema."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.0,  # Zero temperature for maximum precision
                        "response_format": {"type": "json_object"},  # Force JSON output
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract content from response
                content = data["choices"][0]["message"]["content"]
                
                # Parse JSON
                try:
                    extracted = json.loads(content)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    import re
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                    if json_match:
                        extracted = json.loads(json_match.group(1))
                    else:
                        raise Exception("Failed to parse JSON from LLM response")
                
                # Map back to MemoExtraction model
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
                return MemoExtraction(
                    companyName=company or None,
                    contactName=contact or None,
                    contactEmail=contact_email,
                    contactPhone=contact_phone,
                    dealAmount=extracted.get("amount"),
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
                    raw_extraction=extracted
                )
                
        except httpx.HTTPStatusError as e:
            raise Exception(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Extraction failed: {str(e)}")


