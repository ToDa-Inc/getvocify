F12: Chrome live-assist suggest body skips non-meeting `callMode` and sends `contact_id` only on CRM contact records.
Backend: `SYSTEM_PROMPT` de suggest incluye `evidence_refs` y `source_id` en el JSON obligatorio (alineado con `copilot_suggest_v1`).
Live assist y dashboard copilot ya no envían el pitch ficticio de Vocify: sin texto guardado, `product_context` se omite y el textarea queda vacío con placeholder en español.
El párrafo legacy guardado en `vocify_copilot_product_context` se trata como vacío (misma omisión de `product_context`); otro texto de empresa sigue enviándose.
Desktop overlay: checklist de meeting vía `POST /copilot/checklist` y renderer puro `shared/ui/copilot/checklist.js` bajo la tarjeta de ayuda.
Backend: `POST /api/v1/copilot/checklist` devuelve pasos del snapshot publicado y marca `met` solo con `playbook_observations` en la captura y `evidence_refs` no vacíos; modos no-meeting y ambigüedad de playbook sin `capture_id` responden checklist vacío.
