# F17 — Cuentas de SDR y AE

Spec: `docs/features/F17-roles-sdr-ae/spec.md`. Design: `docs/features/F17-roles-sdr-ae/design.md`.

Pieza 2 de 6. La 1 (F16) ya está en esta rama. Las piezas 3 a 6 no son tareas de este plan.

## Global Constraints

- Roles comerciales de Vocify: `sdr`, `ae`, `general`. Nunca se leen del CRM.
- Permiso sigue siendo `owner` | `admin` | `member`. No ampliar quién puede cambiar el permiso.
- Flag `SALES_ROLES_ENABLED`, default `false`. Apagado: el JSON no lleva la clave `sales_role`.
- Por defecto `general` («Ambos»).
- Un `member` no cambia ningún rol comercial (403). Owner y admin sí, también el del owner y el propio.
- Valor desconocido al leer: `general`. Valor inválido al crear invitación con el flag encendido: 400.
- Esta pieza no cambia Hoy, la cola, playbooks, visibilidad de notas ni el email de invitación.
- Tests primero en la lógica determinista. Cada edge case E1–E12 del spec tiene test.
- Migración reversible. Textos de UI en `product-catalog.ts`, es y en.

## Task 1: Migración

Archivos:
- `backend/migrations/055_sales_roles.sql`
- `backend/migrations/055_sales_roles.down.sql`
- `backend/full_reset.sql` (las dos tablas, mismas columnas y checks)
- `backend/tests/test_sales_roles_migration.py` siguiendo `backend/tests/meetings/test_queue_states_migration.py`

Columnas en `company_members` y `company_invitations`:

`sales_role TEXT NOT NULL DEFAULT 'general' CHECK (sales_role IN ('sdr', 'ae', 'general'))`

El up es idempotente (`ADD COLUMN IF NOT EXISTS`, drop/add del check). El down quita el check y la columna. El test aplica up sobre un esquema mínimo, comprueba el default `general` en una fila insertada sin la columna, aplica down y comprueba que la columna ya no está.

No toques código de aplicación.

## Task 2: Normalizar y flag

Archivos:
- `backend/app/services/sales_role.py`
- `backend/app/config.py` (`SALES_ROLES_ENABLED: bool = False` junto a `CRM_STATE_EXIT_ENABLED`)
- `docs/features/MASTER_PLAN.md` (una frase en la lista de flags por empresa)
- `backend/tests/test_sales_role.py`

`normalize_sales_role(value) -> str`: `sdr`, `ae` y `general` se devuelven tal cual; cualquier otra cosa, incluido `None` y `""`, devuelve `general`.

`SALES_ROLE_VALUES = frozenset({"sdr", "ae", "general"})`.

Tests: los tres valores válidos; `None`, `""`, `"owner"`, `"SDR"` → `general`.

## Task 3: API

Archivos: `backend/app/services/company.py`, `backend/app/api/company.py`, `backend/app/api/auth.py` (`CompanySummary`), modelos de request/response que ya viven junto a esas rutas. Tests en `backend/tests/test_sales_role_api.py`, mismo estilo de dobles que `backend/tests/test_company.py`.

Comportamiento, exactamente el de `design.md`:

- Invitación guarda `sales_role`. Flag apagado lo ignora y guarda `general`. Flag encendido y valor inválido: 400.
- Aceptar copia el rol de la invitación; si no es válido, `general`.
- `PATCH /company/members/{member_id}/sales-role`. Owner y admin. Member: 403. No cambia `role`. No reactiva `disabled`.
- Listado y sesión: con flag apagado no existe la clave `sales_role`. Con flag encendido sí. `GET /company/members` devuelve `sales_roles_enabled`.
- Quitar un miembro borra la fila (el rol se va con ella). No hace falta un camino nuevo si el delete actual ya borra la fila: un test lo afirma.

Cubre E1–E12. No cambies Hoy, cola ni playbooks.

## Task 4: Equipo

Archivos: `src/features/company/types.ts`, `src/features/company/api.ts`, el tipo de company en `src/features/auth`, `src/lib/product-catalog.ts`, `src/pages/dashboard/TeamPage.tsx`, `src/lib/sales-role.ts` + `src/lib/sales-role.test.ts`.

`sales-role.ts` exporta las opciones en orden `sdr`, `ae`, `general` y `salesRoleLabel(value, catalog)` que usa las claves `salesRoleSdr`, `salesRoleAe`, `salesRoleGeneral`. Un valor desconocido usa la etiqueta de `general`.

Catálogo:
- es: SDR, AE, Ambos. Etiqueta del grupo: «Rol comercial».
- en: SDR, AE, Both. Etiqueta: «Sales role».

En Equipo, si `salesRolesEnabled` es false, la pantalla queda como hoy. Si es true, el grupo de pastillas del rol comercial va junto al de permiso, por defecto Ambos, y cada miembro e invitación pendiente lo muestran. Owner y admin lo cambian con el PATCH nuevo. Un miembro no ve controles de cambio.

No añadas una pantalla. No cambies `HUBSPOT_INVITE_EMAIL_HINT`.

Test de `sales-role.ts` con `node --experimental-strip-types --test`.
