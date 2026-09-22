# Informe F04

Estado: reglas C09 y el enlace a contactos del CRM cuando hay proveedor conocido. HubSpot sin portal no inventa una URL.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Ranking: dolor reciente antes de «nunca llamado»; reunión acordada fuera; deal cerrado aparte | `1bfe60a` y el commit de esta lista | `tests/hoy/test_priority.py` |
| `GET /api/v1/contact-priorities`: vacío, parcial y sin CRM no se confunden | `3b6a687` | `tests/hoy/test_priority_http.py` |
| La web no convierte un 403 en lista vacía y conserva la lectura anterior si el refetch falla | `3b6a687` | `src/lib/contact-priorities.test.ts` |
| Migración `042_contact_priority_context.sql` | `3b6a687` | Tabla también en `full_reset.sql` |
| Página incompleta de HubSpot o Pipedrive no es «nunca llamado»; email ambiguo no asigna; el mismo nombre no asigna; un fallo conserva la hora | este commit | `tests/hoy/test_priority_context.py` 4 passed, incluido Postgres aislado |

## No verificado

- El `GET` selecciona `crm_connections` y `contact_priority_context` por `company_id`. Las pruebas usan un cliente falso con el mismo `select`/`eq`; no hay una base Supabase real detrás.
- La lectura de contactos asignados usa el `access_token` de la conexión (`connection_assigned_fetch`); `collect_assigned` recorre HubSpot `POST /crm/v3/objects/contacts/search` y Pipedrive `GET /persons` v2. Si el transporte falla, no sustituye la caché.
- «Abrir contactos en CRM» abre Pipedrive o HubSpot cuando hay portal. Sin portal, HubSpot no tiene enlace.
