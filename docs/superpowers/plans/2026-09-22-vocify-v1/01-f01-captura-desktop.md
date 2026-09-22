# F01 — Cierre de captura con desktop: plan ejecutable

> **Ejecución futura:** usar `executing-plans` dentro del subagente dedicado a esta entrega; la coordinación secuencial usa `subagent-driven-development`. Este documento es planificación, no una implementación ni una autorización para desplegar. Ninguna casilla de ejecución está completada.

**Objetivo:** Entregar captura desktop recuperable, transcripción continua y un paquete macOS verificable.

**Arquitectura:** El proceso principal conserva audio; el renderer muestra estado. El backend adapta la captura al pipeline actual. El kernel de UI pertenece al monorepo y se distribuye a los hosts.

**Stack:** FastAPI/Python, Supabase/PostgreSQL, React 18/TypeScript y módulos JS compartidos; Electron/extensión cuando figuren entre las superficies de esta entrega.

**Posición:** 1 de 16. **Estado:** planificada; no iniciada.

**Navegación:** [plan maestro](/Users/danizal/getvocify/proposed_plan.md) · [contratos](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md) · [integración y gates](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-22-vocify-v1/00-integration-and-gates.md)

**Fuentes de esta entrega:** A: [Análisis de producto](/Users/danizal/getvocify/docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md) · S: [Diseño Spine](/Users/danizal/getvocify/docs/superpowers/specs/2026-09-21-copilot-spine-design.md) · PF: [Plan previo de fundamentos/follow-up](/Users/danizal/getvocify/docs/superpowers/plans/2026-09-21-copilot-spine-foundation-and-followup.md) · D: [Estructura inteligente](/Users/danizal/getvocify/docs/features/ESTRUCTURA_INTELIGENTE.md).

## Entrada, salida y frontera de responsabilidad

| Tipo | Contrato de esta entrega |
|---|---|
| Recibe | API de auth; start_extraction_from_transcript; reloj/canales desktop; PF tareas 1–3 y 5. |
| Produce | C01 CaptureContext, evidencia temporal, memo idempotente; C02 kernel/transcript; artefacto distribuible condicionado a Developer ID. |
| Dependencias de código | Código auditado y diseños existentes; ninguna entrega V1 previa. |
| Migración propia | 037_memo_capture_context.sql |
| No le corresponde | No generar scoring, notas de coaching, playbooks ni una segunda entidad Interaction. Firma/publicación no autorizadas hasta resolver §6. |

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

## Feature: F01 — Cierre de captura con desktop

**Fuente:** A §2; D §5; PF tarea 1.  

**Prioridad:** V1.

### En una frase

Una reunión grabada desde el desktop llega a Vocify con su contexto intacto y puede revisarse después, incluyendo el audio cuando se ha capturado.

### Por qué (first principles)

Meetings y llamadas deben alimentar el mismo producto. Si se pierde el tipo de interacción, el audio o el contexto temporal, las funciones posteriores parten de información incompleta.

### Qué ya existe (auditoría)

- Reutiliza captura nativa, permisos, canales y revisión del repositorio hermano.

- Reutiliza `start_extraction_from_transcript`, transcripción batch y reproducción mediante URL firmada.

- Patrón: captura en Electron; interpretación en backend.

- Gap real: importación segura, persistencia de origen, recuperación y audio reproducible.

- [renderTranscript()](/Users/danizal/getvocify-desktop/renderer/app.js:220) concatena `finalTranscript` e `interimTranscript`, reconstruye el contenedor y fuerza el scroll al final en cada actualización. El código no reconcilia visualmente provisional/definitivo; el tamaño de los fragmentos también depende del proveedor. La mejora requerida es continuidad visual sin alterar el texto reconocido.

- [package.json](/Users/danizal/getvocify-desktop/package.json) ya incluye `electron-builder`, `npm run dist:mac`, targets `dmg` y `zip`, nombre «Vocify Companion» e iconos. Tiene `identity: null`, `hardenedRuntime: false`, sin fondo ni posición de iconos del DMG. El [workflow dmg.yml](/Users/danizal/getvocify-desktop/.github/workflows/dmg.yml) desactiva el descubrimiento de firma y sube artifacts de CI; eso no constituye una distribución pública firmada.

- El enlace «Vocify Companion» de [RecordPage.tsx](/Users/danizal/getvocify/src/pages/dashboard/RecordPage.tsx:26) abre el repositorio GitHub. En las rutas web inspeccionadas no se encontró un enlace directo a un DMG. Esto resuelve la duda sobre ese enlace concreto; no demuestra que no exista un canal externo de distribución.

### Backend

- Aplicar la migración 037.

- Persistir `source_type` también en `/memos/upload-and-extract` y en el helper común.

- Añadir un adaptador de captura en `/Users/danizal/getvocify/backend/app/api/captures.py`:

  - `POST /api/v1/captures`: recibe `client_capture_id`, inicio y tipo; devuelve el mismo `memo_id` al repetir la petición.

  - `PUT /api/v1/captures/{id}/audio`: adjunta la grabación al almacenamiento privado.

  - `POST /api/v1/captures/{id}/complete`: recibe transcripción, duración y metadatos; activa el pipeline existente.

- Limitar audio a 512 MiB, validar formato y procesar la carga desde archivo temporal, evitando mantener grabaciones completas duplicadas en memoria.

- Conservar audio PCM/WAV con los dos canales cuando estén disponibles. Mantener offsets sobre un mismo reloj de captura.

- Si la transcripción en vivo quedó incompleta, transcribir el audio conservado antes de extraer. No mezclar silenciosamente un fragmento parcial con un resultado completo.

- Ampliar la reproducción/retranscripción para el origen desktop.

- Una petición repetida devuelve el memo existente; no genera otra extracción ni otro audio lógico.

**SOLID:** el nuevo router adapta la captura al pipeline; no contiene extracción, scoring ni reglas de negocio.

### Frontend / Dashboard

- Ejecutar PF tarea 1 para integrar el desktop. Antes de importar, incorporar expresamente los cambios locales del repo hermano y excluir el clon anidado; nunca usar un añadido indiscriminado de archivos.

- El proceso principal conserva temporalmente audio y metadatos hasta recibir confirmación de subida.

- El renderer muestra `Grabando`, `Pendiente de subir`, `Procesando` o el error concreto.

- Reutilizar la revisión actual; no crear otra pantalla de aprobación.

- Copy de fallo: «La grabación está guardada en este equipo. Reintentar subida».

- No prometer «seguimos grabando en local» hasta haber verificado esa persistencia.

#### Transcripción continua — A1

**Archivos previstos:** crear `/Users/danizal/getvocify/shared/ui/transcript.js` para reconciliación pura, `/Users/danizal/getvocify/shared/ui/transcript.test.js`, `/Users/danizal/getvocify/shared/ui/components/transcript.js` y `/Users/danizal/getvocify/shared/ui/components/v-transcript.js`; ampliar `/Users/danizal/getvocify/shared/ui/vocify-ui.css`. Integrar en `/Users/danizal/getvocify/desktop/renderer/app.js` e `index.html` una vez importado el desktop. Los tokens, base del elemento y copia del kernel siguen PF, según §4.

- `<v-transcript>` recibe la revisión, turnos definitivos y fragmento provisional con identidad de turno/canal. El adaptador conserva el reloj y los datos de captura; el componente solo decide presentación. No suavizar el texto que llega a extracción ni retrasar su persistencia.
- Mantener los nodos del texto ya confirmado. Al llegar un definitivo, reconciliarlo con su provisional: reutilizar el prefijo que coincide, corregir solo el tramo modificado y retirar cualquier duplicado. No vaciar `innerHTML` ni reconstruir todos los turnos en cada evento.
- Mostrar los fragmentos nuevos con aparición gradual mediante opacidad y la duración de S §7; no simular escritura carácter a carácter ni acumular una cola de animaciones que retrase lo reconocido. Al confirmar texto idéntico, cambiar su estado sin hacerlo desaparecer y aparecer de nuevo.
- Con provisional revisado, reconocer sustituciones de palabras, puntuación y cambios de hablante. Un evento vacío o repetido no borra texto definitivo; al parar se espera la finalización del proveedor o se marca el fragmento restante como provisional/incompleto, nunca se certifica como definitivo por una animación.
- Reservar la altura del área de transcripción. Seguir el final solo si el usuario ya estaba al final; si sube para leer, mantener su posición y ofrecer «Volver al directo». Mantener rótulos de hablante estables y aplicar reducción de movimiento del kernel.
- Sin voz todavía: «Escuchando. La transcripción aparecerá aquí». Si no llega audio de sistema, mostrar esa limitación por separado; un contenedor vacío no demuestra que se esté capturando correctamente.

#### Distribución macOS — A2

La distribución forma parte de F01 y tiene criterios propios dentro de la misma entrega. No se añade un sistema de actualización automática en V1.

| Trabajo | Resultado concreto | Dependencia |
|---|---|---|
| Empaquetado reproducible | DMG y ZIP versionados generados por el script existente; registrar arquitectura y macOS efectivamente probados, sin anunciar soporte no verificado. Incluir el helper nativo de captura y los módulos compartidos. | Se puede preparar con la infraestructura actual. |
| Instalador con marca | Fondo con logo existente, nombre legible, icono de Vocify a la izquierda, destino Applications a la derecha e indicación «Arrastra Vocify a Aplicaciones». Ventana y posiciones fijas; el texto forma parte del fondo y no tapa iconos. | Reutilizar assets existentes y configurar `dmg.background`/`contents` en el package del desktop. |
| Firma y notarización | App y binarios auxiliares firmados, hardened runtime y entitlements necesarios, paquete notarizado y ticket adjunto donde corresponda; validación de firma y apertura en un Mac de prueba. | **Pendiente de Dani:** confirmar cuenta Apple Developer, acceso a Developer ID y quién administra las credenciales. No asumir cuenta, comprarla ni convertir su alta en una tarea técnica autorizada. |
| Enlace de descarga | Enlace a un artefacto aprobado, con versión, arquitectura y requisitos comprobados; comprobar descarga → instalación → login → permisos → primera captura. | **Pendiente de Dani:** dashboard, landing o ambos; alojamiento del artefacto y acceso público o autenticado. Propuesta: dashboard primero, reemplazando el enlace al repo en RecordPage; landing solo si se aprueba. |

**Archivos de puesta a punto:** `/Users/danizal/getvocify/desktop/package.json`, `/Users/danizal/getvocify/desktop/build/dmg-background.png` y `/Users/danizal/getvocify/.github/workflows/desktop-dmg.yml` tras la importación. Cuando se confirme Developer ID, añadir `/Users/danizal/getvocify/desktop/build/entitlements.mac.plist` y la configuración de notarización necesaria, usando secretos del entorno de build; no guardar credenciales en el repo. El enlace autorizado se implementa en `/Users/danizal/getvocify/src/pages/dashboard/RecordPage.tsx`; cualquier ubicación adicional se registra tras decidirla.

Antes de activar hardened runtime se prueban Electron, acceso a micrófono/sistema y el helper `vocify-tap` dentro del paquete firmado. Un `.app` que abre pero pierde captura no cumple la entrega. Una firma o notarización fallida impide publicar ese artefacto como versión de distribución; el build local puede conservarse claramente identificado para pruebas internas.

La ausencia actual de firma implica que no está listo para el flujo de distribución confiable de Gatekeeper. No se promete que todos los equipos mostrarán literalmente «app dañada»: el mensaje depende del paquete y del sistema. El requisito verificable es que el paquete descargado pase firma/notarización y la prueba de instalación. Referencias oficiales: [Developer ID y notarización de Apple](https://developer.apple.com/developer-id/) y [configuración DMG de electron-builder](https://www.electron.build/dmg/).

Si las decisiones de distribución siguen pendientes, terminar captura, transcripción, marca y empaquetado verificables, registrar la parte bloqueada y seguir el protocolo B2. F01 no se declara distribuible ni completamente cerrada mientras esos criterios sigan pendientes.

### Criterio de aceptación (Definition of Done)

- [x] Reunión → memo → revisión → aprobación CRM utiliza el pipeline actual. `cd backend && .venv/bin/python -m pytest tests/captures/test_lifecycle.py::test_meeting_capture_complete_uses_existing_pipeline_to_review -q && cd desktop && node --test lib/meeting-handoff.test.js`

- [x] Repetir la subida produce el mismo memo. `cd backend && .venv/bin/python -m pytest tests/captures/test_lifecycle.py::test_complete_same_content_is_idempotent -q`

- [x] Reiniciar la aplicación recupera una captura pendiente. `cd desktop && node --test lib/capture-store.test.js --test-name-pattern 'restart recovers'`

- [x] Un corte del WebSocket no destruye el audio conservado. `cd desktop && node --test lib/capture-store.test.js --test-name-pattern 'transcription would disconnect'`

- [x] La reextracción reconoce el memo como meeting. `cd backend && .venv/bin/python -m pytest tests/captures/test_lifecycle.py::test_meeting_source_type_is_preserved_for_re_extraction -q`

- [x] Los tiempos permiten localizar un fragmento real. `cd backend && .venv/bin/python -m pytest tests/captures/test_audio.py::test_extract_words_keeps_offsets_in_milliseconds tests/captures/test_audio.py::test_partial_transcript_with_complete_audio_does_not_start_extraction tests/intelligence/test_annotations.py::test_put_replay_is_the_same_note_and_a_stale_revision_conflicts -q`

- [ ] Se verifica el flujo en desktop y la revisión correspondiente en web.

- [x] Provisional «Quedamos el mar» → definitivo «Quedamos el martes» aparece una sola vez, conserva hablante y no parpadea. Una corrección dentro del provisional reemplaza únicamente el tramo afectado. `node --test shared/ui/transcript.test.js`

- [x] Eventos repetidos, cambio de hablante y finalización sin último definitivo no duplican ni certifican texto provisional. Una sesión larga conserva scroll voluntario y no reconstruye todo el historial al actualizar. `node --test shared/ui/transcript.test.js`

- [ ] `<v-transcript>` cumple la continuidad visual y `prefers-reduced-motion` en el desktop real, además de sus pruebas de reconciliación.

- [ ] DMG con marca y ZIP incluyen los recursos compartidos y el helper. La instalación desde el artefacto descargado permite login, permisos, captura micrófono/sistema, revisión y retorno al dashboard.

- [ ] Tras confirmar Developer ID, firma y notarización se validan sobre el artefacto distribuible y se registra la evidencia de Gatekeeper; hasta entonces este criterio permanece bloqueado, no aprobado.

- [ ] La ubicación de descarga aprobada lleva al artefacto correcto; ni un enlace al repo ni un artifact privado de CI cuentan como ese entregable.

### Riesgos / edge cases conocidos

Permisos denegados, ausencia de audio de sistema, desconexión, disco lleno y grabación incompleta. La distinción micrófono/sistema no se presenta como identificación individual de todos los participantes.

**Precisión de integración:** el workflow importado tendrá nombre `desktop-dmg.yml` en el monorepo, siguiendo el prefijo previsto en PF; se sustituye la referencia anterior a `dmg.yml` y se mantiene un único workflow.

## Mapa de archivos y responsabilidades

| Acción futura | Ruta | Responsabilidad |
|---|---|
| Modificar | `/Users/danizal/getvocify/backend/app/api/memos.py` | Persistir origen y reutilizar pipeline. |
| Crear | `/Users/danizal/getvocify/backend/app/api/captures.py` | Tres endpoints de captura. |
| Crear | `/Users/danizal/getvocify/backend/app/services/captures.py` | Identidad, finalización y recuperación de captura. |
| Crear | `/Users/danizal/getvocify/backend/tests/captures/test_lifecycle.py` | Contrato y concurrencia de captura. |
| Modificar | `/Users/danizal/getvocify/backend/app/api/transcription.py` | Conservar tiempos y canal. |
| Modificar | `/Users/danizal/getvocify/backend/app/services/memo_playback.py` | Reproducción del audio desktop. |
| Crear | `/Users/danizal/getvocify/backend/migrations/037_memo_capture_context.sql` | Contexto de captura, unicidad e índices. |
| Modificar | `/Users/danizal/getvocify/backend/full_reset.sql` | Esquema equivalente de reset. |
| Crear | `/Users/danizal/getvocify/shared/ui/transcript.js` | Reconciliación visual pura. |
| Crear | `/Users/danizal/getvocify/shared/ui/transcript.test.js` | Provisional/final y revisiones. |
| Crear | `/Users/danizal/getvocify/shared/ui/components/v-transcript.js` | Elemento fino sobre renderer puro. |
| Modificar después de importar | `/Users/danizal/getvocify/desktop/renderer/app.js` | Conectar captura y v-transcript. |
| Crear/importar | `/Users/danizal/getvocify/desktop/electron-main.mjs` | Persistencia local y permisos existentes. |
| Crear/importar | `/Users/danizal/getvocify/desktop/package.json` | DMG/ZIP y firma condicionada. |
| Crear tras importar | `/Users/danizal/getvocify/.github/workflows/desktop-dmg.yml` | Workflow único desde desktop/. |
| Modificar | `/Users/danizal/getvocify/src/pages/dashboard/RecordPage.tsx` | Enlace de descarga solo tras decisión. |

Los archivos marcados «Crear» todavía no existen por esta planificación. Los marcados «Modificar» pueden ser producidos por una dependencia; su procedencia debe quedar indicada. Los tests y fixtures se crean en ejecución, nunca se confunden con datos de producción.

## Tareas secuenciales con ciclo TDD

Cada tarea termina con evidencia revisable. Los ejemplos de contrato y prueba fijan entradas/salidas futuras; no se han ejecutado ahora. Dividir los pasos de implementación en cambios pequeños dentro del mismo ciclo rojo → verde → revisión. No iniciar otra feature para esquivar un fallo.

### F01.01 — Importar desktop y adelantar el kernel necesario

**Archivos:** desktop/, README.md, scripts/build-tokens.mjs, scripts/sync-shared.mjs, shared/ui/; tests de PF 2/3/5.

**Interfaz y propiedad:** C02; aplicar PF 1–3 y solo distribución de módulos presentes de PF 5. El workflow canónico se llama .github/workflows/desktop-dmg.yml.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
shared/ui/ -> chrome-extension/shared/
shared/ui/ -> desktop/renderer/shared/
shared/tokens/tokens.json -> CSS por superficie
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Trabajo local en repo hermano | Inventario y respaldo verificables; ningún archivo local queda fuera del traslado sin razón. |
| Sync dos veces y --check | Segunda copia no cambia archivos; un derivado editado hace fallar --check. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test scripts/build-tokens.test.mjs scripts/sync-shared.test.mjs shared/ui/ui.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Registrar HEAD y cambios locales de ambos repos sin sobrescribirlos; importar según PF preservando historial y excluyendo clon anidado.

- [ ] Construir tokens y base light-DOM de PF, posponiendo compose/followup cuando no sean necesarios para transcript. Crear renderer de transcript antes de distribuirlo.

- [ ] Adaptar workflow al directorio desktop; generar las copias desde shared/, nunca editarlas. Documentar la ruta nueva y retirar ejecución duplicada del workflow importado.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test scripts/build-tokens.test.mjs scripts/sync-shared.test.mjs shared/ui/ui.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Un origen de UI y un desktop editable; inventario del traslado y checks de generación.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F01.01`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F01.02 — Fijar identidad y persistencia idempotente de captura

**Archivos:** backend/app/api/captures.py, services/captures.py, migrations/037_memo_capture_context.sql, tests/captures/test_lifecycle.py; api/router.py.

**Interfaz y propiedad:** C01: client_capture_id se asigna en cliente; capture_id es el ID estable del memo reservado por servidor. La identidad de empresa/autor se deriva de sesión.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"request":{"client_capture_id":"cap-local-1","started_at":"2026-09-22T08:00:00Z","interaction_kind":"meeting"},"response":{"capture_id":"memo-1","memo_id":"memo-1","status":"recording"}}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Dos POST simultáneos mismo autor/client_capture_id | Un memo, mismo capture_id/memo_id; misma extracción lógica. |
| Mismo ID de cliente con otro autor | Ámbitos distintos; nunca devuelve el memo ajeno. |
| complete repetido o contenido distinto | Misma revisión es idempotente; contenido incompatible exige revisión explícita, no sobrescribe en silencio. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/captures/test_lifecycle.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Crear restricciones de unicidad y contexto original con migración aditiva; añadir RLS y validación de ámbito en servicio.

- [ ] Insertar o recuperar el memo reservado de forma atómica; devolver identidad única sin crear tabla Interaction.

- [ ] Persistir source_type en caminos nuevos y existentes; registrar router en api/router.py. Sincronizar full_reset.sql y docs/DATABASE_SCHEMA.md.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/captures/test_lifecycle.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Prueba con dos transacciones y lectura entre empresas rechazada.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F01.02`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F01.03 — Conservar audio, tiempo y recuperación sin duplicar memoria

**Archivos:** desktop/lib/capture-store.js y .test.js nuevos; desktop/electron-main.mjs; backend/app/api/captures.py; tests/captures/test_audio.py nuevos.

**Interfaz y propiedad:** PUT /captures/{id}/audio almacena privado; complete referencia audio/turnos en el mismo reloj. Límite 512 MiB.

**Ejemplo concreto de contrato o prueba a incorporar:**

```json
{"capture_id":"memo-1","audio_status":"partial","transcript_complete":false,"turns":[{"id":"turn-1","speaker_role":"rep","start_ms":0,"end_ms":1250,"text":"Buenos días"}]}
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Cierre antes de subir | Manifiesto y audio recuperados al iniciar; no se borra antes de confirmación remota. |
| Disco lleno o un canal ausente | Error explícito y audio válido previo conservado; no declarar dos canales completos. |
| WS cortado con audio completo | STT batch precede extracción; no mezclar texto parcial como completo. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd backend && .venv/bin/python -m pytest tests/captures/test_audio.py tests/test_memo_playback.py -q` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Persistir manifiesto local por captura con estado y rutas, y escribir audio incremental sin concatenar la reunión entera en memoria.

- [ ] Validar formato/tamaño en API antes de almacenar; limpiar temporales al fallar, conservar fuente local para retry.

- [ ] Propagar tiempos de palabras/turnos desde transcription.py; unir finalización y pipeline solo una vez. Confirmar subida antes de limpiar captura local.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd backend && .venv/bin/python -m pytest tests/captures/test_audio.py tests/test_memo_playback.py -q` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Reinicio real de Electron recupera captura y reproducción localiza el fragmento esperado.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F01.03`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F01.04 — Reconciliar la transcripción sin parpadeo

**Archivos:** shared/ui/transcript.js, transcript.test.js, components/transcript.js, components/v-transcript.js y vocify-ui.css; desktop/renderer/app.js.

**Interfaz y propiedad:** reconcileTranscript(previous, incoming) devuelve el estado de presentación. incoming tiene revision, turns y interim; no modifica los datos persistidos.

**Ejemplo concreto de contrato o prueba a incorporar:**

```js
import assert from 'node:assert/strict';
import { reconcileTranscript } from './transcript.js';
const before = { revision: 1, turns: [], interim: { id: 't1', text: 'Quedamos el mar' } };
const incoming = { revision: 2, turns: [{ id: 't1', text: 'Quedamos el martes' }], interim: null };
assert.deepEqual(reconcileTranscript(before, incoming), incoming);
assert.deepEqual(reconcileTranscript(incoming, before), incoming);
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Interim mar -> definitivo martes | Un turno, texto final martes, interim eliminado; identidad DOM estable. |
| Revisión antigua después de nueva | Se conserva la revisión nueva. |
| Usuario leyendo arriba | No se fuerza scroll; aparece Volver al directo. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `node --test shared/ui/transcript.test.js` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Escribir reconciliador puro por id/revisión con sustitución del tramo provisional; nunca concatenar el provisional confirmado por duplicado.

- [ ] Implementar componente fino que mantiene nodos definitivos, opacidad de nuevos fragmentos y altura reservada; respetar reduced-motion.

- [ ] Sustituir renderTranscript directo y conectar follow-scroll condicionado; conservar You/Them y Stop.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `node --test shared/ui/transcript.test.js` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Pruebas puras y recorrido real con corrección del provisional, texto largo y scroll manual.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F01.04`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

### F01.05 — Preparar el instalador y verificar el recorrido descargable

**Archivos:** desktop/package.json, build/dmg-background.png, workflow desktop-dmg.yml; RecordPage.tsx solo al decidir enlace.

**Interfaz y propiedad:** DMG/ZIP con arquitectura y versión comprobadas. Developer ID y descarga son bloqueos de negocio documentados, no asumidos.

**Ejemplo concreto de contrato o prueba a incorporar:**

```text
Descarga -> DMG -> Applications -> primer inicio -> login
-> permisos -> captura -> stop -> subida -> revisión -> CRM
```

**Casos que deben fallar antes de implementar:**

| Caso / preparación | Resultado exigido |
|---|---|
| Paquete instalado en Mac de prueba | Login, permisos, mic/sistema, overlay, stop y subida funcionan fuera del árbol fuente. |
| Firma ausente/fallida | No se publica como distribución firmada. |
| Artefacto sin helper/shared | Falla gate aunque electron-builder termine con exit 0. |

- [ ] Escribir estos casos en los archivos de prueba indicados; para persistencia/concurrencia usar también PostgreSQL aislado y transacciones reales, no demostrar atomicidad con un mock en memoria.

- [ ] Ejecutar `cd desktop && npm test && npm run dist:mac` y confirmar fallo por la capacidad ausente; si falla por entorno, arreglar el entorno antes de atribuirlo a la feature.

- [ ] Configurar fondo e iconos del DMG con marca existente, preservando script de empaquetado.

- [ ] Registrar opciones de Developer ID y hosting en informe; avanzar build interno sin inventar aprobaciones. Tras respuesta, configurar secretos, firma de helpers, hardened runtime y notarización.

- [ ] Verificar checksum/versión del artefacto descargado y que el enlace aprobado entrega ese paquete. No ejecutar compra, publicación ni distribución durante planificación.

- [ ] Resolver los edge cases nuevos encontrados con su prueba; si requieren decisión humana, aplicar el protocolo de bloqueos del plan maestro y conservar el criterio pendiente.

- [ ] Repetir `cd desktop && npm test && npm run dist:mac` después de implementar; comprobar que el resultado esperado se cumple y ejecutar regresiones del módulo modificado.

- [ ] Revisar y registrar la evidencia de cierre: Informe separa captura verificada de distribución pendiente; F01 no completa si falta gate autorizado.

- [ ] Preparar un commit revisable de esta tarea dentro de la entrega, con archivos explícitos y referencia `F01.05`; documentar en el mismo commit/PR decisiones, pruebas y limitaciones.

## Verificación integrada y criterios de salida adicionales

Grabar una reunión de prueba autorizada con dos canales; interrumpir red, reiniciar y recuperar. Completar subida una vez, abrir memo, escuchar un fragmento por su offset y aprobar una operación CRM de prueba. Verificar continuidad del transcript y el paquete instalado por separado. Registrar autorización de distribución pendiente sin bloquear las comprobaciones independientes.

### Regresiones y comandos al cerrar

- `cd backend && .venv/bin/python -m pytest tests/captures tests/test_memo_playback.py -q`
- `node --test shared/ui/*.test.js`
- `make test-js`
- `npm run build`
- `make check-generated`

Ejecutar los comandos desde `/Users/danizal/getvocify`, salvo el `cd` explícito. Un directorio de pruebas indicado como nuevo solo estará disponible después de sus tareas; que hoy no exista no autoriza a omitirlo al ejecutar. Las pruebas de IA usan datos reales autorizados y anonimizados; los ejemplos sintéticos de este plan sirven solo para contratos y tests deterministas.

### Qué vuelve al coordinador

- [ ] Informe de `F01` con tarea/criterio → resultado → prueba o veredicto → commit, migración aplicada y contrato entregado.

- [ ] Comparación de interfaces producidas con `00-contracts.md`; ninguna divergencia silenciosa de campos, estados, permisos o semántica de `null`.

- [ ] Revisión SOLID y limpieza de listeners/jobs/efectos; los servicios no duplican interpretación que corresponde a extracción.

- [ ] Evidencia de todos los estados de UI especificados. En web, `reticle_act_and_wait` o `reticle_assert` con consecuencia explícita; en desktop/extensión, además el recorrido nativo. `unknown` y `no-fault` no cierran.

- [ ] Bloqueos y edge cases nuevos en `docs/superpowers/deliveries/F01/report.md` y en el commit/PR. No marcar completa mientras haya criterios pendientes; una suspensión debe nombrar las dependencias no afectadas.

## Handoff a la siguiente entrega

F02 recibe kernel, build/sync y captura que conserva identidad/tiempos. F0 recibe memo con empresa original y revisión. Si solo la distribución externa está suspendida, registrar exactamente qué contratos ya pasaron antes de habilitar F02.
