# Informe F12

Estado: la ayuda en vivo no sale en una llamada. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Una llamada no muestra ayuda. Sin playbook o sin evidencia la tarjeta se queda en silencio | `shared/ui/copilot/suggestion-state.test.js` |
| Un paso se marca por evidencia, no por el tiempo transcurrido | el mismo archivo |
| Cambiar de reunión descarta la respuesta anterior. Un evento SSE partido no se lee hasta cerrar el frame | el mismo archivo, 3 passed |

## No verificado

- El overlay del escritorio muestra la ayuda solo en una reunión con playbook y evidencia. Una llamada se queda en la línea de transcripción. No hay comprobación nativa con la ventana minimizada.
- Escritorio: `overlayAssist` en `desktop/renderer/overlay.js`. Extensión: `#copilot-card` pasa por `copilotLiveAssistAllowed` / `assistAllowed` (misma regla: reunión con playbook y evidencia).
