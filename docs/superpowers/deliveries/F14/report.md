# Informe F14

Estado: **cerrada** contra el Definition of Done del plan (criterios de aceptación § Criterio de aceptación). Sin push.

## Criterio → prueba

| Criterio | Prueba |
|---|---|
| «Podríamos vernos» no es acuerdo confirmado | `tests/meetings/test_proposals.py::test_we_could_meet_is_not_a_confirmed_agreement` |
| 16:00 corregido a 17:00 confirmado por ambos | `tests/meetings/test_proposals.py::test_a_corrected_time_keeps_the_last_time_both_confirmed` |
| Fecha sin hora sin default 09:00 | `tests/meetings/test_proposals.py::test_a_date_without_hour_does_not_default_to_nine` |
| Zona horaria y DST (hora duplicada pide revisión) | `test_a_repeated_dst_hour_asks_for_review`, `test_five_oclock_without_context_is_not_seventeen` |
| Repetir aprobación una sola actividad | `test_writes.py::test_repeating_an_approval_*`, `test_accept_http.py::test_accept_once_*`, `test_crm_writer.py` (mock HTTP) |
| Corregir propuesta sin duplicar KPI remoto | `test_writes.py::test_correcting_a_proposal_reuses_one_remote_activity` |
| Meeting booked ≠ close / venta ganada | `closes_deal is False` en propuestas y escrituras; `change_stage` no-op sin mapeo |
| Overlay sin «Reunión detectada»; revisión sí tras extracción | `shared/ui/meeting-proposal.test.js` (surface `live`, `extractionPending`, detectada sin CRM) |
| Estados distintos y reabrir conserva propuesta/decisión | `meeting-proposal.test.js` estados; `test_reopening_review_keeps_*`; GET `test_get_returns_the_stored_proposal_*` |

## Evidencia adicional

| Pieza | Prueba |
|---|---|
| Hook post-extracción inserta propuesta una vez por revisión | `tests/memos/test_post_extraction_hooks.py` |
| Propuesta ambigua persiste `starts_at` NULL | Postgres aislado en `test_an_ambiguous_proposal_is_stored_without_a_start_time` |
| Accept/omit/reconcile HTTP | `tests/meetings/test_accept_http.py` |
| Revisión web: carga GET, vacío oculto, error de lectura | `src/lib/meeting-proposal-review.test.ts` + `MeetingProposalReview.tsx` |
| Copy vía catálogo `shared/ui/i18n.js` | `meeting-proposal.test.js::localizes titles by lang` |

## Bloqueos (fuera del DoD de aceptación)

| Tema | Motivo |
|---|---|
| Escritura CRM en tenant real HubSpot/Pipedrive | No ejecutada en este cierre (sin llamada live CRM). El adaptador se prueba con `httpx.MockTransport` en `test_crm_writer.py` y writer inyectado en accept HTTP. |

## Comandos de cierre ejecutados

- `cd backend && .venv/bin/python -m pytest tests/meetings -q` → 22 passed
- `node --test shared/ui/meeting-proposal.test.js` → 6 passed
- `node --test src/lib/meeting-proposal-review.test.ts` → 5 passed
