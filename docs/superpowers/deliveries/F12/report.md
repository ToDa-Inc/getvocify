F12: Chrome live-assist suggest body skips non-meeting `callMode` and sends `contact_id` only on CRM contact records.
Backend: `SYSTEM_PROMPT` de suggest incluye `evidence_refs` y `source_id` en el JSON obligatorio (alineado con `copilot_suggest_v1`).
Live assist y dashboard copilot ya no envían el pitch ficticio de Vocify: sin texto guardado, `product_context` se omite y el textarea queda vacío con placeholder en español.
El párrafo legacy guardado en `vocify_copilot_product_context` se trata como vacío (misma omisión de `product_context`); otro texto de empresa sigue enviándose.
