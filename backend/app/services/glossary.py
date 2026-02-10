from typing import List, Dict, Any
from supabase import Client
from app.deps import get_supabase
import logging

logger = logging.getLogger(__name__)

class GlossaryService:
    def __init__(self, supabase: Client = None):
        self.supabase = supabase or get_supabase()

    async def get_user_glossary(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetch the custom vocabulary / glossary from user_profiles.
        """
        try:
            response = self.supabase.table("user_profiles") \
                .select("glossary") \
                .eq("id", user_id) \
                .single() \
                .execute()
            
            return response.data.get("glossary", []) if response.data else []
        except Exception as e:
            logger.error(f"Error fetching glossary for user {user_id}: {e}")
            return []

    async def update_glossary(self, user_id: str, glossary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Update the entire glossary array for a user.
        """
        try:
            response = self.supabase.table("user_profiles") \
                .update({"glossary": glossary}) \
                .eq("id", user_id) \
                .execute()
            
            return response.data[0].get("glossary", []) if response.data else []
        except Exception as e:
            logger.error(f"Error updating glossary for user {user_id}: {e}")
            raise e

    def format_for_deepgram(self, glossary: List[Dict[str, Any]]) -> List[str]:
        """
        Formats glossary for Deepgram's 'keywords' parameter.
        Note: We use plain words for maximum compatibility with nova-3.
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
