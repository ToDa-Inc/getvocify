# Design · F16 — El comercial decide el estado; la cola obedece al CRM

## Resumen técnico
1. Tres columnas nuevas en `crm_configurations`: modo (`queue_state_source`) y dos listas de estados (`queue_booked_states`, `queue_ended_states`).
2. Módulo puro `backend/app/services/hoy/crm_state.py`: qué estados sacan de la cola, cómo se lee el estado de un contacto y qué estado confirmó el comercial.
3. La lectura de contactos asignados (`hoy/assigned.py`) añade `crm_state` a cada contacto: `hs_lead_status` en modo lead, o la etapa del último deal en modo deal.
4. `rank_candidates` y `/today` filtran con esos estados; con el flag encendido dejan de usar `meeting_agreed` y `deal_closed`.
5. La aprobación revisada escribe el estado confirmado en la caché `contact_priority_context` (efecto inmediato). La siguiente lectura del CRM lo sustituye.

## Toca el pipeline común?
- [ ] Añade campos a `extracted`: no.
- [ ] Añade etapa al pipeline: no.
- [x] Solo consume: `raw_extraction` revisado (estado confirmado), `meeting_proposals` (sugerencia), caché `contact_priority_context`.

## Modelo de datos
Migración `backend/migrations/054_crm_queue_states.sql` (+ `.down.sql`):

```sql
ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS queue_state_source TEXT NOT NULL DEFAULT 'deal_stage',
  ADD COLUMN IF NOT EXISTS queue_booked_states TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS queue_ended_states TEXT[] NOT NULL DEFAULT '{}';
-- CHECK queue_state_source IN ('deal_stage','lead_status')
-- Backfill: queue_booked_states = ARRAY[meeting_booked_stage_id] donde exista.
```

Valores de estado guardados:
- HubSpot etapa: id de etapa (`dealstage`). HubSpot lead: valor de la opción de `hs_lead_status`.
- Pipedrive: `str(stage_id)`, o `status:won` / `status:lost`.

Caché `contact_priority_context.payload` (sin migración, es JSONB): clave nueva `crm_state` (string o null). Solo existe la clave si el estado se leyó bien; si falta, se conserva la anterior (E11).

## API
- `GET/POST /crm/hubspot/configuration(configure)` y `/crm/pipedrive/configuration`: `CRMConfigurationRequest/Response` añaden `queue_state_source`, `queue_booked_states`, `queue_ended_states`. La respuesta añade `queue_states_enabled: bool` (flag encendido para la empresa). La pantalla muestra el bloque solo si es `true`.
- `GET /contact-priorities` y `GET /today`: sin cambios de forma; filtran por estado.
- Preview de memo (HubSpot): con modo lead, fila `hs_lead_status` obligatoria y primera.

## Prompts
Ninguno.

## Lecturas al CRM (modo deal)
- HubSpot: `POST /crm/v3/objects/deals/search` (owner IN owners de miembros, `dealstage`, `hs_lastmodifieddate`, paginado por `hs_object_id`), después `POST /crm/v4/associations/deals/contacts/batch/read` en lotes de 1000.
- Pipedrive: `GET /api/v2/deals?owner_id=<id>&limit=500` (cursor), que ya trae `person_id`, `stage_id`, `status` y `update_time`.
- Modo lead (HubSpot): añadir `hs_lead_status` a las propiedades de la búsqueda de contactos que ya se hace. Sin lecturas nuevas.

## Frontend
- `src/components/dashboard/crm/QueueStatesPicker.tsx`, compartido por `HubSpotConfiguration.tsx` y `PipedriveConfiguration.tsx`. Va debajo del selector de «reunión agendada» de F14: un selector de modo (solo HubSpot) y dos listas de casillas compactas («Sale de la cola · reunión agendada», «Sale de la cola · fin»). Peso visual secundario; sin pantalla nueva. Solo owner/admin (el resto lo ve en solo lectura, como el resto de la configuración).
- `src/lib/queue-states.ts` (puro, testeado): opciones de estado según modo y proveedor.
- Revisión: sin cambios de componentes; la fila llega como `ProposedUpdate` y ya se pinta.

## Feature flag
`CRM_STATE_EXIT_ENABLED` (config.py, por empresa). Solo actúa si `DEAL_STAGE_CONFIRM_ENABLED` también está encendido. Rollout: founders → 3 design partners con HubSpot (uno en modo lead) → betas.

## Riesgos y decisiones
| Decisión | Alternativas descartadas | Por qué |
|---|---|---|
| El CRM es la fuente de verdad del estado | Guardar solo lo confirmado en Vocify; híbrido completo | Una sola verdad; recoge cambios hechos en el CRM y reaperturas |
| Escritura inmediata en la caché al aprobar | Esperar a la siguiente lectura (≤ 30 min) | Un contacto recién agendado no puede seguir en la cola del comercial |
| En modo deal decide el deal modificado más recientemente | «Cualquier deal en salida»; «todos en salida» | Refleja lo último que hizo el comercial; regla simple y testeable |
| Lectura fallida conserva el último estado conocido | Vaciar el estado | Vaciarlo devolvería a la cola contactos ya agendados |
| Modo lead solo HubSpot | Leads de Pipedrive | Pipedrive no tiene estado de lead en la persona; se amplía si un cliente lo pide |

## Firma
- [ ] Revisado por: ____ · fecha: ____
