# Proceso de venta editable: plan de implementación

> Ejecución en línea (executing-plans), commits directos a `main`, todo apagado tras `SALES_PROCESS_ENABLED`.

**Goal:** que cada empresa defina su proceso como lista ordenada de tipos propios, construya el playbook de cada tipo
con Vocify, y que a cada miembro se le asignen los tipos que ejecuta, sin cambiar nada para los usuarios actuales.

**Architecture:** dos tablas nuevas independientes de las funciones SQL de `playbooks` (`company_sales_process`: orden
y `stage` por tipo; `member_interaction_types`: tipos por miembro o invitación). El rol `sales_role` se sigue
escribiendo, derivado de los tipos, así que sus ~50 lectores no cambian. Enrutado y visibilidad filtran por los tipos
asignados solo cuando existen.

**Tech Stack:** FastAPI + Supabase (patrón `AssistantStore`: InMemory/Sql, 503 `not_activated`), React/TS, ES/EN en
`product-catalog.ts`.

**Spec:** `docs/superpowers/specs/2026-10-17-proceso-de-venta-editable-design.md`

## Global Constraints
- Con el flag apagado o sin filas nuevas, `route`, `visible_to_role` y el lector de llamadas devuelven lo de hoy.
- Migración 084 idempotente, columnas/tablas nuevas; SQL de activación para el fundador (el agente no tiene DDL).
- No tocar coaching, ayuda en directo ni informes. `sales_role` solo se escribe derivado.
- Pantallas fáciles, intuitivas, bonitas, en el estilo de Inicio/Coaching; vista previa de desarrollo en claro, oscuro, móvil.
- Tests primero; `git add <rutas propias>`; commit a `main`; sin push hasta que Toni lo diga.

## Review Focus
1. Borrar o renombrar un tipo asignado a miembros: se limpia su lista; vacía vuelve a `NULL` (todos).
2. Empresa sin filas de proceso (la de hoy): la API devuelve el catálogo creado, en su orden, y nada falla.
3. Miembro con tipos que ya no existen o lista vacía: se trata como `NULL`.
4. Invitación con tipos que se acepta después: se copian al miembro y se deriva el rol.
5. Sin las tablas (503 `not_activated`): la pantalla lo dice con calma y el resto del producto no se entera.

### Task 1: Almacén y migración 084
Files: `backend/migrations/084_sales_process.sql` (+`.down.sql`), `backend/084_sales_process_APPLY_IN_SUPABASE.sql`,
`backend/app/services/sales_process/store.py`, test `backend/tests/sales_process/test_store.py`.
Produces: `SalesProcessStore` con `list_process(company_id) -> [{key, position, stage}]`,
`replace_process(company_id, rows)`, `get_member_types(company_id, *, user_id=None, invitation_id=None) -> list|None`,
`set_member_types(company_id, types|None, *, user_id=None, invitation_id=None)`, `drop_type(company_id, key)`;
`InMemorySalesProcessStore`, `SqlSalesProcessStore`, `SalesProcessUnavailable`, `get_sales_process_store`.

### Task 2: Lógica pura
Files: `backend/app/services/sales_process/logic.py`, test `test_logic.py`.
Produces: `STAGES`, `role_from_types(types, stage_of) -> "sdr"|"ae"|"general"`, `stage_for(key, rows)`
(fila propia, si no catálogo por rol, si no `first_contact`), `assigned_types(raw, existing_keys) -> list|None`
(limpia claves que no existen; vacía = `None`), `slug_key(label, taken)`.

### Task 3: Flag
Files: `config.py`, `feature_flags.py`; test de flags. `SALES_PROCESS_ENABLED` apagado y en `CLIENT_FLAGS`.

### Task 4: API del proceso
Files: `backend/app/api/sales_process.py`, `router.py`, tests. `GET /sales-process` → `[{key,label,stage,recognize,
position,has_playbook}]`; `PUT /sales-process` reemplaza la lista: crea los tipos nuevos (`add_type`), renombra y fija
`recognize` (`set_meta`), guarda orden y stage, archiva los quitados y limpia sus asignaciones. Owner/admin, flag, 503.

### Task 5: Tipos por miembro e invitación
Files: `backend/app/api/company.py`, `backend/app/services/company.py` (ganchos mínimos), `api/sales_process.py`,
tests. `PUT /sales-process/members/{user_id}` y campo `interaction_types` al invitar; aceptar la invitación copia los
tipos; en ambos casos se deriva y se escribe `sales_role`.

### Task 6: Enrutado y visibilidad por tipos asignados
Files: `services/playbooks/motion.py`, `routing.py`, tests de equivalencia. Con tipos asignados: solo esos tipos son
visibles y candidatos; con uno solo, la llamada va a él; sin tipos, comportamiento actual.

### Task 7: Lectura de llamadas con la definición propia
Files: `services/playbooks/type_classifier.py`, test. `describe_type` usa nombre + `stage` + `recognize` de los tipos
propios, y el lector solo ofrece los tipos del miembro.

### Task 8: Rellenar lo existente y SQL de activación
Files: `docs/superpowers/plans/2026-10-17-activacion-proceso-de-venta.sql`. Backfill de `company_sales_process` desde el
catálogo creado y de `member_interaction_types` desde `sales_role`.

### Task 9: Front: API, hook y editor del proceso
Files: `src/features/sales-process/{api.ts,useSalesProcess.ts,SalesProcessEditor.tsx}`, copia ES/EN, preview.

### Task 10: Front: Playbook con el proceso primero
Files: `PlaybookList.tsx`, `PlaybookStart.tsx`. Con el flag: la empresa sin tipos ve "¿Qué tipos de interacción
tenéis?"; la lista de tipos es la del proceso (sin Llamadas/Reuniones ni "Sin crear"); cada tipo sin playbook ofrece
construirlo con Vocify.

### Task 11: Front: equipo
Files: `src/pages/dashboard/TeamPage.tsx`, `src/features/company/*`. Casillas "Qué interacciones hace" al invitar y en
el perfil; sin selector SDR/AE/General con el flag; roles visibles Owner / Admin / Miembro.

### Task 12: Construir cada tipo con Vocify
Files: `services/playbooks/gaps.py`, `assistant.py`, tests. Los huecos incluyen, por tipo propio sin pasos, "¿qué
pasos seguís en {tipo}?" con las plantillas como ejemplo.

### Task 13: Cierre
Pasadas completas, comprobación de lo prohibido, spec actualizado, resumen.
