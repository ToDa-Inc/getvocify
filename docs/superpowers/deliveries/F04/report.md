# Informe F04

Estado: reglas C09 y el bloque del inicio están en `feat/vocify-v1`. No está cerrada.

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
- Los proveedores no llaman a la red: `parse_assigned_page` interpreta una página ya recibida.
- «Abrir contactos en CRM» no abre un CRM: no hay URL de contactos.
- Reticle no tiene sesión en este worktree. El inicio no se recorrió en el navegador.
