import json
import httpx
import logging
from typing import List
from app.config import settings

logger = logging.getLogger(__name__)

class GlossaryAIService:
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.EXTRACTION_MODEL

    async def generate_phonetic_hints(self, target_word: str, category: str = "General") -> List[str]:
        """
        Uses LLM to predict common misheard variations (phonetic errors) 
        for a given word in a Sales/Business context.
        """
        prompt = f"""You are an expert in Speech-to-Text (STT) and Phonetics, specializing in Spanish-English "Spanglish" sales environments.
A salesperson is using a transcription tool. They just added "{target_word}" (Category: {category}) to their glossary.

Predict 4-6 common ways this word might be misheard or incorrectly transcribed by an AI configured for Spanish or Multi-language.

STT BEHAVIOR GUIDELINES (Phonetic Physics):
1. **Acronym Collision**: If "{target_word}" is an acronym (like FTES), Spanish STT often hears fragments (FT is, Efete ese) or similar common acronyms (FPS, FTS).
2. **Spanglish Mapping**: If "{target_word}" contains English vowels (ee, ea, ay), they collide with Spanish vowels (i, e).
3. **Consonant Drift**: If it ends in "k", "t", or "d", it's often heard as "s", "sh", or "ch" (e.g., 50k -> 50 cash).
4. **Context Drift**: How would a native Spanish speaker's accent sound to an English-centric AI?

EXAMPLES:
- "Edenred": ["En red", "Enred", "Eden red", "Edén red"]
- "FTES": ["FPS", "FTS", "FT is", "Efetes", "Efete ese", "Efectivos"]
- "50k": ["50 kas", "50 cash", "Cincuenta kas"]
- "Cobee": ["Covid", "Cobi", "Kobi", "Cobe"]

TARGET WORD: "{target_word}"
"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a phonetic error prediction engine. Output only JSON arrays."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "response_format": {"type": "json_object"} if "gpt-4" in self.model else None
                    }
                )
                
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                
                # Robust parsing
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        # Some models return {"hints": [...]} or similar
                        for key in data:
                            if isinstance(data[key], list):
                                return data[key]
                except:
                    # Fallback for plain array text
                    import re
                    match = re.search(r'\[.*\]', content, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                
                return []

        except Exception as e:
            logger.error(f"Failed to generate phonetic hints: {e}")
            return []
