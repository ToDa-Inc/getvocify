# Informe F04

Estado: reglas C09 y el bloque del inicio están en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Ranking: dolor reciente antes de «nunca llamado»; reunión acordada fuera; deal cerrado aparte | `1bfe60a` y el commit de esta lista | `tests/hoy/test_priority.py` |
| `GET /api/v1/contact-priorities`: vacío, parcial y sin CRM no se confunden | este commit | `tests/hoy/test_priority_http.py` |
| La web no convierte un 403 en lista vacía y conserva la lectura anterior si el refetch falla | este commit | `src/lib/contact-priorities.test.ts` |
| Migración `042_contact_priority_context.sql` | este commit | Tabla también en `full_reset.sql` |

## No verificado

- La ruta lee una caché de proceso, no la tabla `042`.
- HubSpot y Pipedrive no rellenan esa caché.
- «Abrir contactos en CRM» no abre un CRM: no hay URL de contactos.
- Reticle no tiene sesión en este worktree. El inicio no se recorrió en el navegador.
- `tsc --noEmit` pasó antes de los últimos botones. No sustituye un recorrido de la página.
