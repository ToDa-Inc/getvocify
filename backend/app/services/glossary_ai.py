import logging
from typing import Dict, List

from app.services.llm import LLMClient

logger = logging.getLogger(__name__)

# Match pre-router glossary httpx behavior: short timeout, single attempt.
_GLOSSARY_HINT_TIMEOUT = 10.0
_GLOSSARY_BULK_TIMEOUT = 30.0
_GLOSSARY_MAX_RETRIES = 0


class GlossaryAIService:
    """Phonetic hint generation via the shared LLM router."""

    def __init__(self) -> None:
        self.llm = LLMClient()

    def _hints_from_parsed(self, data: object) -> List[str]:
        if isinstance(data, list):
            return [str(h).strip() for h in data if h]
        if isinstance(data, dict):
            for key in data:
                if isinstance(data[key], list):
                    return [str(h).strip() for h in data[key] if h]
        return []

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

Return JSON with a single key "hints" whose value is an array of strings.
"""

        try:
            data = await self.llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a phonetic error prediction engine. Output only JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                timeout=_GLOSSARY_HINT_TIMEOUT,
                max_retries=_GLOSSARY_MAX_RETRIES,
            )
            hints = self._hints_from_parsed(data)
            if hints:
                return hints
            if isinstance(data, dict) and "hints" in data:
                val = data["hints"]
                if isinstance(val, list):
                    return [str(h).strip() for h in val if h]
            return []
        except Exception as e:
            logger.error("Failed to generate phonetic hints: %s", e)
            return []

    BULK_BATCH_SIZE = 15

    async def generate_phonetic_hints_bulk(
        self, words: List[str], category: str = "General"
    ) -> Dict[str, List[str]]:
        """
        Predict sound-alikes for multiple words in batched LLM calls.
        Returns {word: [hint1, hint2, ...]}.
        """
        if not words:
            return {}
        seen = set()
        unique = []
        for w in words:
            w = (w or "").strip()
            if w and w not in seen:
                seen.add(w)
                unique.append(w)
        if not unique:
            return {}

        result: Dict[str, List[str]] = {}
        for i in range(0, len(unique), self.BULK_BATCH_SIZE):
            batch = unique[i : i + self.BULK_BATCH_SIZE]
            batch_result = await self._generate_phonetic_hints_batch(batch, category)
            result.update(batch_result)
        return result

    async def _generate_phonetic_hints_batch(
        self, words: List[str], category: str
    ) -> Dict[str, List[str]]:
        """Single LLM call for a batch of words."""
        words_str = '", "'.join(words)
        prompt = f"""You are an expert in Speech-to-Text (STT) and Phonetics, specializing in Spanish-English "Spanglish" sales environments.
A salesperson is bulk-adding these terms (Category: {category}) to their glossary: "{words_str}".

For EACH word, predict 4-6 common ways it might be misheard or incorrectly transcribed by an AI configured for Spanish or Multi-language.

STT BEHAVIOR (Phonetic Physics):
- Acronym Collision: acronyms often heard as fragments (FTES → FPS, FT is)
- Spanglish Mapping: English vowels (ee, ea) collide with Spanish (i, e)
- Consonant Drift: terminal k/t/d → s/sh/ch (50k → 50 cash)
- Context Drift: Spanish accent to English-centric AI

Return ONLY a JSON object. Each key is the EXACT word, each value is an array of strings.
Example: {{"Edenred": ["En red", "Enred", "Eden red"], "FTES": ["FPS", "FTS", "FT is"]}}

Words to process: {words_str}
"""
        try:
            data = await self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Output only valid JSON. No preamble."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                timeout=_GLOSSARY_BULK_TIMEOUT,
                max_retries=_GLOSSARY_MAX_RETRIES,
            )
            if not isinstance(data, dict):
                return {}
            out: Dict[str, List[str]] = {}
            for word in words:
                val = data.get(word)
                if isinstance(val, list):
                    out[word] = [str(h).strip() for h in val if h]
                elif isinstance(val, str):
                    out[word] = [val.strip()] if val.strip() else []
                else:
                    out[word] = []
            return out
        except Exception as e:
            logger.error("Bulk phonetic hints failed: %s", e)
            return {w: [] for w in words}
