# Informe F12

Estado: la ayuda en vivo no sale en una llamada. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Una llamada no muestra ayuda. Sin playbook o sin evidencia la tarjeta se queda en silencio | `shared/ui/copilot/suggestion-state.test.js` |
| Listen en pestaña CRM usa `callMode`/`liveAssistKind` para tratar la sesión como reunión aunque `kind` siga en `call` | el mismo archivo |
| El shell del escritorio reenvía `kind`, `playbookReady`, `evidenceRefs` y `card` al overlay | `desktop/lib/shell.test.js` |
| El renderer del escritorio rellena `liveAssistOverlay` desde `playbook_ready`, `evidence_refs` y `text` del suggest | `desktop/lib/live-assist-overlay.test.js` |
| Un paso se marca por evidencia, no por el tiempo transcurrido | el mismo archivo |
| Cambiar de reunión descarta la respuesta anterior. Un evento SSE partido no se lee hasta cerrar el frame | el mismo archivo, 3 passed |
| Extensión: el background reenvía `playbook_ready` / `evidence_refs` del SSE al gate de `#copilot-card` | `chrome-extension/lib/live-assist-gate.test.js` |
| `/copilot/suggest` incluye `playbook_ready` y `evidence_refs` validados en el evento `result` para meetings | `backend/tests/copilot/test_live_meetings.py` |
| Escritorio: no repite `/copilot/suggest` tras éxito si la línea final es idéntica; un fallo deja la línea reintentable | `desktop/lib/copilot-suggest.test.js` |
| Escritorio: `/copilot/suggest` lleva `call_mode` desde la sesión (reunión vs llamada) y `contact_id` solo si la sesión ya lo tiene | `desktop/lib/copilot-suggest.test.js` |
| Backend: `contact_id` opcional en `/copilot/suggest` se normaliza en `SuggestContext` sin inventar contacto; `speakerphone` sigue siendo llamada y `meeting` reunión | `backend/tests/copilot/test_suggest_contact_context.py` |

## No verificado

- El overlay del escritorio muestra la ayuda solo en una reunión con playbook y evidencia. Una llamada se queda en la línea de transcripción. No hay comprobación nativa con la ventana minimizada.
- Escritorio: `overlayAssist` en `desktop/renderer/overlay.js`. Extensión: `#copilot-card` pasa por `copilotLiveAssistAllowed` / `assistAllowed` (misma regla: reunión con playbook y evidencia).
