# F16 — Estado manual y cola que obedece al CRM · Plan

Spec: `docs/features/F16-estado-manual/spec.md` · Design: `docs/features/F16-estado-manual/design.md` (mandan sobre este plan).

Reglas: TDD en lógica determinista; cada edge case E1–E18 del spec con su test; todo detrás de `CRM_STATE_EXIT_ENABLED` (y requiere `DEAL_STAGE_CONFIRM_ENABLED`); flag apagado = comportamiento actual intacto. Tests backend: `cd backend && python -m pytest tests/hoy tests/hubspot tests/meetings -q`. Frontend: `node --experimental-strip-types --test src/lib/*.test.ts` y `npm run build`.

## Backend (Grok)
1. **Flag + migración + config.** `CRM_STATE_EXIT_ENABLED: bool = False` en `backend/app/config.py`. Migración `backend/migrations/054_crm_queue_states.sql` + `.down.sql` (columnas del design, backfill desde `meeting_booked_stage_id`, idempotente, test como `tests/meetings/test_meeting_stage_migration.py`). Añadir columnas a `backend/full_reset.sql`. `CRMConfigurationRequest/Response` (`app/models/crm_config.py`) y `app/services/crm_config.py`: guardar/leer `queue_state_source`, `queue_booked_states`, `queue_ended_states` (Pipedrive fuerza `deal_stage`, sin duplicados, un estado no puede estar en ambas listas) y devolver `queue_states_enabled`.
2. **`backend/app/services/hoy/crm_state.py` (puro).** `QueueStates`, `queue_states_enabled(supabase, company_id)`, `load_queue_states(...)`, `exit_reason(state, states) -> "booked"|"ended"|None`, `pick_deal_state(deals)` (último modificado, empate id mayor; Pipedrive `status:won`/`status:lost`), `confirmed_state_from_extraction(extraction, source, provider)` (lead: `raw_extraction.contact_properties.hs_lead_status`; deal: `raw_extraction.dealstage` / `stage_id`).
3. **Cola.** `hoy/priority.py::rank_candidates(..., states=None)`: con states, ignora `meeting_agreed`/`deal_status` y excluye por `crm_state`. `hoy/memo_facts.py`: con flag no marca `meeting_agreed`.
4. **Lectura de estados.** `hoy/assigned.py`: modo lead añade `hs_lead_status` a la búsqueda de contactos; modo deal lee deals (HubSpot deals search + associations v4 batch; Pipedrive deals v2) y pone `crm_state` en cada contacto. Lectura fallida → sin clave `crm_state` y cobertura partial. `hoy/context.py::fold_context`: si falta `crm_state`, conserva el anterior. Cablear en `app/api/contact_priorities.py`.
5. **Hoy.** `app/api/today.py`: ocultar tarjetas cuyo contacto tenga estado de salida (usando `contact_priority_context`). `hoy/materialize.py`: con flag, `deal_closed` inferido no suprime señales.
6. **Aprobación.** `app/services/memo_approval.py`: tras sync correcto de una aprobación revisada (no `skip_deal` en modo deal), escribir `crm_state` confirmado en `contact_priority_context.payload` del contacto. Sin revisión o sync fallido → nada.
7. **Revisión modo lead (HubSpot).** `deal_stage_confirm.preview_stage_kwargs` + `hubspot/preview.py`: fila `hs_lead_status` siempre presente y primera, preselección = primer estado «reunión agendada» si hay reunión acordada no omitida, si no la sugerida, si no la actual. Sin opciones en el portal → sin fila.

## Frontend (Composer)
8. Tipos en `src/lib/api/crm.ts` y `src/lib/api/hubspot-setup.ts`. `src/lib/queue-states.ts` (puro + test): opciones por modo/proveedor (HubSpot etapas de todos los pipelines o opciones de `hs_lead_status` del schema de contactos; Pipedrive etapas + Ganado/Perdido) y poda de ids que ya no existen al guardar. `src/components/dashboard/crm/QueueStatesPicker.tsx` compacto bajo el selector de reunión agendada en `HubSpotConfiguration.tsx` y `PipedriveConfiguration.tsx`, solo si `queue_states_enabled`. Textos es/en en `src/lib/product-catalog.ts`.

## Cierre
9. Línea del flag en `docs/features/MASTER_PLAN.md` §3. Suite completa verde.
