from typing import List, Dict, Any, Optional
from supabase import Client
from app.deps import get_supabase
from app.services.company import get_company_id_for_user
import logging

logger = logging.getLogger(__name__)

class GlossaryService:
    def __init__(self, supabase: Client = None):
        self.supabase = supabase or get_supabase()

    def _company_id_for_user(self, user_id: str) -> Optional[str]:
        return get_company_id_for_user(self.supabase, user_id)

    async def get_user_glossary(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetch the shared company glossary (falls back to legacy user_profiles).
        """
        company_id = self._company_id_for_user(user_id)
        table = "companies" if company_id else "user_profiles"
        key_col = "id"
        key_val = company_id or user_id
        try:
            response = (
                self.supabase.table(table)
                .select("glossary")
                .eq(key_col, key_val)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            if not rows:
                return []
            return rows[0].get("glossary", []) or []
        except Exception as e:
            logger.error("Error fetching glossary for user %s: %s", user_id, e)
            return []

    async def update_glossary(self, user_id: str, glossary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Update the shared company glossary (owner/admin only at API layer).
        """
        company_id = self._company_id_for_user(user_id)
        table = "companies" if company_id else "user_profiles"
        key_col = "id"
        key_val = company_id or user_id
        try:
            response = (
                self.supabase.table(table)
                .update({"glossary": glossary})
                .eq(key_col, key_val)
                .execute()
            )
            return response.data[0].get("glossary", []) if response.data else []
        except Exception as e:
            logger.error("Error updating glossary for user %s: %s", user_id, e)
            raise e

    def format_for_deepgram(self, glossary: List[Dict[str, Any]]) -> List[str]:
        """
        Formats glossary for Deepgram Nova-3 `keyterm` (correct spellings only).
        """
        keywords = []
        for item in glossary:
            word = item.get("target_word")
            if word:
                keywords.append(word)
        return keywords

    def format_for_speechmatics(self, glossary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Formats glossary for Speechmatics 'custom_vocabulary' parameter.
        """
        sm_glossary = []
        for item in glossary:
            content = item.get("target_word")
            sounds_like = item.get("phonetic_hints", [])
            if content:
                entry = {"content": content}
                if sounds_like:
                    entry["sounds_like"] = sounds_like
                sm_glossary.append(entry)
        return sm_glossary

    def format_for_llm(self, glossary: List[Dict[str, Any]]) -> str:
        """
        Formats glossary into a descriptive string for LLM system prompt instructions.
        """
        if not glossary:
            return ""
            
        lines = ["Ground Truth Glossary (Correction Guide):"]
        for item in glossary:
            word = item.get("target_word")
            hints = item.get("phonetic_hints", [])
            category = item.get("category", "General")
            
            hint_str = f" (often misheard as: {', '.join(hints)})" if hints else ""
            lines.append(f"- {word} [{category}]{hint_str}")
            
        return "\n".join(lines)
