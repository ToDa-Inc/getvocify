# Playbook: funnel de ventas y vuestra empresa en una sola pantalla

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que la página Playbook, con `SALES_PROCESS_ENABLED`, sea una sola pantalla con dos bloques (Funnel de ventas y Vuestra empresa) y un tercero (otros tipos de llamada), donde todo se crea y se edita en ventanas emergentes, sin cambiar cómo funciona hoy el playbook.

**Architecture:** una pantalla nueva `PlaybookHome` sustituye, solo en modo proceso, al raíl + detalle actual de `PlaybookList`. El detalle de una interacción (`CallTypePanel`) y el de la empresa (`CompanyKnowledge`) se reutilizan tal cual dentro de ventanas laterales. Crear = una ventana con el editor de tipos y un segundo paso con tres caminos. Backend: una migración pequeña (085) añade el objetivo de cada tipo y el valor `other` de `stage` para las llamadas fuera del funnel.

**Tech Stack:** React/TS/Tailwind (`THEME_TOKENS`), Radix Dialog y Sheet ya en el proyecto, FastAPI + Supabase, ES/EN en `product-catalog.ts`.

**Spec:** `docs/superpowers/specs/2026-10-17-proceso-de-venta-editable-design.md` (esta pantalla es su capa de UI) y los dos croquis de Toni del 18 oct.

## Global Constraints
- Cambio de UI/UX: no cambiar el funcionamiento del playbook (pasos, objeciones, publicar, intake, asistente, coaching). Con el flag apagado la página es la de hoy.
- Todo sobre el fondo de la app: sin tarjetas blancas ni cajas ajenas a la estética (contornos finos, `THEME_TOKENS`, `Button` y `Segmented` del proyecto).
- Todo en una pantalla: crear y editar se hacen en ventanas emergentes; no se navega a otra vista.
- Imprescindibles de una interacción del funnel: **objetivo** y **descripción de la llamada** (la descripción es la frase `recognize` que ya lee Vocify para reconocer el tipo). Las de "otro tipo de llamada" no los exigen y no puntúan en coaching.
- El funnel se dibuja de más ancho a más estrecho, en el orden del proceso. Clic en una interacción abre su información y pasos.
- "Producto y oferta" sale de Ajustes y vive en Vuestra empresa (mismo dato: `companies.product_context`).
- Tests primero; `git add <rutas propias>`; commits a `main`; sin push hasta que Toni lo diga.

## Review Focus
1. Empresa sin nada (primera vez): dos bloques vacíos con "Crear +", y crear no deja la pantalla rota si las tablas no existen (503 `not_activated`).
2. Una interacción del funnel sin objetivo o sin descripción no se puede guardar; una de "otro tipo" sí.
3. Quitar o reordenar interacciones del funnel no toca las de "otro tipo" ni sus playbooks.
4. Una empresa que ya tenía "Producto y oferta" lo ve rellenado en Vuestra empresa, y el enlace antiguo de Ajustes la lleva a Playbook.
5. Con el flag apagado nada cambia (incluida la lista de Ajustes).

### Task 1: Objetivo por tipo y llamadas fuera del funnel (backend)
**Files:** Create `backend/migrations/085_sales_process_goal.sql` (+`.down.sql`, `backend/085_sales_process_goal_APPLY_IN_SUPABASE.sql`); Modify `backend/app/services/sales_process/{store,logic,process}.py`, `backend/app/api/sales_process.py`; Test `backend/tests/sales_process/`.
**Interfaces:** Produces: `company_sales_process.goal TEXT` y `stage` admite `other`; filas `{key, position, stage, goal}`; `ProcessType` gana `goal: Optional[str] (<=160)`; GET/PUT devuelven `goal`; `role_from_types` ignora los tipos `other` (solo `other` = `general`); `apply_process` exige `goal` y `recognize` (descripción) a los tipos de `first_contact` y `deal` (422 `goal_required` / `description_required`) y no a `other`.
- [ ] Step 1: tests que fallan: el store guarda y devuelve `goal`; `role_from_types(["x"], stage_of=lambda _: "other") == "general"` y mezclar `other` con `first_contact` da `sdr`; la API rechaza un tipo de funnel sin objetivo o sin descripción y acepta uno `other` sin ellos; `GET` devuelve el objetivo.
- [ ] Step 2: ejecutar (FAIL), implementar, ejecutar (PASS).
- [ ] Step 3: SQL de 085 idempotente (`ADD COLUMN IF NOT EXISTS goal`, cambiar el CHECK de `stage`), commit `feat(sales-process): goal per type and calls outside the funnel`.

### Task 2: Producto y oferta pasa a Vuestra empresa
**Files:** Modify `src/pages/dashboard/settings/OfferSection.tsx` (redirige), `src/lib/settings-nav.ts` (quita la entrada), `src/features/playbooks/components/CompanyKnowledge.tsx` (nueva pestaña/zona "Producto y oferta" con `ProductOfferSettings`); Test `src/lib/settings-nav.test.ts` si existe.
- [ ] Step 1: test: la lista de Ajustes ya no contiene `offer`; la ruta `/dashboard/settings/offer` redirige a `/dashboard/playbook`.
- [ ] Step 2: implementar con el mismo guardado de hoy (`authApi.updateProfile({ productContext })`); en Vuestra empresa el texto va en una sección propia al inicio.
- [ ] Step 3: commit `feat(playbook): product and offer live in Vuestra empresa`.

### Task 3: Pieza pura del funnel y copia ES/EN
**Files:** Create `src/lib/playbook-home.ts` (+test); Modify `src/lib/product-catalog.ts` vía `.superpowers/scratch/copy_home.py`.
**Interfaces:** `funnelWidths(count, min = 0.46) -> number[]` (1 → [1]; decrece lineal de 1 a `min`); `splitFunnel(types) -> {funnel, other}` (los `other` fuera, orden conservado); `homeProgress(types) -> {total, written}` (cuántos tienen contenido); `COMPANY_AREAS` (empresa, producto, oferta, competencia, ICP, casos) con la sección de `CompanyKnowledge` a la que abre cada una.
- [ ] Step 1: tests (anchuras decrecientes y nunca bajo el mínimo; `other` separado; progreso).
- [ ] Step 2: implementar y añadir la copia (títulos, textos de cada bloque, ventanas, tres caminos, errores).
- [ ] Step 3: commit.

### Task 4: Pantalla `PlaybookHome`
**Files:** Create `src/features/playbooks/components/home/{PlaybookHome,FunnelBlock,CompanyBlock,OtherCalls}.tsx`; Modify `src/pages/dev/PlaybookAssistantPreview.tsx`.
**Interfaces:** `PlaybookHomeView` (pura): `types: {key,label,goal,description,stage,state}[]`, `company: {areas: {id,filled}[]}`, `canEdit`, `onCreateFunnel()`, `onOpenType(key)`, `onCreateCompany()`, `onOpenCompany(area?)`, `onCreateOther()`.
- [ ] Step 1: escenarios de vista previa: `home-empty` (los dos bloques vacíos, croquis 1), `home-filled` (funnel con 4 interacciones y objetivo bajo cada una, empresa con sus áreas, "SAC" en otros, croquis 2), `home-mobile`.
- [ ] Step 2: implementar. Titulares centrados sobre cada bloque; bloque vacío = contorno punteado con "Crear +"; funnel = píldoras de contorno fino con ancho de `funnelWidths`, el objetivo bajo cada una en texto pequeño; empresa = las seis áreas como lista limpia con un punto de estado; abajo "¿Quieres que Vocify te ayude en otro tipo de llamadas?" con las suyas y "+ crear interacción". Mismo fondo, sin tarjetas.
- [ ] Step 3: comprobar en vista previa (claro, oscuro, móvil) y commit.

### Task 5: Ventana "Tu funnel" y los tres caminos
**Files:** Create `src/features/playbooks/components/home/{ProcessDialog,PathChoice}.tsx`; Modify `src/features/sales-process/SalesProcessEditor.tsx` (campos objetivo y descripción, modo "otras llamadas").
- [ ] Step 1: la ventana tiene dos pasos. Paso 1: el editor (nombre, objetivo, descripción, fase del funnel, orden); se guarda con `PUT /sales-process`. Paso 2: "¿Cómo quieres darnos el contenido?" con tres opciones: subir un PDF completo (la caja de intake de varios archivos dentro de la ventana), ir interacción por interacción subiendo documentos (abre la primera sin contenido), ir interacción por interacción respondiendo preguntas y creándolo con Vocify (las preguntas guiadas por tipo, dentro de la ventana). "Lo hago luego" cierra.
- [ ] Step 2: la edición posterior reabre el paso 1; "otras llamadas" usa el mismo editor con `stage = other`, sin obligar objetivo ni descripción.
- [ ] Step 3: escenarios de vista previa de cada paso y commit.

### Task 6: Ventanas laterales de interacción y empresa, y cableado
**Files:** Modify `src/features/playbooks/components/PlaybookList.tsx`; Create `home/{TypeSheet,CompanySheet}.tsx`.
- [ ] Step 1: en modo proceso `PlaybookList` pinta `PlaybookHome`; abrir una interacción muestra el `detail()` actual en un `Sheet`; abrir Vuestra empresa muestra `CompanyKnowledge` con su zona de producto y oferta; el asistente de mejoras (`ImproveHub`) se conserva encima cuando está activo; sin flag, nada cambia.
- [ ] Step 2: quitar el bloque de subida y el enlace "Editar mi proceso" del modo proceso (ahora viven en las ventanas).
- [ ] Step 3: build, lint de los ficheros tocados, tests, commit.

### Task 7: Cierre
- [ ] Pasadas completas (backend de `sales_process` y `playbooks`, `src/lib/*.test.ts`, build), comprobar que con el flag apagado la página y Ajustes son los de hoy, SQL de activación de 085, spec actualizado y resumen para Toni (qué no se ha podido ver en la página real).
