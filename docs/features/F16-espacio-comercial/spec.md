# Spec · F16 — Espacio del comercial («la casa del comercial»)

> Plan Lista 2 · entrega E10. Estado: **diseño aprobado (26 sep 2026), en construcción**.
> Diseño y wireframes: [`design.md`](./design.md). Maqueta: [`mock.html`](./mock.html).

## 1. Job to be done

«Cuando empiezo el día o acabo de colgar, el comercial quiere ver en una sola pantalla qué le toca, por qué y con qué preparación, y hacerlo ahí mismo (llamar, confirmar, enviar el follow-up) para pasar el día vendiendo y no dejar nada pendiente en silencio.»

Hasta ahora el comercial apenas abría Vocify (`docs/EXPERIENCIA_PRODUCTO.md`). A partir de F16 pasa tiempo dentro: Vocify es donde organiza su día. Sigue sin haber analítica para él.

## 2. Audiencia y mensaje

- [x] Rep («solo vendes»). El owner/admin que también vende usa la misma casa para su propio día; su vista de equipo sigue en **Equipo** (F15/E8), aparte.
- Frase: «Abre Vocify y tu día ya está preparado: a quién llamar, por qué y qué decir.»

## 3. Métrica de calidad (decide el GA)

Métricas internas. Ninguna se enseña al comercial.

| Métrica | Umbral GA | Cómo se mide |
|---|---|---|
| Acciones de Hoy resueltas desde la casa sin cambiar de pantalla | ≥ 70 % | `POST /today/{id}/resolve` con `surface=home` / total de resoluciones |
| Apertura → primera acción | mediana ≤ 60 s | primer resolve o llamada tras cargar `/dashboard` |
| Follow-ups listos enviados el mismo día | ≥ 60 % | `followup.sent_at − generated_at < 24 h` |
| Confirmaciones pendientes con más de 24 h | ≤ 10 % | antigüedad de las señales de confirmación (E7) |
| Días activos por comercial y semana | ≥ 4 | sesiones con al menos una acción |

## 4. Alcance

**Sí (v1):**
1. Nueva home del comercial en `/dashboard` con cinco secciones: Reuniones de hoy, Falta tu OK, A quién llamar, Próximas y Hecho hoy.
2. Panel de contacto sin salir de la home: preparación (brief), conversaciones recientes, follow-up pendiente y una acción principal. Fijo a la derecha desde 1280 px; en `Sheet` por debajo.
3. Dialer integrado en el panel (la misma instancia de `DashboardDialer`), con el brief visible durante la llamada y un estado «Después de la llamada».
4. Navegación del comercial más corta y sin la tarjeta de planes para miembros.
5. Teclado de la cola F06, más ↑/↓ (y j/k) para moverse por la lista.
6. Todos los estados: primera vez, vacío, parcial, carga, error y mucho volumen.
7. Copy nuevo en ES y EN en `src/lib/product-catalog.ts`.
8. Tres lecturas nuevas en backend: follow-ups listos, próximas tareas y hecho hoy (sección 7).

**No (v1), recorte explícito:**
- El contenido nuevo de E3 (brief v2), E4 (llamada en frío), E5 (reuniones) y E7 (confirmaciones). F16 deja el hueco; cada entrega lo llena detrás de su flag.
- Editar campos del CRM desde la home. La revisión completa sigue en `MemoDetail`.
- Paneles, gráficos, rachas, comparativas o rankings para el comercial.
- Hoy dentro del popup de la extensión (el popup no pinta la lista hoy y no cambia).
- Calendario o agenda semanal, filtros, búsqueda o reordenación manual de Hoy.
- Layout móvil (< 768 px): se mantiene el actual.
- Vista de equipo (E8).

## 5. Feature flag

- `REP_WORKSPACE_ENABLED`, por empresa, con el patrón existente `feature_flags.is_enabled(supabase, company_id, flag)` (`backend/app/services/feature_flags.py`) y valor global `False` en `backend/app/config.py`.
- Hoy no hay flags expuestos al frontend. Se expone como capacidad de empresa, igual que `can_use_dialer` (`backend/app/services/company.py`, `backend/app/api/auth.py`, `backend/app/api/company.py` → `src/features/company/types.ts`, `src/features/company/api.ts`): `rep_workspace_enabled` → `company.repWorkspace`.
- **Flag apagado:** `/dashboard` sigue exactamente como hoy (`DashboardHome` = `TodayPanel` + `ActivityPanel`, navegación actual).
- **Rollout:** founders → 3 design partners → betas. **Rollback:** apagar el flag; no hay migración de datos.

## 6. Comportamiento

### Flujo principal (un día)

1. **8:30.** Abre `/dashboard`. Ve la fecha, una línea de pulso y, por este orden: Reuniones de hoy, Falta tu OK, A quién llamar (la primera tarjeta ya seleccionada), Próximas y Hecho hoy plegado. El panel de la derecha ya muestra la preparación de la primera llamada.
2. **Falta tu OK.** Confirma la etapa de ayer (Confirmar, con 5 s para deshacer). Abre un follow-up listo: el panel muestra el borrador y lo envía.
3. **Llama.** `Enter` (o «Llamar a Marina») marca con el dialer existente. El brief sigue visible y la barra de llamada ocupa el pie del panel. La tarjeta seleccionada muestra «En llamada · 03:12».
4. **Cuelga.** El panel pasa a «Después de la llamada»: estado del CRM (guardado o «Revisar y guardar»), la confirmación de E7 si la hay y el follow-up redactándose. `n` pasa a la siguiente tarjeta.
5. **Sin respuesta / buzón.** La selección avanza sola (reductor F06). La tarjeta se queda en Hoy con la nota «Sin respuesta · 10:14».
6. **11:30, reunión.** La fila muestra «Falta del playbook: decisor, presupuesto» (E5). Tras la reunión, desktop la captura y la conversación aparece en Falta tu OK o en Hecho hoy.
7. **Tarde.** Hecho hoy crece; Próximas enseña lo de mañana con el marcador «En el CRM» (E2).
8. **Viernes.** El informe semanal llega a la campana (F13), sin comparativas.

### Criterios de aceptación

1. **Flag apagado:** `/dashboard` y la navegación son idénticos a los actuales (test de render).
2. **Flag encendido:** las secciones salen en el orden Reuniones de hoy → Falta tu OK → A quién llamar → Próximas → Hecho hoy. Una sección vacía no se pinta (ni su título).
3. **Máximo 7 tarjetas de Hoy** entre reuniones, confirmaciones y llamadas. El resto sale como una línea «N más cuando termines estos». Tres confirmaciones o más se agrupan en una sola fila.
4. **Selección inicial:** desde 1280 px, al cargar queda seleccionada la primera tarjeta de A quién llamar y su panel abierto. Por debajo de 1280 px no hay panel hasta que el comercial selecciona algo; entonces se abre en `Sheet`.
5. **Panel:** muestra el brief de `/briefs` (máx. 3 líneas + etiqueta si viene), las 3 últimas conversaciones, el follow-up pendiente si lo hay y una sola acción principal.
6. **Llamada:** `Enter` llama al contacto seleccionado usando la instancia de dialer ya montada en `DashboardLayout`. No se crea un segundo dialer y la llamada no se corta al cambiar de sección ni de ruta.
7. **Después de la llamada:** con conversación, el panel muestra el estado del CRM, la confirmación (E7) si aplica y el follow-up; `n` selecciona la siguiente. Con buzón o sin respuesta, la selección avanza y la tarjeta se queda.
8. **Teclado:** `Enter`, `s`, `n` y `Esc` conservan su significado de F06 (`shared/ui/queue.js`, `QUEUE_KEYS`). ↑/↓ y j/k mueven la selección. Ningún atajo se dispara dentro de inputs o contenteditable, ni con ⌘/Ctrl.
9. **Resolver una tarjeta** (descartar, confirmar, llamada completada) la retira con colapso de altura medida (con movimiento reducido, solo opacidad). «Deshacer» se ve 5 s y el foco va a la siguiente acción válida o al estado vacío (F06).
10. **Sin saltos:** la lista no se reordena durante una llamada ni con el panel en «Después de la llamada». Al volver el foco, lo nuevo entra al final de su sección con fundido.
11. **Navegación del comercial:** Hoy, Conversaciones, Preguntar, Llamar, Ajustes. Equipo solo para owner/admin y sin ranking. Los miembros no ven la tarjeta de planes.
12. **Preguntar** se abre en la columna derecha en lugar del panel de contacto; al cerrarlo vuelve el contacto que había.
13. **Estados** diseñados según `design.md` §6: carga, error, CRM sin conectar (admin / miembro), sin conversaciones, sin contactos asignados, todo hecho y parcial.
14. **Copy** nuevo en ES y EN en `product-catalog.ts`. Sin «IA», sin puntuaciones, sin números de prioridad.
15. **Reticle:** un flow guardado con este intent y veredicto `pass`: «el comercial abre Hoy, ve por qué llamar a su primer contacto y llama sin salir de la pantalla».

### Edge cases (del recorrido)

Cada fila tiene su test en la tarea indicada (`design.md` §14).

| Momento | Caso | Comportamiento esperado | Test |
|---|---|---|---|
| Apertura | CRM sin conectar, miembro | «Conecta tu CRM para preparar tu día» + «Tu administrador tiene que conectar el CRM.» + «Grabar una interacción». Sin panel | T3 |
| Apertura | CRM sin conectar, owner/admin | Igual, con «Conectar CRM» como acción principal | T3 |
| Apertura | CRM conectado, sin conversaciones, con contactos asignados | A quién llamar se llena con contactos sin llamar (`/contact-priorities`); el panel muestra la preparación en frío (E4) o «Sin conversación todavía.» | T3 |
| Apertura | Sin contactos asignados | «Todavía no hay contactos asignados para priorizar» + «Revisa tu asignación con el administrador» (miembro) / «Mapear responsables» (admin) | T3 |
| Apertura | `/today` devuelve 5xx | «No se pudo preparar el día» + «Reintentar». Las secciones que no dependen de `/today` siguen | T3 |
| Apertura | `coverage` parcial (CRM caído o sin permiso de emails) | Tarjetas verificadas + línea «Información incompleta · 10:05» bajo el pulso | T3 |
| Apertura | Falla `/contact-priorities` y `/today` responde | Solo tarjetas de `/today`; sin error a pantalla completa | T3 |
| Apertura | 40 señales | 7 tarjetas + «33 más cuando termines estos» (texto, no enlace). Al resolver, sube la siguiente | T3 |
| Apertura | Nada pendiente | «Nada urgente hoy. Buen momento para prospectar»; Próximas y Hecho hoy siguen visibles | T3 |
| Apertura | Owner/admin que vende | Su propia casa (solo sus datos) + Equipo en el menú | T4 |
| Apertura | Flag apagado a mitad de sesión | Al siguiente `/auth/me` vuelve la home actual; nada se pierde | T1 |
| Reuniones | Reunión con día y sin hora (E5) | «Hoy · sin hora» | T3 |
| Reuniones | Movida en el CRM | «acordada el {fecha}» (E5) | T3 |
| Reuniones | Ya pasada | Se queda atenuada hasta el final del día; si hay conversación, pasa a Hecho hoy | T3 |
| Falta tu OK | Confirmada desde la extensión u otra pestaña | Desaparece al refrescar, con fundido de 150 ms si tenía el foco | T3 |
| Falta tu OK | Follow-up redactándose | Fila «Escribiendo el seguimiento…» sin acción | T3 |
| Falta tu OK | Follow-up fallido | «No se pudo redactar» + «Reintentar» | T3 |
| Falta tu OK | Follow-up enviado desde Gmail o la extensión | Desaparece al refrescar | T2 |
| Falta tu OK | Follow-up de una conversación de otro comercial | Nunca aparece (solo el autor lo envía, `api/followup.py`) | T2 |
| Falta tu OK | Más de 3 filas | 3 visibles + «N más», que despliega en el sitio | T3 |
| Falta tu OK | Autoaprobación apagada | «Conversación con {nombre} sin guardar en el CRM» + «Revisar» → `MemoDetail` | T3 |
| Panel | Contacto sin teléfono | La acción principal pasa a «Abrir en el CRM» (F06) | T5 |
| Panel | Dialer no disponible (plan, app desktop, sin número verificado) | Sin «Llamar»; acción principal «Abrir en el CRM» | T5 |
| Panel | Brief cargando | Una sola línea «Leyendo…» (`BRIEF_LOADING`) | T4 |
| Panel | CRM caído / 401 al pedir el brief | «No se pudo cargar todo.» + las líneas verificadas | T4 |
| Panel | Contacto sin conversación | «Sin conversación todavía.» (F03), o preparación en frío con E4 | T4 |
| Panel | Cambio rápido entre tarjetas | Nunca se pinta el brief del contacto anterior (guarda de `shared/ui/brief.js`) | T4 |
| Panel | Contacto borrado en el CRM | La tarjeta sale al refrescar; si estaba seleccionada, pasa a la siguiente | T3 |
| Panel | CRM sin filtro de historial por contacto (Pipedrive hoy) | Se oculta el bloque de conversaciones; no se pinta vacío | T4 |
| Llamada | No conecta | «Llamada fallida» en la barra; la tarjeta se queda seleccionada | T5 |
| Llamada | Clic en otra tarjeta durante la llamada | La selección no cambia; tooltip «En llamada» | T5 |
| Llamada | Cambio de ruta durante la llamada | El dialer vuelve a su posición flotante actual (`FloatingDialer`) y la llamada sigue | T5 |
| Llamada | Abrir Preguntar durante la llamada | Preguntar sustituye al contenido del panel; la barra de llamada sigue en el pie | T5 |
| Llamada | Recarga del navegador | La llamada se corta (limitación actual del SDK de voz); se documenta, no se resuelve en v1 | — |
| Después | Procesado > 60 s | «Procesando la llamada…»; el comercial puede pulsar `n`. El resultado aparece luego en Falta tu OK o Hecho hoy | T5 |
| Después | Autoaprobación con cambio de etapa o reunión | Confirmación de E7 dentro del panel; «Deshacer» 5 s | T5 |
| Después | Buzón detectado (`screening_outcome`) | La selección avanza; no hay conversación ni follow-up | T5 |
| Hecho hoy | Cambio de día (zona del comercial) | Se vacía a medianoche | T2 |
| Multi-pestaña | Misma acción en dos pestañas | Idempotente (`request_id`); un 409 refresca y enseña el estado real (F06) | T3 |
| Ancho | 1024 px | Lista a todo el ancho; panel en `Sheet` | T4 |

## 7. Contratos de datos

| Sección | Endpoint | Estado |
|---|---|---|
| Reuniones de hoy | `GET /api/v1/today`, ítems `type: "meeting_today"` | **Falta (E5)**, `HOY_MEETINGS_ENABLED` |
| A quién llamar | `GET /api/v1/today` (`commitment_due`, `no_reply`, `going_cold`, `objection_open`) + `GET /api/v1/contact-priorities` (dolor confirmado, sin llamar) | Existe |
| Falta tu OK · confirmaciones | `GET /api/v1/today`, `type: "confirm_pending"` + `POST /today/{id}/resolve` con `action: "confirm"` | **Falta (E7)**, `HOY_CONFIRMATIONS_ENABLED` |
| Falta tu OK · follow-ups | `GET /api/v1/followups?status=ready` → `[{memo_id, contact_id, contact_name, company_name, subject, status, generated_at}]` (solo del autor) | **Falta (F16 · T2)** |
| Falta tu OK · por revisar | `GET /api/v1/memos?status=pending_review&limit=5` | **Falta el filtro `status` (F16 · T2)**; el listado existe (`api/memos.py`) |
| Próximas | `GET /api/v1/today/upcoming?days=7` → compromisos con fecha entre mañana y +7 días, más `crm_task_id` si E2 creó la tarea | **Falta (F16 · T2)**. Marcador «En el CRM» con E2 |
| Hecho hoy | `GET /api/v1/today/done` → señales resueltas hoy, follow-ups enviados, confirmaciones y llamadas conectadas del día | **Falta (F16 · T2)** |
| Panel · preparación | `GET /api/v1/briefs?contact_id=&connection_id=` | Existe (F03). Contenido v2 con E3; en frío con E4 |
| Panel · conversaciones | `GET /api/v1/memos?hubspot_contact_id=&limit=3` | Existe (HubSpot) |
| Panel · follow-up | `GET/POST /api/v1/memos/{id}/followup` | Existe (F02) |
| Llamar | `DashboardDialer` + `/calls/*` | Existe |
| Después de la llamada | `GET /api/v1/calls/{call_sid}` (memo_id, screening_outcome) → `GET /memos/{id}`, `/memos/{id}/meeting-proposal`, `/memos/{id}/followup` | Existe |
| Acciones y deshacer | `POST /today/{id}/resolve`, `PATCH /today/{id}` | Existe (F06) |
| Capacidad | `rep_workspace_enabled` en el resumen de empresa de `/auth/me` | **Falta (F16 · T1)** |

Las tres lecturas nuevas son deterministas y de solo lectura: no escriben en el CRM ni crean un camino de procesamiento paralelo. Todo sigue saliendo de `memos` (Interaction), `action_signals` y `outbound_calls`.

### Addendum T2 — lecturas (26 sep 2026)

**Flag.** `/followups`, `/today/upcoming` y `/today/done` van detrás de `REP_WORKSPACE_ENABLED`. Apagado, responden 404 `{"detail": "Not Found"}`, igual que una ruta que no existe. El flag se comprueba antes que los parámetros: con el flag apagado, un `status` desconocido o un `days` fuera de rango también dan 404. Las tres devuelven una lista JSON.

**Zona horaria.** La del comercial, con el mismo helper que ya usa Hoy (`brief_preferences.timezone`; por defecto `Europe/Madrid`). «Hoy» y «mañana» son días naturales en esa zona, también en los cambios de hora.

**`GET /api/v1/followups?status=ready`**
- `status`: uno o varios separados por comas, entre `ready` (por defecto), `generating` («Escribiendo el seguimiento…») y `unavailable` (el borrador falló o salió vacío: «No se pudo redactar»). Son los valores guardados en `memos.followup.status`. `sent` no se acepta porque va a Hecho hoy. Otro valor → 422.
- **Solo el autor** (`memos.user_id`), también para owner/admin, porque solo el autor envía (`api/followup.py`).
- **Ventana:** conversaciones creadas en los últimos 7 días (`memos.created_at`), de la más reciente a la más antigua, con un máximo de 50.
- Una conversación rechazada (`memos.status = rejected`) no sale aunque su borrador siga listo.
- Un borrador copiado pero no enviado sigue en `ready`. Enviado desde Gmail o desde la extensión pasa a `sent` y desaparece.
- Fila: `{memo_id, contact_id, contact_name, company_name, subject, status, generated_at}`.
  - `contact_id` = `hubspot_contact_id`.
  - Nombre y empresa salen de `extraction.contactName` / `companyName`, igual que en las tarjetas de Hoy.
  - `subject` (asunto final, o el del borrador) solo va relleno en `ready`; en los demás estados es `null`.
  - `generated_at` = `ready_at` y, si falta, `started_at`.

**Filtro `status` en `GET /api/v1/memos`**
- Opcional. Admite los estados de `MEMO_PIPELINE_STATUSES` (`app/services/captures.py`); otro valor → 422. Sin `status`, la respuesta es idéntica a la actual.
- **No va detrás del flag.** Es un filtro genérico e inocuo sobre un listado que ya existe y respeta las mismas reglas de visibilidad (`scope`, autor).
- Es un filtro exacto sobre la columna: `pending_review` también incluye las notas de buzón o sin respuesta (`screeningOutcome`), que nunca se autoaprueban.
- `reached_only=true` (opcional, por defecto `false`, tampoco detrás del flag) las descarta: quita las notas con `screening_outcome` `voicemail` o `no_response` y conserva las que no tienen `screening_outcome` (notas de voz, reuniones, llamadas sin clasificar). Es lo que pide «por revisar»: `?status=pending_review&reached_only=true`. Sin el parámetro, la consulta no cambia.

**`GET /api/v1/today/upcoming?days=7`**
- `days` entre 1 y 14 (por defecto 7); fuera de ese rango → 422.
- **Ventana:** desde mañana a las 00:00 hasta las 00:00 del día `mañana + days`, sin incluirlo; es decir, `days` días naturales empezando mañana. Lo que vence hoy o antes no sale: ya lo enseña Hoy (`commitment_due`).
- **Fuente:** las mismas conversaciones de las que Hoy saca sus señales: las 40 más recientes del propio comercial (`read_hoy_memos` en `app/services/hoy/materialize.py`), y de ellas los compromisos C04 (`extraction.intelligence.commitments`, con `due_at` y `text`).
- **Misma regla que Hoy, con el mismo código** (`fresh_signals`): por contacto (`hubspot_contact_id`, o la propia conversación si no tiene contacto) solo cuenta la conversación más reciente (`capture_started_at` o `created_at`). Si esa conversación marca `deal_closed`, no sale nada. Así Próximas no promete algo que Hoy no vaya a enseñar ese día.
- **Sin duplicados, con la clave de Hoy:** `commitment:{memo_id}:{tipo}:{fecha de due_at}`. Dos compromisos del mismo tipo el mismo día en la misma conversación son una sola fila (la primera), igual que una sola tarjeta en Hoy; tengan o no `id`.
- Fila: `{memo_id, contact_id, contact_name, company_name, text, due_at, precision, crm_task_id}`.
  - `precision` = `temporal_precision` del modelo (`date` | `time`), o `null` si falta.
  - `crm_task_id` = `commitment.crm_task_id` (E2), o `null` si falta.
  - Orden: por `due_at`.

**`GET /api/v1/today/done`**
- Desde la medianoche local del comercial hasta ahora. De lo más reciente a lo más antiguo, con un máximo de 50.
- Fila: `{kind, contact_name, contact_id, at, memo_id}`. `contact_id` es el id del contacto en el CRM (el de la señal, o `hubspot_contact_id` de la nota o de la llamada), o `null` si no se conoce (añadido en la revisión de T3, 26 sep 2026).
  - `contact_name` sale del nombre extraído en la conversación: la de la fila o, si no, otra del mismo contacto, como en las tarjetas de Hoy. Si no hay ninguna, `null`.
  - `memo_id` puede ser `null`.
  - `kind` es extensible: E7 añadirá `confirmation`.
- **Qué cuenta como «hecho»:**
  - `signal`: una señal de Hoy **que el comercial resolvió hoy**: `status = resolved`, con `last_action_at` de hoy.
    - «Descartado» no es «hecho», y pospuesto tampoco.
    - Las resoluciones automáticas (el contacto respondió, la señal dejó de aplicar) no escriben `last_action_at`, así que no cuentan.
    - Tampoco cuentan si antes hubo, ese mismo día, una acción del comercial que no era resolver: una deshecha (`undo_deadline` vacío) o una posposición (`previous_status = snoozed`).
    - `at` = `last_action_at`.
  - `followup`: `memos.followup.status = sent` con `sent_at` de hoy. Copiar no cuenta. `at` = `sent_at`.
  - `call`: una llamada del dialer (`outbound_calls`) hecha hoy (`created_at`) con `call_disposition = connected`, es decir, con conversación.
    - No cuentan buzón, sin respuesta, comunicando, no contesta, fallida ni cancelada.
    - Tampoco la que aún no se ha clasificado: aparece al terminar de procesarse.
    - `at` = `answered_at` o, si falta, `created_at`.

**Edge cases (cada fila tiene su test en `backend/tests/hoy/test_rep_workspace_reads.py`; las filas hermanas comparten test)**

| Lectura | Caso | Comportamiento esperado |
|---|---|---|
| Las tres | Flag apagado | 404 en `/followups`, `/today/upcoming` y `/today/done`, también con un `status` desconocido o un `days` fuera de rango |
| Las tres | Flag encendido y sin datos | 200 con `[]` |
| `/followups` | Follow-up listo de un miembro, pedido por su owner | No sale en la lista del owner; sí en la del autor |
| `/followups` | Enviado (Gmail, extensión) o generándose | No sale con `status=ready` |
| `/followups` | Copiado sin enviar | Sale en `ready` |
| `/followups` | `status=generating,unavailable` | Salen los dos, con `subject: null` |
| `/followups` | Conversación de hace más de 7 días | No sale |
| `/followups` | `status=sent` o desconocido | 422 |
| `/followups` | Conversación rechazada con borrador listo | No sale |
| `/memos` | `status=pending_review` | Solo las notas en ese estado |
| `/memos` | Sin `status` | Mismas filas y misma consulta que hoy |
| `/memos` | `reached_only=true` | Sin buzón ni sin respuesta; salen las conectadas y las que no tienen `screening_outcome` |
| `/memos` | `reached_only=false` | Mismas filas y misma consulta que sin el parámetro |
| `/memos` | Estado desconocido | 422 |
| `upcoming` | Compromiso hoy a las 23:30 (Madrid) | No sale |
| `upcoming` | Compromiso mañana a las 00:30 (Madrid) | Sale |
| `upcoming` | Último día de la ventana a las 23:59 / día siguiente a las 00:00 | El primero sale; el segundo no |
| `upcoming` | Comercial en `Atlantic/Canary` | La ventana sigue su zona, no la de Madrid |
| `upcoming` | Con `crm_task_id` / sin él | En la fila / `null` |
| `upcoming` | Compromiso de otro comercial | No sale |
| `upcoming` | Mismo compromiso repetido en la conversación | Una sola fila |
| `upcoming` | Sin `id`: dos del mismo tipo el mismo día, y otro de otro tipo | Dos filas: la primera del par y la del otro tipo (clave de Hoy) |
| `upcoming` | Compromiso en una conversación más antigua que las 40 últimas | No sale (misma ventana que Hoy) |
| `upcoming` | Conversación más reciente con el mismo contacto, sin compromisos | El compromiso anterior no sale (regla de Hoy) |
| `upcoming` | `days=0` o `days=15` | 422 |
| `done` | Señal resuelta ayer a las 23:59 (Madrid) | No sale |
| `done` | Señal resuelta hoy a las 00:01 (Madrid) | Sale |
| `done` | Señal descartada o pospuesta hoy | No sale |
| `done` | Señal resuelta por el sistema, o tras deshacer o posponer hoy | No sale |
| `done` | Follow-up enviado hoy | Sale como `followup`, con `memo_id` y nombre |
| `done` | Follow-up enviado ayer o solo copiado | No sale |
| `done` | Llamada con buzón, sin respuesta o sin clasificar | No sale |
| `done` | Llamada conectada hoy | Sale como `call`, con el nombre de su conversación |
| `done` | Datos de otro comercial | No salen |
| `done` | Más de 50 filas | 50, de la más reciente a la más antigua |

### Addendum T3 — composición de la casa (26 sep 2026)

**Una sola regla, pura.** `composeHome` (`shared/ui/home.js`) recibe las seis lecturas (`/today`, `/contact-priorities`, `/followups`, `/memos` por revisar, `/today/upcoming`, `/today/done`), los resultados locales de las acciones de Hoy y la hora, y devuelve el estado de la casa y sus secciones. `RepHome` solo pinta. Una lectura que aún carga llega como `undefined`; una que falló, como `null`: su sección no sale y las demás siguen.

**Lecturas.** En paralelo con `/today`. Follow-ups: `?status=ready,generating,unavailable`. Por revisar: `/memos?status=pending_review&reached_only=true&limit=5`. En la casa estas lecturas, `/today` y `/contact-priorities` usan `staleTime: 0`: con el `staleTime` global infinito, `refetchOnWindowFocus` no volvía a leer nunca. Fuera de la casa (flag apagado), nada cambia.

**Tope de 7.** Las tarjetas de Hoy se reparten en el orden de las secciones: reuniones, confirmaciones y llamadas. Tres confirmaciones o más son una fila «{n} confirmaciones pendientes» que cuenta 1 y se despliega en el sitio. «N más cuando termines estos» suma lo que no cabe y el `folded_count` de `/today`, y va bajo la última sección de Hoy que se pinte (llamadas, confirmaciones o reuniones), aunque no quepa ninguna llamada. Si `/today` trae una `manual_task` visible, todas sus tarjetas cupieron y su `folded_count` son solo tareas del CRM, que la casa no pinta: no se suma.

**A quién llamar.** Tarjetas de `/today` (sin `manual_task`, `meeting_today` ni `confirm_pending`) y, detrás, los contactos de `/contact-priorities` con motivo `pain_agree_next_step` («Dolor confirmado») o `no_calls_logged` («Sin llamar»). Un contacto que ya sale en `/today` no se repite. Las tarjetas de prioridad no tienen id de señal: se llaman o se abren en el CRM, no se descartan.

**Falta tu OK.** Confirmaciones → follow-ups → por revisar. Se ven 3 filas y «{n} más» despliega el resto en el sitio. Los follow-ups y las revisiones no cuentan en el tope de 7.
- Follow-up `ready`: «Follow-up para {nombre} · «asunto»» + «Abrir».
- Follow-up `generating`: «Follow-up para {nombre} · Escribiendo el seguimiento…», sin acción.
- Follow-up `unavailable`: «Follow-up para {nombre} · No se pudo redactar» + «Abrir» (a `MemoDetail`). **Desviación de la fila «Follow-up fallido»:** no hay «Reintentar» porque no hay backend para regenerar (`should_generate` devuelve `False` para `unavailable`). Volverá cuando exista.
- Por revisar: «Conversación con {nombre} sin guardar en el CRM» + «Revisar» (a `MemoDetail`). El nombre es `extraction.contactName`, o «Contacto».
- «Abrir» en un follow-up y «Revisar» en una confirmación también llevan a `MemoDetail` hasta que exista el panel (T4).

**Reuniones (E5) y confirmaciones (E7).** Llegan como ítems de `/today` con los campos de siempre y, en las reuniones, `due_at` y `precision`. Sin hora (`precision: "date"`) → «Hoy · sin hora». Con hora ya pasada → atenuada hasta que acabe el día. Con `memo_id` (ya capturada) → sale de Reuniones. «acordada el {fecha}» lo escribe el backend en `detail` y se pinta tal cual. Sin E5/E7 no llegan y no sale nada.

**Próximas.** Filas de `/today/upcoming` con `inCrm = Boolean(crm_task_id)` → chip «En el CRM». La fecha es «Mañana» o «Jue 1 oct», en la zona del navegador.

**Hecho hoy.** Filas de `/today/done` de tipo `call`, `followup`, `signal` o `confirmation` (otro tipo no se pinta ni se cuenta). Si un contacto tiene `call` y `signal`, solo queda la `call`. Se compara por `contact_id` cuando las dos filas lo traen; si no, por nombre (sin mayúsculas ni espacios extra); una fila sin nombre ni id no se deduplica. El contador es el número de filas.

**Pulso.** «{n} llamadas hoy» con las filas `call` de Hecho hoy; sin llamadas, no hay pulso. «, todas guardadas en {CRM}» solo si todo esto es verdad: hay CRM conectado, la lectura de por revisar respondió con menos de 5 filas (está completa), toda llamada tiene `memo_id` y ninguna está por revisar. Con una llamada: «1 llamada hoy, guardada en {CRM}».

**Estados (en este orden).**
1. `/today` cargando sin datos → tres siluetas de papel; nada más.
2. `/today` falla sin datos → «No se pudo preparar el día» + «Reintentar»; el resto de secciones se pinta con lo que tenga, también las tarjetas de `/contact-priorities` en A quién llamar.
3. Sin CRM y sin tarjetas de Hoy → «Conecta tu CRM para preparar tu día»; miembro: «Tu administrador tiene que conectar el CRM.» + «Grabar una interacción»; owner/admin: «Conectar CRM» + «Grabar una interacción». Un solo botón por estado: con «Conectar CRM» o «Mapear responsables», «Grabar una interacción» es acción de texto; para el miembro es el único botón. No se pide el CRM hasta que la lectura de integraciones ha respondido.
4. Nada pendiente (sin reuniones, Falta tu OK ni llamadas) y fuentes completas: si `/contact-priorities` responde `title_no_assigned` → «Todavía no hay contactos asignados para priorizar» + «Revisa tu asignación con el administrador» (miembro) o «Mapear responsables» (owner/admin) + «Grabar una interacción»; si no → «Nada urgente hoy. Buen momento para prospectar». Próximas y Hecho hoy siguen. Ni «Nada urgente» ni «sin contactos asignados» se dicen hasta que `/contact-priorities`, follow-ups y por revisar han respondido.
5. `coverage` incompleta, `/today` falló al refrescar con datos previos, o falló `/contact-priorities`, follow-ups o por revisar → «Información incompleta · hh:mm» bajo el pulso. Con fuentes incompletas y nada pendiente no se dice «Nada urgente».

**Acciones y 409.** Un resultado local solo manda sobre `/today` si su `version` es mayor. Si ya no está pendiente, se ve mientras dura su «Deshacer» y después la tarjeta sale. Un 409 al resolver o deshacer trae la fila real: se olvida el resultado local de esa tarjeta y se vuelve a leer `/today`. Nunca se pinta un estado que el servidor no ha dicho.

**Copy fuera de §12 del diseño** (hace falta para pintar lo anterior): `home_followup_writing`, `home_followup_failed`, `home_followup_subject` (las comillas del asunto, «…» en ES y “…” en EN), `home_confirm_group`, `home_pulse_call`, y el pulso con «guardadas» como frase entera (`home_pulse_calls_saved`, `home_pulse_call_saved`) para que la UI no una frases con puntuación propia; y `done_signal` («Resuelto: {nombre}»). «{n} más» de Falta tu OK reutiliza `today_folded`.

**Follow-ups redactándose.** Mientras alguno está `generating`, la lectura se repite cada 5 s durante 2 minutos como mucho; después solo al volver a la pestaña. `followupPoll` es puro y tiene test.

**Accesibilidad de «{n} más».** El botón lleva `aria-expanded` y `aria-controls`; al desplegar, el foco pasa a la primera fila nueva.

**Fuera de T3.** Criterio 9 (salida con altura medida, foco a la siguiente acción) y criterio 10 (sin reordenar; lo nuevo, al final de su sección) se entregan en T4/T5 con el panel y la selección.

**Edge cases (cada fila tiene su test en `shared/ui/home.test.js`; lo que solo se ve en el navegador lo dice la última columna)**

| Caso | Comportamiento esperado | Navegador |
|---|---|---|
| Secciones con datos | Orden Reuniones → Falta tu OK → A quién llamar → Próximas → Hecho hoy | — |
| Sección vacía | No sale | — |
| 2 reuniones + 2 confirmaciones + 6 llamadas | 2 + 2 + 3 llamadas; «3 más» | — |
| 3 confirmaciones o más | Una fila agrupada que cuenta 1 | — |
| Contacto en `/today` y en `/contact-priorities` | Una tarjeta, la de `/today` | — |
| 7 reuniones + 3 llamadas / 7 reuniones + `folded_count: 12` | Solo Reuniones; «3 más» / «12 más» bajo las reuniones | Posición de la línea |
| Prioridades con otros motivos (`followup_pending`, `scheduled_no_early_call`, `history_partial`) | No salen | — |
| 40 señales (`/today` trae 7 y `folded_count: 33`) | 7 tarjetas + «33 más» | — |
| `/today` con `manual_task` visible y `folded_count` | No se suma a «N más» | — |
| Falta tu OK con más de 3 filas | 3 + «{n} más» | Despliegue en el sitio |
| Follow-up `generating` | Fila sin acción | — |
| Follow-up `unavailable` | Fila «No se pudo redactar» + «Abrir»; sin «Reintentar» | — |
| Conversación por revisar | Fila con nombre + «Revisar» a su `MemoDetail` | — |
| Próximas con y sin `crm_task_id` | `inCrm` verdadero / falso | — |
| Próximas mañana y dentro de 5 días | «Mañana» / «Lun 5 oct» | — |
| Hecho hoy con `call` y `signal` del mismo contacto | Solo la `call` (por `contact_id` si las dos lo traen; si no, por nombre); contador 1 | — |
| Hecho hoy con un tipo desconocido | No sale ni cuenta | — |
| Pulso con 3 llamadas guardadas / una por revisar / lectura de revisión incompleta o caída / sin CRM | Con «todas guardadas» / sin / sin / sin | — |
| Sin llamadas hoy | Sin pulso | — |
| `/today` cargando | Estado de carga, sin secciones | Siluetas |
| `/today` 5xx | Estado de error; follow-ups, Próximas y Hecho hoy siguen | «Reintentar» |
| `/today` 5xx con prioridades | Estado de error; A quién llamar sigue con las tarjetas de `/contact-priorities` | — |
| Lecturas que deciden «Nada urgente» o «Conecta tu CRM» aún cargando | Ni «todo hecho» ni «conecta»; sin bloque de estado | — |
| Prioridades, follow-ups o por revisar caídos, sin nada pendiente | Sin «todo hecho»; «Información incompleta · hh:mm» | — |
| Follow-up `generating` más de 2 minutos | Deja de repetir la lectura; vuelve al enfocar la pestaña | — |
| `/contact-priorities` caído | Solo tarjetas de `/today`; sin error | — |
| CRM sin conectar, miembro / owner-admin | Estado `connect`, sin / con «Conectar CRM» | Botones |
| Sin conversaciones y con contactos asignados | A quién llamar con los contactos «Sin llamar» | — |
| Sin contactos asignados, miembro / owner-admin | Estado `no_assigned`, con «Revisa tu asignación…» / «Mapear responsables» | Botones |
| Nada pendiente | Estado «todo hecho»; Próximas y Hecho hoy siguen | — |
| `coverage` parcial | Tarjetas + «Información incompleta · hh:mm»; con nada pendiente no es «todo hecho» | — |
| Reunión sin hora / movida en el CRM / ya pasada / capturada | «Hoy · sin hora» / `detail` tal cual / atenuada / fuera | Atenuado |
| Confirmada en otra pestaña, contacto borrado en el CRM | Al refrescar, la fila o la tarjeta no está | Fundido de 150 ms (T4) |
| Resultado local más viejo que `/today` | Manda `/today` | — |
| Descartada con «Deshacer» vencido | La tarjeta sale | — |
| 409 al resolver o deshacer | Se olvida el resultado local y se relee `/today` | — |

### Addendum T4 — panel de contacto, selección y teclado (26 sep 2026)

**Filas.** Se recorren en el orden en que se ven: reuniones → Falta tu OK (las visibles; al desplegar «{n} más», también las nuevas) → A quién llamar. No son filas: la fila agrupada de confirmaciones (no es un contacto) ni una tarjeta resuelta mientras dura su «Deshacer». Las reglas son puras (`shared/ui/home.js`: `homeRows`, `homeSelection`, `holdOrder`).

**La casa es la cola.** La selección es el estado de `queueReducer` (F06) con las filas como `items`: el índice es la fila seleccionada. `s` es `skip` (en la última fila, sin selección, como en F06); `Esc` es `exit`; `n` solo actúa en revisión (T5). ↑/↓ y j/k mueven sin dar la vuelta; sin selección, ↓ elige la primera fila y ↑ la última. En T4 `Enter` no pasa la cola a `calling`: llama con el dialer flotante de hoy y la selección sigue libre (la llamada en la cola es T5).

**Selección inicial.** Desde 1280 px, mientras el comercial no haya tocado la selección, queda seleccionada la primera tarjeta de A quién llamar; si no hay llamadas, la primera fila. Por debajo de 1280 px no se selecciona nada hasta que el comercial elige. Tras `Esc`, un refresco no vuelve a seleccionar.

**Teclado.** Solo con el flag y en la casa. Ninguna tecla actúa dentro de un input, textarea, select o contenteditable, ni con ⌘, Ctrl o Alt. `Enter` sobre un botón o enlace con el foco no hace nada más: ya lo activa el navegador. Con Preguntar abierto, `Enter` no actúa (el panel no se ve). `Esc` cierra Preguntar; si no está abierto, quita la selección, y eso cierra el `Sheet`.

**`Enter` = la acción principal del panel.**
- Confirmación seleccionada → Confirmar.
- Si no: con contacto, dialer disponible y sin que el CRM diga que no tiene teléfono → llamar.
- Si no: «Abrir en el CRM» si hay enlace; si no, nada.

**Resolver** (descartar, posponer, confirmar): la selección pasa a la siguiente fila válida; si no hay, a la anterior; si no queda ninguna, sin selección. La tarjeta se convierte en la fila «Descartada · Deshacer» (o «Pospuesta · Deshacer») con un colapso de altura medida (`exitMotion`); con movimiento reducido, solo opacidad. A los 5 s se va con un fundido de 150 ms. «Posponer a mañana» es `snooze` hasta las 00:00 de mañana en la zona del navegador.

**Refresco sin saltos.** Lo que ya estaba conserva su sitio aunque el servidor cambie el orden; lo nuevo entra al final de su sección con un fundido; lo que desaparece se funde en 150 ms y, si estaba seleccionado, la selección pasa a la siguiente fila válida.

**Panel** (`ContactPanel`, el mismo fijo o en `Sheet`):
- **Cabecera:** iniciales, nombre y «cargo · empresa» si el CRM los da. ↗ «Abrir en el CRM» si hay enlace. ✕ solo en `Sheet`.
- **Reunión seleccionada:** «Reunión hoy 11:30» (o «Hoy · sin hora») y, debajo, `detail` tal cual («Falta del playbook: …»), encima de «Antes de llamar».
- **Confirmación seleccionada:** su texto, `detail`, «Confirmar» (`outline`, con la pista ↵) y «Revisar» si trae `memo_id`. Sin pastilla de llamar.
- **Antes de llamar:** `/briefs` para ese contacto. Como mucho 3 líneas de hechos; «No se pudo cargar todo.» es un aviso y no cuenta en las 3. `label` → `.v-chip`; una línea con `source: "playbook"` → filete bronce. Cargando: «Leyendo…». Lectura caída (red, 401): «No se pudo cargar todo.». La respuesta guarda el contacto pedido y solo se pinta si es el seleccionado.
- **Acción principal, solo una:**
  - «Llamar a {nombre}» (pastilla llena, pista ↵). {nombre} es el nombre de pila.
  - Si no se puede llamar, «Abrir en el CRM» ocupa la misma pastilla y la ↗ de la cabecera no se repite.
  - Debajo, a 12 px, el teléfono que devuelve el CRM para ese contacto (la búsqueda del dialer). Nunca el de otro resultado.
  - «Posponer a mañana» · «Descartar» solo en tarjetas de `/today` con id: no en las de prioridad ni en confirmaciones.
- **Follow-up pendiente:** si `/followups` trae uno de ese contacto o la fila es un follow-up. «asunto» · listo · Abrir (a `MemoDetail`); redactándose o fallido, con los textos de Falta tu OK.
- **Por revisar seleccionada:** la misma fila («Conversación con {nombre} sin guardar en el CRM») y «Revisar».
- **Conversaciones:** solo con HubSpot. `GET /memos?hubspot_contact_id=&reached_only=true&limit=3`, sin `scope`: solo las del propio comercial, también si es owner/admin. El bloque no sale si el CRM no es HubSpot, mientras carga ni si no hay ninguna.
  - Cada fila: «fecha · tipo · duración» + resumen (2 líneas como mucho). Clic → `MemoDetail`.
  - El tipo sale de `interactionKind`, un campo nuevo y de solo lectura en la respuesta de memos (`interaction_kind_of`). Si no se reconoce: «Conversación».
  - Duración en minutos, solo si es mayor que 0.
- **Cambio de contacto:** fundido de 150 ms, sin deslizar.

**Columna derecha** (`DashboardLayout`, flag encendido y `/dashboard`):
- Desde 1280 px, una columna de 400 px con el panel. Sin selección, no hay columna.
- Preguntar ocupa su lugar; al cerrarlo vuelve el contacto que había.
- Por debajo de 1280 px, Preguntar se abre como hoy y el panel va en el `Sheet` del design system (`src/components/ui/sheet.tsx`), no modal, 400 px a la derecha, `Esc` cierra: la lista sigue usable y un clic en otra tarjeta cambia el contacto.
- Fuera de `/dashboard`, o con el flag apagado, nada cambia.

**Tarjetas con el flag encendido:**
- Sin botones fijos. Clic o foco = seleccionar.
- Icono de teléfono de 36 px: desde 1280 px, al pasar el ratón o con el foco; por debajo, siempre. Nunca en la seleccionada desde 1280 px. Solo con contacto y dialer.
- La seleccionada lleva borde bronce/45.
- Con el flag apagado, `CallCard` y `TodayPanel` no cambian.

**Copy fuera de §12:** `panel_meeting_today`, `panel_contact_sheet` (aria-label del `Sheet`), `panel_brief_failed`, `panel_followup_ready`, `panel_kind_call`, `panel_kind_meeting`, `panel_kind_visit`, `panel_kind_conversation`, `panel_minutes`, `home_card_dismissed`, `home_card_snoozed`. «Leyendo…» reutiliza `teamLoading`, el mismo texto que `BRIEF_LOADING`. El ✕ del `Sheet` reutiliza `cancelAction`, como el de Preguntar.

**Fuera de T4:** dialer anclado, «En llamada», «Después de la llamada», borrador dentro del panel, bloqueo de la selección durante la llamada y «sin número verificado» (T5).

**Edge cases (cada fila tiene su test; la última columna dice dónde, o «Navegador» si solo se ve pintado)**

| Caso | Comportamiento esperado | Test |
|---|---|---|
| ↑/↓, j/k con y sin selección | Mueven; sin selección, la primera o la última fila | `queue.test.js`, `home.test.js` |
| Tecla dentro de input, textarea, select o contenteditable | Ninguna acción | `queue.test.js` |
| ⌘, Ctrl o Alt | Ninguna acción | `queue.test.js` |
| `Enter`, `s`, `n`, `Esc` | Mismo significado que F06 | `queue.test.js` |
| `Enter` con el foco en un botón o enlace | Solo lo activa el navegador | `queue.test.js` |
| Carga desde 1280 px con reuniones y Falta tu OK | Seleccionada la primera tarjeta de A quién llamar | `home.test.js` |
| Carga por debajo de 1280 px | Nada seleccionado | `home.test.js` |
| Sin llamadas | Seleccionada la primera fila | `home.test.js` |
| `Esc` y refresco | Sigue sin selección | `home.test.js` |
| Orden de navegación | Reunión → Falta tu OK → llamadas; en los extremos se queda | `home.test.js` |
| Confirmaciones agrupadas; tarjeta en su «Deshacer» | No son filas | `home.test.js` |
| «{n} más» desplegado | Sus filas se recorren | `home.test.js` |
| Resolver la seleccionada | La siguiente; en la última, la anterior; si no queda nada, sin selección | `home.test.js` |
| `s` en la última fila | Sin selección (F06) | `home.test.js` |
| Refresco con una fila nueva y el orden cambiado | Lo de antes en su sitio, lo nuevo al final, la selección igual | `home.test.js` |
| Contacto borrado en el CRM (desaparece al refrescar) | Si estaba seleccionado, pasa al siguiente; fundido de 150 ms | `home.test.js`, `today-card.test.js`; fundido: Navegador |
| Posponer a mañana | `snooze` hasta las 00:00 de mañana | `home.test.js` |
| Brief cargando / lectura caída / parcial / sin conversación | «Leyendo…» / «No se pudo cargar todo.» / aviso + líneas / «Sin conversación todavía.» | `brief.test.js` |
| Cambio rápido entre tarjetas | Nunca el brief del contacto anterior | `brief.test.js` |
| `label` y línea de playbook; más de 3 líneas | Chip y filete; 3 líneas | `brief.test.js` |
| Acción principal | Llamar / Abrir en el CRM (sin teléfono, sin dialer, sin contacto) / Confirmar / ninguna | `contact-panel.test.ts` |
| Teléfono de otro resultado de búsqueda | No se enseña | `contact-panel.test.ts` |
| CRM sin filtro por contacto (Pipedrive, Salesforce) | Sin bloque de conversaciones | `contact-panel.test.ts` |
| Owner/admin que vende | Historial solo con sus conversaciones; Equipo en el menú | `contact-panel.test.ts`, `nav.test.ts` |
| Tipo y duración de una conversación | Llamada / Reunión / Visita / Conversación; «14 min»; sin duración si es 0 | `contact-panel.test.ts`, `test_memo_interaction_kind.py` |
| 1024 px | Lista a todo el ancho; panel en `Sheet` al seleccionar; icono de teléfono siempre visible | Navegador |
| Preguntar abierto desde 1280 px | Ocupa la columna; al cerrarlo vuelve el contacto | Navegador |
| Colapso al resolver; movimiento reducido | Altura medida / solo opacidad | Navegador |
| Flag apagado | `/dashboard`, `CallCard` y `TodayPanel` como hoy | Navegador (sin cambios en esos caminos) |

## 8. Dependencias

- **Existentes:** F05 (`/today`), F06 (acciones, deshacer, cola), F03 (`/briefs`), F02 (follow-up), F04 (`/contact-priorities`), F07 (Preguntar), F13 (campana e informes), F15 (Equipo).
- **E2:** marcador «En el CRM» en Próximas. Sin E2, Próximas muestra los compromisos sin marcador.
- **E3:** brief v2 y etiqueta «Pitch hecho · falta cualificar» en el panel. Sin E3, el panel muestra las líneas actuales de F03.
- **E4:** preparación en frío para contactos sin llamar. Sin E4, «Sin conversación todavía.» + el motivo de la prioridad.
- **E5:** sección Reuniones de hoy. Sin E5, la sección no aparece.
- **E6:** no bloquea; «Tu forma de escribir» vive en Ajustes.
- **E7:** confirmaciones en Falta tu OK y en «Después de la llamada». Sin E7, Falta tu OK solo muestra follow-ups y conversaciones por revisar.
- **E1:** tipo de interacción (Llamada / Reunión / Visita) en el historial del panel. Sin E1 se muestra «Conversación».

## 9. Evals

F16 no añade ni modifica prompts. Es UI más lecturas deterministas, así que va con tests (`design.md` §14). Los evals del follow-up son de E6.
