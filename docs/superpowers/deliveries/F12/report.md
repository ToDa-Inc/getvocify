# Informe F12

Estado: la ayuda en vivo no sale en una llamada. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Una llamada no muestra ayuda. Sin playbook o sin evidencia la tarjeta se queda en silencio | `shared/ui/copilot/suggestion-state.test.js` |
| Un paso se marca por evidencia, no por el tiempo transcurrido | el mismo archivo |
| Cambiar de reunión descarta la respuesta anterior. Un evento SSE partido no se lee hasta cerrar el frame | el mismo archivo, 3 passed |

## No verificado

- El overlay del escritorio no usa este estado. No hay comprobación nativa con la ventana minimizada.
- El detector de turnos de la beta no se ha sustituido por este módulo.
