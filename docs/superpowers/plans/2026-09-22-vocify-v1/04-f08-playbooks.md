# F08 — Playbooks por tipología y onboarding manual: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Publicar playbooks por tipología con revisión humana, versiones estables y onboarding manual.

**Arquitectura:** Importación transforma contenido aportado en borrador. Publicación atómica activa una versión inmutable; consumidores fijan esa versión y no leen configuración mutable durante una reunión.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 4 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** P: [Prompt técnico](/Users/danizal/getvocify/docs/TECHNICAL_PLANNING_PROMPT_VOCIFY_V1.md) · A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · I: [Integración de superficies](/Users/danizal/getvocify/docs/features/PLAN_INTEGRACION.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | C04 EvidenceRef; garantías de claim/retry C05 aplicadas a playbook_imports040, no a un memo falso; contexto de empresa y roles. |
| Produce | C06 PlaybookSnapshot, pasos con IDs estables y entradas respaldadas; Settings con estados por tipología. |
| Dependencias de código | [F0-F0.1](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/03-f0-f0.1-inteligencia-y-jobs.md) |
| Migración propia | 040_company_playbooks.sql |
| No le corresponde | No entrevista IA, OCR ni reconstrucción de scoring histórico. No suponer que un borrador habilita coaching. |

La posición en la cola no convierte todas las entregas anteriores en dependencias técnicas. Los contratos nombrados aquí deben existir y tener evidencia de aceptación antes de ejecutar tareas que los consuman. Una dependencia suspendida solo permite avanzar si la parte consumida ya está verificada y el coordinador lo documenta.

## Restricciones globales aplicables

- «Una feature a la vez, hasta el final, antes de pasar a la siguiente».

- Cada entrega sigue TDD y se valida contra SOLID antes de darse por cerrada — no son sugerencias de estilo, son parte del Definition of Done de cada una.

- Un subagente/sesión por entrega, sin implementación simultánea de features. Los bloqueos externos se registran y permiten preparación de trabajo independiente según §5; nunca cuentan como cierre ni permiten saltar una dependencia incumplida.

- Cada feature cubre ausencia de datos y datos parciales/ambiguos. Todo caso nuevo descubierto durante su implementación se resuelve y prueba en esa entrega, o se registra como bloqueo de producto si exige una decisión que el agente no puede tomar.

- «ICP: empresas con CRM estructurado (HubSpot o Pipedrive) con 2-way email sync nativo».

- «Email vía Gmail directo: no se construye».

- «Composio: no se usa».

- «Detección de tono/emoción real desde transcripción: fuera de scope».

- «Meeting booked ≠ close».

- «Slack/Teams: no se construye».

- «WhatsApp para notificaciones push de equipo: no se construye».

- «Onboarding de playbook: 100% self-serve manual».

- Checklist y nueva asistencia en vivo: **solo meetings**.

- No incorporar bots de reuniones, fuentes nuevas de captura, roleplay, leaderboards ni dashboards personalizables por chat.

- No introducir datos ficticios en producción.

- La UI debe mostrar primero el motivo o la acción útil; detalles, puntuaciones y configuración aparecen al ampliar o una forma de descubrirlo más.

- Todo contenido generado debe ser breve, específico y respaldado por información disponible.

- Todo componente del kernel de UI compartido (`shared/ui/`) hereda las reglas de motion y accesibilidad de [copilot-spine-design.md §2.3 y §7](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md:36): no se repiten por feature, se cumplen por construcción. La carga reserva el espacio del componente final; los cambios de altura se animan con medidas reales; `prefers-reduced-motion` elimina movimiento y conserva solo opacidad; el texto mantiene contraste ≥4.5:1 y cada control tiene foco visible. También se heredan los objetivos de interacción, regiones de estado e idioma definidos en §7. Esta restricción incluye F02, F05, F06, F09 y F12, y se verifica al integrar el kernel en cada superficie.

## Especificación funcional conservada

Este bloque conserva la especificación y los criterios aprobados para planificar. Las tareas posteriores la concretan; no eliminan estados de UI, restricciones ni decisiones pendientes. Las referencias §2–§6 que aparezcan en el bloque remiten al plan maestro. Las citas al repo hermano son auditoría; los cambios futuros del desktop se realizan en el monorepo tras F01.

## Feature: F08 — Playbooks por tipología y onboarding manual

**Fuente:** A §4.1–4.3; P §5.1.2; I §3.9.  

**Prioridad:** V1.

### En una frase

El responsable comercial puede introducir su proceso de venta y mantener una versión distinta para cada tipo de conversación.

### Por qué (first principles)

Vocify necesita saber qué considera correcta cada empresa. Sin ese marco, el coaching produciría consejos genéricos y puntuaciones sin una referencia compartida.

### Qué ya existe (auditoría)

- Settings, contexto de producto, transcripción y permisos de administración.

- Reutiliza el patrón de edición compartida de empresa.

- Gap real: configuración por tipología, importación de contenido y versiones.

### Backend

- Migración 040:

  - `interaction_types`: empresa, clave estable, nombre y estado activo.

  - `playbooks`: empresa, tipología y versión activa.

  - `playbook_versions`: texto original, texto normalizado, criterios de buena interacción, pasos, autor y fecha.

  - `playbook_entries`: categoría de objeción, guía, versión y referencia al fragmento original.

  - `playbook_imports`: origen, estado, resultado y error.

- Crear `/Users/danizal/getvocify/backend/app/services/playbooks/` para importación, versiones y lectura.

- Endpoints:

  - `GET/POST /api/v1/playbooks`.

  - `GET/PUT /api/v1/playbooks/{id}`.

  - `POST /api/v1/playbooks/imports`.

  - `GET /api/v1/playbooks/imports/{id}`.

- Texto: edición directa.

- PDF: extracción mediante `pypdf`; PDF sin texto o cifrado devuelve un error accionable. No añadir OCR en V1. [Limitación documentada](https://github.com/py-pdf/pypdf/blob/main/docs/user/extract-text.md).

- Audio: utilizar STT existente; no crear un memo comercial ni ejecutar sync CRM por explicar un playbook.

- Un meeting existente puede usarse como fuente únicamente tras selección expresa y comprobación de permisos.

- Un LLM puede proponer estructura desde el contenido aportado; el manager revisa y guarda. No entrevista al usuario ni inventa metodología.

- Publicar una versión es atómico. Los scores antiguos conservan la versión con la que se calcularon.

**SOLID:** importadores separados; tipologías como datos; consumidores reciben solo pasos o entradas de objeción que necesitan.

### Frontend / Dashboard

- Sección `Playbooks` dentro de Settings, siguiendo `SettingsLayout`.

- Módulo `/Users/danizal/getvocify/src/features/playbooks/`.

- Una lista de tipologías y un editor. Texto/PDF/audio son formas de cargar el mismo contenido.

- `usePlaybooks` y `usePlaybookImport` con TanStack Query.

- Pasos y criterios en sección ampliable; no un configurador complejo obligatorio.

- Copy: «Así vendemos en discovery».

#### Onboarding y estados de configuración — A10

En `/Users/danizal/getvocify/src/features/playbooks/components/PlaybookSetupNotice.tsx`, mostrar un aviso persistente dentro de Settings cuando no exista una versión publicada aplicable. El aviso se alimenta de `usePlaybooks`; no utiliza una bandera local que pueda decir «configurado» después de perder el borrador.

| Estado de empresa/tipología | Qué ve el usuario | Acción |
|---|---|---|
| Sin ningún playbook | «Define vuestro proceso para activar el coaching» y checklist breve: elegir tipología → aportar contenido → revisar y publicar. | Owner/admin: «Configurar playbook». Member: «Tu administrador debe configurar el proceso», sin botón de edición. |
| Borrador sin publicar | «Tienes un playbook pendiente de publicar». Conservar contenido y progreso. | «Continuar configuración» abre ese borrador. |
| Importando | Nombre del archivo y «Preparando contenido para revisión» dentro del espacio del editor. | Permitir salir y recuperar el estado mediante el ID de importación. |
| Error o contenido ambiguo | Error específico —PDF sin texto, importación fallida o pasos contradictorios— sin sustituir la versión activa. | Reintentar la importación o editar el borrador; nunca publicar por defecto. |
| Publicado para unas tipologías, no para otras | Estado por tipología: «Activo» o «Sin proceso publicado». | Configurar únicamente la tipología pendiente. No declarar listo el coaching de toda la empresa por tener un playbook cualquiera. |

El aviso desaparece para la tipología al publicar correctamente. No impide grabar, revisar ni sincronizar CRM; explica por qué scoring/checklist de esa tipología aún no están disponibles. La publicación muestra qué versión se activa y mantiene las reuniones en curso en su versión original.

### Criterio de aceptación (Definition of Done)

- [ ] Texto, PDF y audio terminan en un playbook revisable.

- [ ] Un miembro puede leer lo permitido, pero no modificarlo.

- [ ] Añadir una tipología no requiere desplegar código.

- [ ] Un error de importación no sustituye la versión activa.

- [ ] Cada entrada generada apunta a contenido aportado.

- [ ] La interfaz permite completar la configuración sin entrevista de IA.

- [ ] Una empresa nueva ve el aviso y completa tipología → contenido → revisión → publicación. Un member ve la explicación sin controles de escritura.

- [ ] Un borrador o importación parcial no oculta el aviso ni habilita coaching; publicar una tipología no marca las demás como configuradas.

### Riesgos / edge cases conocidos

Documentos sin texto, contenido contradictorio, playbook demasiado extenso y cambios de versión durante una reunión. La reunión utiliza la versión fijada al comenzar.

**Precisión C05:** las importaciones utilizan estado/lease en `playbook_imports` de 040; se reutilizan garantías de recuperación, no la identidad memo de `memo_jobs`. No crear un memo comercial para una importación.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Crear | `/Users/danizal/getvocify/backend/app/models/playbooks.py` | Contratos de versiones y entradas. |
| Crear | `/Users/danizal/getvocify/backend/app/api/playbooks.py` | CRUD, importación y publicación. |
| Crear | `/Users/danizal/getvocify/backend/app/services/playbooks/imports.py` | Adaptadores texto/PDF/audio. |
| Crear | `/Users/danizal/getvocify/backend/app/services/playbooks/versions.py` | Publicación y lectura snapshot. |
| Crear | `/Users/danizal/getvocify/backend/migrations/040_company_playbooks.sql` | Cinco tablas con aislamiento. |
| Crear | `/Users/danizal/getvocify/backend/tests/playbooks/test_versions.py` | Atomicidad y versión fijada. |
| Crear | `/Users/danizal/getvocify/backend/tests/playbooks/test_imports.py` | Fuentes y errores. |
| Crear | `/Users/danizal/getvocify/src/features/playbooks/components/PlaybookSetupNotice.tsx` | Onboarding por rol/tipología. |
| Crear | `/Users/danizal/getvocify/src/features/playbooks/components/PlaybookEditor.tsx` | Editor y publicación explícita. |
| Crear | `/Users/danizal/getvocify/src/features/playbooks/hooks/usePlaybooks.ts` | Lectura/invalidación scoped. |
| Crear | `/Users/danizal/getvocify/src/features/playbooks/hooks/usePlaybookImport.ts` | Recuperación de importación. |
| Modificar | `/Users/danizal/getvocify/src/pages/dashboard/settings/SettingsLayout.tsx` | Entrada de navegación. |
| Modificar | `/Users/danizal/getvocify/src/App.tsx` | Ruta de Settings. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F08.01 — Persistir versiones y publicar atómicamente

**Archivos:** models/playbooks.py, services/playbooks/versions.py, migration040, tests/playbooks/test_versions.py.

**Interfaz y propiedad:** C06 active_version_id apunta a snapshot inmutable. step_id conserva identidad dentro de versión y entrada guarda fuente.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"playbook_id":"pb-1","version_id":"pv-2","sales_motion_key":"discovery","steps":[{"step_id":"pain","label":"Confirmar problema","criterion":"El prospecto confirma un problema concreto"}],"entries":[]}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Publicaciones simultáneas | Una versión activa inequívoca; la anterior sigue legible. |
| Editar durante meeting | La captura conserva versión fijada al inicio. |
| Member intenta publicar | 403 y ninguna fila mutada. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/playbooks/test_versions.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Crear tablas, índices/RLS y funciones de publicación atómica; actualizar reset/schema.

- [ ] Validar contenido y tipología de empresa antes de activar; no permitir una entrada grounded sin fuente aportada.

- [ ] Añadir lectura get_published_playbook(company_id, sales_motion_key, version_id=None) en versions.py.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/playbooks/test_versions.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Snapshots y permisos comprobados en DB aislada.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F08.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F08.02 — Importar fuentes a borrador sin efectos comerciales

**Archivos:** imports.py, api/playbooks.py, tests/playbooks/test_imports.py.

**Interfaz y propiedad:** POST /playbooks/imports devuelve import_id y status; GET recupera resultado. Audio usa STT existente sin memo comercial.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"import_id":"imp-1","status":"failed","reason":"pdf_has_no_text","active_version_unchanged":true}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| PDF cifrado/sin texto | Error accionable; versión activa intacta. |
| Audio válido | Borrador editable y cero sync CRM. |
| Reintento mismo import | No publica ni duplica versiones automáticamente. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/playbooks/test_imports.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Implementar adaptadores de texto/PDF/audio y validar origen seleccionado/permisos del memo si se reutiliza una grabación.

- [ ] Guardar texto original, propuesta normalizada y vínculos de fuente; mostrar contradicciones para revisión.

- [ ] Usar job recuperable y exponer estado/error sin inventar contenido al fallar importación.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/playbooks/test_imports.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Tres formatos terminan en borrador; nunca en publicación implícita.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F08.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F08.03 — Entregar Settings con onboarding, edición y publicación

**Archivos:** src/features/playbooks/; SettingsLayout.tsx; App.tsx; api/router.py.

**Interfaz y propiedad:** C06 + estados U/A10. React Query separa empresa/tipología; éxito publish invalida lista y detalle.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
sin playbook -> borrador -> revisión -> publicación -> activo
importación fallida -> borrador conservado / activo anterior conservado
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Empresa nueva member/admin | Mensaje dependiente del rol; admin puede iniciar y member no editar. |
| Borrador/importando | No desaparece aviso de proceso sin publicar. |
| Publicar discovery | No habilita otras tipologías. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `npm run build` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Construir lista/editor y aviso de configuración con pasos elegir/aportar/revisar/publicar.

- [ ] Conectar polling de import y recuperación al reabrir; conservar borrador ante errores.

- [ ] Registrar intención y verificar flujo texto, un error PDF y permisos por ruta/API.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `npm run build` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reticle prueba publicación real de fixture y cambio del estado visible; backend valida permisos.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F08.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Owner crea tipología, pega proceso, revisa pasos/entradas y publica; otro usuario member puede leer sin editar. Una importación fallida no borra versión activa. Abrir captura, publicar otra versión y demostrar que conserva snapshot.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/playbooks -q`
- `npm run build`
- `make test-js`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F08` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F08/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F09/F12 reciben get_published_playbook y snapshot inmutable. F0 puede enriquecer playbook_observations cuando el snapshot esté disponible; ausencia sigue representada sin error de pipeline.
