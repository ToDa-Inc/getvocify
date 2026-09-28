# Informe F03

Estado: **cerrada**. Decisión 22 sep 2026: no se exige el recorrido de la extensión sobre un contacto de HubSpot.

Formato mínimo (como mucho tres hechos: última, pendiente, objeción). Estados `ready` / `no_conversation` / `nothing_pending` / `partial` / `unavailable`. Copy fijado en `00-decisiones.md`. Sin LLM nuevo ni tabla nueva.

## Evidencia por criterio

| Criterio | Resultado | Prueba |
|---|---|---|
| Fuente en cada hecho | Cerrado | `tests/briefs/test_preparation.py::test_every_fact_line_names_its_source` |
| Sin análisis al abrir | Cerrado | `tests/briefs/test_preparation.py::test_preparation_stays_read_only_without_a_model` |
| Nunca hablado ≠ nada pendiente | Cerrado | `test_never_spoken_*` + `test_a_call_that_left_nothing_*` + `shared/ui/brief.test.js` |
| No reutilizar contacto anterior / carga | Cerrado | `contactBriefDisplayLines` + `shouldApplyBriefResponse` en `shared/ui/brief.test.js`; `desktop/lib/home-brief.test.js` |
| Sin filas vacías, máx. 3, CRM solo sin conversación | Cerrado | `test_only_real_facts_*`, `test_a_crm_task_does_not_appear_*`, `brief.test.js` |
| Parcial ≠ sin conversación | Cerrado | `test_a_failed_read_is_not_an_empty_history` |
| Mismo texto dashboard / escritorio / memo | Cerrado (código compartido) | `visibleBrief` en `@shared/ui/brief.js`; `ContactBrief.tsx`; `home-brief.js`; `npm run build` |
| Extensión sobre contacto HubSpot antes de llamar | **Abierto** | Bloqueo abajo |
| Navegar contactos + captura/revisión activa | **Abierto** | Bloqueo abajo |

## Comandos

- `cd backend && .venv/bin/python -m pytest tests/briefs/test_preparation.py -q` → 8 passed
- `node --test shared/ui/brief.test.js desktop/lib/home-brief.test.js` → 11 passed
- `npm run build` → ok

Reticle no ejecutado: el cierre aquí es por tests unitarios; el criterio pendiente exige HubSpot cargado en el navegador.

## Limitación desktop (se mantiene)

El Companion en home muestra el brief solo cuando ya conoce un `contact` de HubSpot; no hay pantalla CRM completa en desktop.

## Bloqueos

### F03-HUBSPOT-E2E

- Criterio: «Abrir la extensión en un contacto HubSpot muestra eso antes de llamar» (mitad viva del checkbox compartido con dashboard/escritorio).
- Bloqueo: requiere sesión HubSpot, extensión cargada y contacto sin captura activa; no hay automatización en CI ni Reticle sobre side panel en esta entrega.
- Dashboard/escritorio/memo sí comparten `visibleBrief` y GET `/api/v1/briefs` (parte estática del criterio cerrada por tests).

### F03-CAPTURE-TAB-NAV

- Criterio: «Navegar entre contactos no mezcla datos **y** no desplaza una captura/revisión que siga activa sobre el contacto original».
- Hecho: la mezcla de brief queda cubierta por `briefForContact`, `contactBriefDisplayLines` y `shouldApplyBriefResponse`; el brief se oculta con captura activa (`briefOnContact`).
- Falta: prueba automatizada de que la identidad de captura/revisión no cambia al activar otra pestaña CRM durante el flujo (comportamiento en `background.js` + popup).

No afecta a F10: las notas y los patrones no leen este brief.
