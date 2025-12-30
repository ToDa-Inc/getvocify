"""
OpenRouter LLM extraction service
"""

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
    
    def _build_prompt(self, transcript: str) -> str:
        """Build the extraction prompt"""
        return f"""You are an AI assistant that extracts structured CRM data from sales call transcripts.

TRANSCRIPT:
{transcript}

Extract the following information as JSON. Set fields to null if not mentioned or unclear. Only extract what is explicitly stated.

{{
  "companyName": string | null,
  "dealAmount": number | null,
  "dealCurrency": "EUR",
  "dealStage": string | null,
  "closeDate": string | null (ISO format YYYY-MM-DD if mentioned),
  "contactName": string | null,
  "contactRole": string | null,
  "contactEmail": string | null,
  "contactPhone": string | null,
  "summary": string (2-3 sentences about the meeting),
  "painPoints": string[],
  "nextSteps": string[],
  "competitors": string[],
  "objections": string[],
  "decisionMakers": string[],
  "confidence": {{
    "overall": number (0-1, how confident you are in the extraction),
    "fields": {{ "fieldName": number (0-1) }}
  }}
}}

Rules:
- Be conservative - only extract what's explicitly stated
- If a date is mentioned but unclear, set closeDate to null
- If an amount is mentioned but currency is unclear, assume EUR
- summary should be 2-3 sentences summarizing the meeting
- confidence.overall should reflect overall extraction quality
- confidence.fields should have scores for each extracted field

Return ONLY valid JSON, no other text."""

    async def extract(self, transcript: str) -> MemoExtraction:
        """
        Extract structured CRM data from transcript
        
        Args:
            transcript: The transcript text from Deepgram
            
        Returns:
            MemoExtraction with extracted data and confidence scores
        """
        if not transcript or len(transcript.strip()) < 10:
            # Return empty extraction for very short transcripts
            return MemoExtraction(
                summary="Transcript too short to extract meaningful data.",
                confidence={"overall": 0.0, "fields": {}}
            )
        
        prompt = self._build_prompt(transcript)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
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
                                "content": "You are a CRM data extraction assistant. Always return valid JSON only."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,  # Low temperature for consistent extraction
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
                
                # Map to MemoExtraction model
                return MemoExtraction(
                    companyName=extracted.get("companyName"),
                    dealAmount=extracted.get("dealAmount"),
                    dealCurrency=extracted.get("dealCurrency", "EUR"),
                    dealStage=extracted.get("dealStage"),
                    closeDate=extracted.get("closeDate"),
                    contactName=extracted.get("contactName"),
                    contactRole=extracted.get("contactRole"),
                    contactEmail=extracted.get("contactEmail"),
                    contactPhone=extracted.get("contactPhone"),
                    summary=extracted.get("summary", ""),
                    painPoints=extracted.get("painPoints", []),
                    nextSteps=extracted.get("nextSteps", []),
                    competitors=extracted.get("competitors", []),
                    objections=extracted.get("objections", []),
                    decisionMakers=extracted.get("decisionMakers", []),
                    confidence=extracted.get("confidence", {"overall": 0.5, "fields": {}})
                )
                
        except httpx.HTTPStatusError as e:
            raise Exception(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Extraction failed: {str(e)}")


