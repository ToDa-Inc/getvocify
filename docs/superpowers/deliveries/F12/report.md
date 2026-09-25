# Informe F12

Estado: **BLOCKED** — nueve de trece criterios de aceptación del plan tienen prueba automatizada; cuatro requieren ventana Electron minimizada/fullscreen o reunión en vivo.

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| Pasos por evidencia, no por tiempo | `shared/ui/copilot/suggestion-state.test.js` (`stepStatus`); `backend/tests/copilot/test_checklist_http.py::test_capture_marks_met_only_with_stored_observations_and_evidence` |
| Sin playbook/respaldo, tarjeta silenciosa | `desktop/lib/live-assist-overlay.test.js`; `shared/ui/copilot/suggestion-state.test.js`; `chrome-extension/lib/live-assist-gate.test.js`; `backend/tests/copilot/test_live_meetings.py::test_empty_evidence_stays_silent_without_advice_text` |
| Ayuda desactivable | `shared/ui/copilot/pill.test.js` (`enabled: false`); `chrome-extension/lib/copilot-meeting-ui.test.js`; `chrome-extension/lib/copilot-suggest-body.test.js`; `desktop/lib/copilot-session.test.js` (`turnOffLiveAssist`) |
| Duración mínima, retirada y cooldown | `shared/ui/copilot/pill.test.js`; `chrome-extension/lib/copilot-pill-card.test.js` |
| Intervención del comercial oculta la línea | `shared/ui/copilot/pill.test.js` (`speakerRole: rep` y hold) |
| Cancelar/cambiar meeting descarta respuestas | `shared/ui/copilot/suggestion-state.test.js` (`reduceSuggestion`); `shared/ui/copilot/suggest-stream.test.js` |
| Beta + núcleo compartido (SSE/cancelación) | `shared/ui/copilot/suggest-stream.test.js`; `chrome-extension/lib/copilot-sse.test.js`; `src/features/copilot/api/suggest.ts` → `shared/ui/copilot/suggest-stream.js` |
| Desktop: una sesión STT y un suggest activo | `desktop/lib/copilot-session.test.js`; `desktop/lib/copilot-suggest.test.js`; `desktop/lib/overlay-no-duplicate-suggest.test.js` |
| Overlay minimizado/fullscreen nativo | **Bloqueado:** requiere ventana Electron minimizada o fullscreen sobre app de reunión |
| Flujo real desktop verificado | **Bloqueado:** mismo recorrido nativo fuera de unit tests |
| Overlay con sugerencia + progreso minimizado | **Bloqueado:** requiere principal minimizada y overlay visible en OS |
| Live/Idle/ayuda sin recorte ni foco robado | Parcial: `desktop/lib/shell.test.js` (`overlayBoundsForState`); **bloqueado** foco, Stop y doble clic nativos |
| Respaldo verbatim ≥12 caracteres | `backend/tests/copilot/test_live_meetings.py::test_short_verbatim_ref_is_not_grounded_without_playbook_evidence` |

## Comandos de cierre

```text
cd backend && .venv/bin/python -m pytest tests/copilot/test_live_meetings.py tests/copilot/test_checklist_http.py -q
node --test shared/ui/copilot/*.test.js
cd desktop && node --test lib/copilot-session.test.js lib/copilot-suggest.test.js lib/live-assist-overlay.test.js lib/overlay-no-duplicate-suggest.test.js lib/shell.test.js
make test-js
npm run build
```

## Bloqueos (no resueltos en este cierre)

- Verificación nativa del overlay con ventana principal minimizada o en fullscreen (criterios 9, 10, 11 parcial, 12).
- No se activó `INTELLIGENCE_WORKER_PUBLISH`; no se probaron micrófonos.
