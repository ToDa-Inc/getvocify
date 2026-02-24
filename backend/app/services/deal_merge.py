"""
Deal merge service for updating existing deals.

When a new audio/memo is matched to an existing deal, this service merges
existing deal properties with the new extraction intelligently:
- description: append new summary (keep history)
- scalar fields: use new value if present, else keep existing
- list fields: add new items, remove obsolete, dedupe
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.llm import LLMClient

logger = logging.getLogger(__name__)


def _format_prop_for_prompt(name: str, value: Any) -> str:
    """Format a property for the LLM prompt."""
    if value is None or value == "":
        return f"- {name}: (vacío)"
    if isinstance(value, list):
        return f"- {name}: {value}"
    return f"- {name}: {value}"


class DealMergeService:
    """
    Merges new extraction with existing deal properties.
    Uses LLM to decide how to combine values (append, replace, merge lists).
    """

    def __init__(self) -> None:
        self.llm = LLMClient()

    async def merge_properties(
        self,
        existing_properties: dict[str, Any],
        new_properties: dict[str, Any],
        allowed_fields: list[str],
        transcript: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Merge existing deal properties with new (already mapped to HubSpot format).

        Args:
            existing_properties: Current deal properties from HubSpot
            new_properties: New properties from map_extraction_to_properties_with_stage
            allowed_fields: Fields we're allowed to update
            transcript: Optional transcript snippet for context

        Returns:
            Merged properties dict (HubSpot format, only fields to update)
        """
        fields_to_consider = [
            f for f in allowed_fields
            if f not in ("hs_object_id", "hs_createdate", "hs_lastmodifieddate")
        ]
        if not fields_to_consider:
            return {}

        existing_str = "\n".join(
            _format_prop_for_prompt(k, existing_properties.get(k))
            for k in fields_to_consider
            if k in existing_properties or k in new_properties
        )
        new_str = "\n".join(
            _format_prop_for_prompt(k, new_properties.get(k))
            for k in fields_to_consider
            if k in new_properties and new_properties.get(k) is not None
        )

        transcript_snippet = ""
        if transcript and len(transcript) > 50:
            transcript_snippet = transcript[:1500] + ("..." if len(transcript) > 1500 else "")

        prompt = f"""Tienes un Deal existente en HubSpot con estos valores:

{existing_str or "(ninguno)"}

El usuario ha grabado un nuevo audio. De la transcripción se ha extraído:

{new_str or "(ninguno nuevo)"}
"""

        if transcript_snippet:
            prompt += f"""

Fragmento de transcripción:
\"\"\"
{transcript_snippet}
\"\"\"
"""

        prompt += """

INSTRUCCIONES:
- **description**: AÑADE el nuevo resumen al existente. Formato: valor_existente + "\\n\\n---\\n\\n" + nuevo_resumen. Nunca borres el historial.
- **amount, closedate, dealstage** y otros escalares: USA el nuevo valor si la extracción lo tiene; si no, MANTÉN el existente.
- **dealname**: MANTÉN el existente (es el mismo deal).
- Campos tipo lista (ej. pain points, competidores): FUSIONA - añade los nuevos que no estén, mantén los existentes que sigan siendo relevantes. Si el usuario dice que algo "ya no aplica" o "se resolvió", quítalo.
- Si el nuevo valor es vacío/null y el existente tiene valor, MANTÉN el existente.
- Devuelve las propiedades con los valores YA en formato HubSpot (closedate = timestamp ms, amount = string).
- Devuelve SOLO los campos que deben actualizarse. No incluyas campos sin cambios.

Devuelve JSON. Ejemplo: {"description": "existente\\n\\n---\\n\\nNuevo", "amount": "5000"}
Si no hay cambios, devuelve {}.
Devuelve ÚNICAMENTE JSON válido."""

        messages = [
            {
                "role": "system",
                "content": "Eres un asistente que fusiona datos de CRM. Devuelves solo JSON válido.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            out = await self.llm.chat_json(messages, temperature=0.0)
        except Exception as e:
            logger.warning("Deal merge LLM failed: %s. Using fallback.", e)
            return self._fallback_merge(existing_properties, new_properties, allowed_fields)

        if not isinstance(out, dict):
            return self._fallback_merge(existing_properties, new_properties, allowed_fields)

        merged = {
            k: v for k, v in out.items()
            if k in allowed_fields and v is not None and v != ""
        }
        return merged

    def _fallback_merge(
        self,
        existing: dict[str, Any],
        new: dict[str, Any],
        allowed_fields: list[str],
    ) -> dict[str, Any]:
        """Fallback: use new if present, else keep existing. Description = append."""
        merged = {}
        for f in allowed_fields:
            if f in ("dealname", "hs_object_id", "hs_createdate", "hs_lastmodifieddate"):
                continue
            new_val = new.get(f)
            existing_val = existing.get(f)
            if f == "description":
                if new_val and existing_val:
                    merged[f] = f"{existing_val}\n\n---\n\n{new_val}"
                elif new_val:
                    merged[f] = new_val
                elif existing_val:
                    pass
            elif new_val is not None and new_val != "":
                merged[f] = new_val
            elif existing_val is not None and existing_val != "":
                merged[f] = existing_val
        return merged
