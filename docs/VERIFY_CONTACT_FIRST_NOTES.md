# Verificación manual: contact-first sync (FASE 1 + 2.2 + 2.3)

Este documento acompaña a los 6 commits sobre `backend/app/services/hubspot/sync.py`,
`tasks.py`, `associations.py`, `crm_updates.py`, `salesforce_provider.py`,
`memo_approval.py`, `memos.py` y la extensión/frontend. Es una checklist para que la
ejecutes tú mismo, con el backend corriendo en local contra tu portal de pruebas, antes de
que Álvaro toque nada.

**Nada de esto se ha ejecutado todavía.** No hay tests automatizados (ni siquiera con
mocks) cubriendo este código - `backend/tests/hubspot/` está vacío, y por FASE 0 tenías
explícitamente prohibido escribir tests nuevos en este PR. Lo único que respalda este
código hasta ahora es revisión de código línea por línea entre nosotros, y tu
verificación manual de los `associationTypeId` contra la documentación oficial de
HubSpot. Esta es literalmente la primera vez que se ejecuta. Ver la sección 7 para el
detalle de qué es más probable que falle por eso.

## 0. Antes de empezar

Aplica primero, en este orden (independientes entre sí, pero ambas antes de desplegar):

1. `backend/migrations/019_backfill_crm_updates_status.sql` - ya aplicada según tu
   confirmación anterior.
2. `backend/migrations/020_fix_line_item_resource_type_check.sql` - revísala y
   aplícala si no lo has hecho ya.
3. Antes de desplegar el código con `track()` (el `git push` a `main`), comprueba que no
   haya ninguna sync en vuelo - un despliegue puede matar el proceso a mitad de una sync y
   dejar una fila `pending` huérfana (ver sección 11.B). Ejecuta:

   ```sql
   select id, memo_id, action_type, resource_type, status, created_at,
          now() - created_at as age
   from crm_updates
   where status = 'pending'
   order by created_at desc
   limit 20;
   ```

   - Si no hay filas, o todas tienen `age` de varios minutos o más (restos de pruebas
     anteriores, no algo en curso), adelante.
   - Si hay alguna con `age` de segundos o menos de un minuto: probablemente hay una sync
     real en curso ahora mismo (alguien aprobando una memo desde el popup). Espera 1-2
     minutos y repite la consulta - las acciones de una sync (upserts, nota, tareas) tardan
     segundos, no minutos, así que si sigue apareciendo con `age` creciendo sin confirmarse
     nunca (nunca desaparece ni pasa a `success`/`failed`), no la esperes indefinidamente:
     es la señal de que el propio código actual ya se ha quedado colgado por otra razón, no
     de que el despliegue vaya a romper algo.
   - No hace falta que la tabla esté completamente vacía de `pending` - una fila `pending`
     de hace 2 horas es ruido de pruebas antiguas, no una sync en curso. Lo que importa es
     la antigüedad, no el conteo.

Luego:

```bash
make backend
```

Deja el terminal abierto y visible: vas a grepear su salida en tiempo real (o pegarla
después). El formato de log local es texto plano con pares `clave=valor` al final de
cada línea (no JSON) - los greps de este documento buscan el texto del mensaje, que
aparece igual en ambos formatos.

## 1. Qué grabar y dónde

Necesitas **dos** contactos de prueba distintos en HubSpot para cubrir los dos casos que
importan:

- **Contacto A - sin deal**: no tiene ningún deal asociado (así `matched_deals` viene
  vacío y el backend resuelve `skip_deal=True`). Debe estar asociado a una **empresa**
  para poder comprobar también su timeline. Si no tiene empresa, omite esa fila del
  resultado y anótalo - no es un fallo, es limitación del caso elegido.
- **Contacto B - con deal**: asociado a un **deal existente** y a una **empresa**. Este
  es el caso que ya funcionaba antes de todo este trabajo y que no debe haberse roto: la
  nota debe seguir llegando a las tres timelines (contacto, empresa, deal), no solo a la
  del deal como antes.

Para cada uno, abre la **página de detalle del contacto** en HubSpot (URL con
`.../contacts/record/0-1/<id>`, no la del deal ni la de la empresa) y grava desde ahí con
la extensión. El tipo de página importa: la extensión resuelve `contact_id` (y a través
de él `company_id`/`deal_id`) a partir de esta página vía `parseHubSpotUrl` +
`GET /crm/hubspot/contacts/{id}/context`.

Contenido de la grabación, para ambos contactos:
- Contenido claro para el resumen (para que la nota no salga vacía).
- Al menos un **next step con fecha/hora explícita** (p. ej. "enviar la propuesta el
  viernes"), para forzar la creación de una tarea.
- Si quieres intentar también la verificación de line items (sección 5), menciona
  explícitamente un producto con nombre, cantidad y precio (p. ej. "le vendemos 3
  licencias del plan Pro a 50 euros cada una"). Esto depende de que el LLM de extracción
  meta esos datos en `extraction.raw_extraction.line_items` - no está garantizado por
  cómo hables, así que si no aparece, no asumas que el código falló: usa la
  verificación directa por SQL de la sección 5 en su lugar.

Espera a que termine de transcribir/extraer y abre la pantalla de previsualización
(popup de la extensión) para cada uno.

## 2. Qué debes ver en la pantalla de confirmación (antes de aprobar)

**Contacto A (sin deal)**, en la tarjeta "Deal Target":
- Nombre: **"Contact only (no deal)"**. Si ves un nombre de deal, el matching encontró
  uno y no estás en el escenario `skip_deal` - para y revisa el contacto elegido.
- Motivo: "Sync will update the matched contact".
- Los next steps grabados aparecen en la lista de action items.

**Contacto B (con deal)**, en la misma tarjeta:
- Nombre del deal existente (no "New Deal", no "Contact only").

Aprueba la sync desde cada popup.

## 3. Qué comprobar después en HubSpot, objeto por objeto

### Caso A - Contacto sin deal

| Objeto | Qué mirar | Resultado esperado |
|---|---|---|
| **Contacto** | Pestaña "Activity" / timeline | Nota nueva ("Nota de llamada (Vocify)" / "Call note (Vocify)") con resumen y transcripción con turnos "Comercial:"/"Contacto:" |
| **Contacto** | Pestaña "Tasks" | Tarea nueva con fecha de vencimiento coherente, **asociada al contacto** |
| **Empresa** (si tenía) | Pestaña "Activity" | **La misma nota** (mismo texto) - es la asociación adicional, no una nota duplicada |
| **Deals** | Busca por contacto/empresa | **Ningún deal nuevo**. Si aparece uno, revisa el log `sync_started` (sección 4) para ver si `skip_deal` llegó en `False` |

### Caso B - Contacto con deal existente (el caso que no debe romperse)

| Objeto | Qué mirar | Resultado esperado |
|---|---|---|
| **Deal** | Pestaña "Activity" | Nota nueva, igual que siempre |
| **Contacto** | Pestaña "Activity" | **La misma nota**, ahora también aquí (antes de este cambio, solo llegaba al deal) |
| **Empresa** | Pestaña "Activity" | **La misma nota**, también aquí |
| **Deal** | Pestaña "Tasks" (o el widget) | Tarea nueva asociada al **deal**, no al contacto (con deal, las tareas siguen colgando del deal como siempre) |

Si algo del Caso B cambió de comportamiento respecto a antes de este trabajo (p. ej. la
tarea acaba en el contacto en vez del deal), es una regresión - para y avísame antes de
seguir.

## 4. Líneas de log a grepear en el backend

Busca por el texto del mensaje (ignora mayúsculas/minúsculas y emoji si tu terminal los
recorta):

```bash
grep -i "hubspot sync started" backend.log
grep -i "task association target resolved" backend.log
grep -i "tasks created" backend.log
grep -i "note association targets resolved" backend.log
grep -i "note associated" backend.log
grep -i "note created" backend.log
grep -i "skipping duplicate" backend.log
grep -i "hubspot sync complete" backend.log
```

Orden esperado y qué confirma cada línea (con el `target_type`/`targets` variando entre
Caso A y B como se indica):

1. `🔗 HubSpot sync started` - Caso A: `deal_id=None skip_deal=True contact_id=<A>`.
   Caso B: `deal_id=<deal> skip_deal=False contact_id=<B>`.
2. `🎯 Task association target resolved` - Caso A: `target_type=contact
   contact_id=<A> deal_id=None`. Caso B: `target_type=deal deal_id=<deal>`.
3. `✅ Tasks created` - `count=1` (o el número de next steps válidos) y `task_ids`.
4. `🎯 Note association targets resolved` - Caso A: `targets=['contacts:<A>',
   'companies:<id>']` (sin `deals:`). Caso B: `targets=['deals:<deal>',
   'contacts:<B>', 'companies:<id>']` - las **tres**.
5. `✅ Note associated` - una línea **por cada objeto** de la lista anterior, con
   `association_type_id` = 202 (contacto), 190 (empresa) o 214 (deal). Si falta alguna,
   ve al punto 5 de la sección 6 (asociación individual fallida).
6. `✅ Note created` - confirma que la nota en sí se creó (`note_id=<id>`).
7. `✅ HubSpot sync complete`.

Por API en vez de por logs: cada paso también queda en `crm_updates` (sección 5).

## 5. `crm_updates`: que quede en 'success', no en 'pending', y line items

Esto es lo que valida que `track()` (FASE 2.2) funciona de verdad, no por casualidad de
orden como antes.

**Pásame esta consulta para que la ejecute yo** (recuerda la regla: no toco
`.env`/credenciales de producción, pero esta consulta la corres tú y me pegas el
resultado, o me das acceso de solo lectura si prefieres ejecutarla tú misma vía el SQL
editor de Supabase):

```sql
select memo_id, action_type, resource_type, status, resource_id, error_message, created_at, completed_at
from crm_updates
where memo_id in ('<memo_id_caso_A>', '<memo_id_caso_B>')
order by memo_id, created_at;
```

Resultado esperado:
- **Ninguna fila con `status = 'pending'`** una vez la sync ha terminado (si ves alguna,
  o la request sigue en vuelo, o algo murió entre el `reserve` y el `confirm` de
  `track()` - espera al menos `CRM_UPDATES_PENDING_TTL_MINUTES` = 10 minutos y repite la
  consulta antes de darlo por un bug real).
- Caso A: filas `action_type IN ('upsert_contact', 'create_tasks', 'create_note')`,
  todas `status='success'`, ninguna `create_deal`/`update_deal`.
- Caso B: filas `action_type IN ('upsert_contact', 'update_deal' o 'create_deal',
  'create_tasks', 'create_note')`, todas `status='success'`.
- `resource_id` debe venir poblado en las filas de `create_note` (el `note_id` de
  HubSpot) y `create_tasks` (mirar `data->>'task_ids'` en vez de `resource_id`, que es
  singular).

**Line items (fix de la 020)**: si conseguiste que la grabación produjera line items
(ver sección 1), busca la fila `action_type='create_line_item'` para ese memo - debe
existir y estar en `status='success'`, no fallida ni ausente por completo. Si la
grabación no produjo `raw_extraction.line_items` (lo más probable la primera vez),
verifica el fix directamente sin depender del LLM:

```sql
-- Debe ejecutarse SIN error tras aplicar la 020 (antes de la 020 fallaba con
-- "violates check constraint crm_updates_resource_type_check"). Usa un
-- memo_id/user_id/crm_connection_id reales que ya existan (los de cualquiera
-- de los dos memos de prueba sirven) para no violar las FK.
begin;
insert into crm_updates (memo_id, user_id, crm_connection_id, action_type, resource_type, status)
values ('<memo_id_real>', '<user_id_real>', '<crm_connection_id_real>', 'create_line_item', 'line_item', 'success');
rollback;
```

El `rollback` deja la tabla intacta - es solo para confirmar que el CHECK acepta
`'line_item'` ahora, sin dejar basura de prueba.

## 6. Reintentar la misma memo: no debe duplicar nada

Con cualquiera de los dos memos ya aprobados y sincronizados con éxito, fuerza un
segundo intento de sync sobre la misma memo (repite el approve desde la extensión, o
llama a `POST /memos/{id}/approve` otra vez con el mismo `memo_id`).

Resultado esperado:
- En HubSpot: **ni una nota ni una tarea nuevas** - el contacto/deal siguen con
  exactamente los mismos que después del primer intento.
- En el log: `Skipping duplicate transcript note` (evento `note_skipped_duplicate`) y
  `Skipping duplicate task sync for memo retry` (evento `tasks_skipped_duplicate`), en
  vez de los logs de creación de la sección 4.
- En `crm_updates`: **ninguna fila nueva** para ese `memo_id` en el segundo intento (la
  consulta de la sección 5 debe devolver el mismo número de filas que antes del retry).

Si en cambio ves una segunda nota o tarea, el dedupe por `memo_id`
(`is_action_already_done`, filtrando por `status='success'`) no está funcionando - es
el escenario que más nos preocupa de todo este trabajo. Para y avísame con el log
completo del segundo intento antes de seguir probando nada más.

## 7. Atomicidad de la nota: ¿HubSpot rechaza el POST entero si una asociación es inválida?

Todo el fallback anti-duplicados en `sync.py` (paso 7) asume que si el `POST
/crm/v3/objects/notes` con las 3 asociaciones en el array falla, **nada** se crea en
HubSpot - por eso es seguro reintentar con el create "bare" (sin asociaciones) y asociar
uno por uno. Nunca se ha comprobado contra la API real. Esta sección lo fuerza.

### Cómo inyectar el ID inválido

`company_id` en el payload de `POST /memos/{id}/approve` (`ApproveMemoRequest`,
`backend/app/models/memo.py`) llega **tal cual lo mandes**, sin que el backend compruebe
que ese ID exista de verdad ni que esté relacionado con el `contact_id` - solo lo usa
`sync.py` para construir el array `associations` de la nota. No hace falta tocar nada en
HubSpot ni en el contacto: basta con saltarte el popup para esta única llamada y pegarle
directo al backend con un `company_id` que no existe.

1. Usa el Caso B (contacto con deal y empresa reales) para tener 2 asociaciones válidas
   (deal + contacto) junto a la inválida (empresa) - así se distingue "todo falla" de
   "falla solo la inválida".
2. Grava una memo nueva sobre ese contacto (o reutiliza una que **todavía no hayas
   aprobado** - si ya está aprobada, este payload de más abajo sin `extraction` no
   volverá a sincronizar, ver el aviso en el paso 4).
3. Consigue el token: abre las devtools del navegador (o de la propia extensión) en la
   pestaña Network, busca cualquier llamada a la API de Vocify ya autenticada, y copia
   el valor completo del header `Authorization` (empieza por `Bearer `).
4. Ejecuta (sustituye `<memo_id>`, `<token>`, `<contact_id_real>`, `<deal_id_real>` -
   deja `company_id` tal cual, es el ID inválido a propósito):

```bash
curl -i -X POST "http://localhost:8000/memos/<memo_id>/approve" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "deal_id": "<deal_id_real>",
    "contact_id": "<contact_id_real>",
    "company_id": "999999999999",
    "skip_deal": false,
    "create_note": true
  }'
```

No incluyas `"extraction"` - si la memo aún no estaba aprobada, `approve_memo_core` usa
la extracción ya guardada de la transcripción. Si la memo YA estaba aprobada, omitir
`extraction` hace que el endpoint devuelva el resultado cacheado sin volver a
sincronizar (mira el bloque `if memo_data.get("status") == "approved" ...` en
`memo_approval.py`) - por eso el paso 2 pide una memo sin aprobar todavía.

### Qué comprobar después

Grepea el log por `note_create_with_assoc_failed`, `note_associated`, y
`note_association_failed` para esta memo, y mira el deal y el contacto en HubSpot.

- **Supuesto correcto (esperado)**: aparece `⚠️ Note create with associations failed
  (safe to retry bare)` seguido de `✅ Note associated (fallback)` **dos veces** (deal y
  contacto) y `⚠️ Failed to associate note ... to companies 999999999999` una vez. En
  HubSpot: la nota existe en la timeline del deal y del contacto, y no hay ninguna nota
  huérfana ni duplicada. Esto confirma que HubSpot rechazó el create-con-asociaciones
  completo antes de persistir nada, y que el fallback hizo su trabajo sin crear dos
  notas.
- **Supuesto falso (el riesgo real)**: **no** aparece `note_create_with_assoc_failed`,
  y en su lugar ves `✅ Note associated` (la rama feliz, no la de fallback) para las
  tres, incluida la empresa con ID `999999999999`. Esto significaría que HubSpot creó
  la nota igualmente y simplemente ignoró en silencio la asociación inválida, sin
  devolver ningún error - el código de `sync.py` no comprueba la respuesta asociación
  por asociación, solo asume que si el create no lanzó excepción, las tres se aplicaron.
  Si ves esto, para y avísame: significa que una asociación inválida (company_id
  obsoleto, ID de un objeto bordado/mergeado) puede quedar reportada como éxito en
  `crm_updates` sin que sea verdad, aunque en este caso concreto no genere una nota
  duplicada (ese riesgo específico sigue cerrado por el diseño del fallback).

Nota sobre el alcance de esta prueba: un ID completamente inexistente es el caso más
fácil de forzar y el más probable de ser rechazado por la validación de HubSpot antes de
crear nada. No cubre el caso más sutil de un ID que existe pero al que le falta permiso
de escritura solo para ese tipo de objeto - ese haría falta forzarlo quitando un scope
de la conexión, que es más intrusivo y no lo recomiendo para esta ronda.

## 8. Salesforce: `skip_deal=True` debe fallar visiblemente, no silenciosamente

Solo si tienes un portal de Salesforce de prueba conectado. Repite el Caso A (contacto
sin deal) pero con la conexión de CRM activa apuntando a Salesforce en vez de HubSpot.

Resultado esperado:
- El popup/dashboard debe mostrar el mensaje real: *"Salesforce doesn't support
  contact-only sync yet. An Opportunity is required..."* - no el genérico "Failed to
  sync with HubSpot"/"Something went wrong".
- **No debe crearse ninguna Opportunity** en Salesforce para esa memo.
- En el backend, `POST /memos/{id}/approve` debe devolver **409**, no 500 (puedes
  confirmarlo con las devtools del navegador/Network tab, o `curl -i` a mano).

## 9. Qué reportar al terminar

Para cada verificación:
- ✅/❌ Caso A: nota en timeline de contacto y de empresa, tarea en el contacto, ningún
  deal nuevo.
- ✅/❌ Caso B: nota en las tres timelines (deal, contacto, empresa), tarea en el deal.
- ✅/❌ `crm_updates` sin filas `pending` colgadas, para ambos casos.
- ✅/❌ Line item: fila `success` (real o vía el `insert`/`rollback` de la sección 5).
- ✅/❌ Reintento de memo: sin duplicados, ni en HubSpot ni en `crm_updates`.
- ✅/❌ Atomicidad de la nota (sección 7): supuesto correcto o falso, con las líneas de
  log exactas que lo confirman.
- ✅/❌ Salesforce: 409 + mensaje real, sin Opportunity creada (o "N/A, sin portal de
  Salesforce de prueba").
- Pega las líneas de log relevantes de la sección 4, o si algo falló, la línea de error
  correspondiente y el resultado completo de la consulta SQL de la sección 5.
- Antes de empezar: confirma que el botón **Rollback** de la sección 12 aparece de
  verdad sobre el despliegue de `3e90075` en tu dashboard de Railway - mejor descubrir
  ahora que no está disponible (fuera de ventana de retención) que durante un
  incidente real.

## 10. Si falla: síntomas → log a mirar → sospechoso

| Síntoma | Log a mirar | Punto de código sospechoso |
|---|---|---|
| El popup muestra un nombre de deal en vez de "Contact only (no deal)" en el Caso A | No hace falta backend: revisa `preview.py`/matching | `matching.py` (fuera de alcance, no lo tocamos) |
| `sync_started` no lleva `skip_deal=True` en el Caso A | Log de `sync_started`, y si no aparece, la request `POST /memos/{id}/approve` | El popup no mandó `skipDeal: true` o `memo_approval.py` no lo propagó |
| No aparece `Task association target resolved` ni `Tasks created` | Busca `tasks_skipped_duplicate` (memo ya sincronizada, prueba con una memo nueva) | Si tampoco aparece: revisa que `extraction.nextSteps` no viniera vacío en la memo (tabla `memos`, columna `extraction`) |
| Aparece `Tasks created` pero la tarea no cuelga del objeto esperado | Revisa el payload del cliente HTTP en DEBUG (o log temporal en `tasks.py: create_task`) | `HubSpotTasksService.create_task` - confirma que `contact_id`/`deal_id` llegó correcto desde `create_tasks_from_extraction` |
| No aparece `Note association targets resolved` | Revisa que "Create note" estuviera marcado y que el transcript no llegara vacío | Condición `if create_note and transcript and transcript.strip() and (deal_id or contact_id or company_id)` en `sync.py`, paso 7 |
| `Note create with associations failed, retrying bare` seguido de `Failed to associate note ... to <object>` | Ese `<object>` es el que falló; el resto sigue asociado | Falta de scope en la conexión para ese tipo de objeto (`crm.objects.notes.write` + el `.write` del objeto que falle) |
| La nota aparece en unos objetos pero no en otros | `Note association targets resolved` - comprueba si ese objeto estaba en la lista de `targets` | El id de ese objeto (company_id/deal_id) nunca llegó a `sync.py` - revisa `GET /crm/hubspot/contacts/{id}/context` en `crm.py` |
| Se creó un deal nuevo en el Caso A | `sync_started` con `deal_id` distinto de `None`, o `deal_created` en el log | Algo en preview/matching encontró o creó un deal antes de `sync_memo` - revisa `preview.py`, no es este cambio |
| Queda una fila `pending` en `crm_updates` más de 10-15 minutos después de terminar la sync | Busca excepciones en el log alrededor de esa acción, y el log `🚨 stale pending` (background task, cada 5 min) | El proceso murió entre el `reserve` y el `confirm` de `track()` (crash, deploy a mitad, timeout no capturado) |
| `create_line_item` falla incluso tras aplicar la 020 | El mensaje de error completo en `⚠️ Line item create failed` | Puede ser un fallo real de HubSpot (falta `crm.objects.line_items.write`, o el portal no tiene "Commerce" activado) - no confundir con el bug de la 020, que era en nuestra propia tabla, no en HubSpot |
| El sync falla entero (`success=False`) | Busca `❌ Sync failed` o `Unexpected error` cerca del final del log | Si menciona `note_format` o `ModuleNotFoundError`, es un problema de import ajeno a esta verificación - repórtalo aparte |

## 11. Riesgos conocidos y documentados

### 11.A. Condición de carrera en `track()`

`previous_updates` (el dedupe de `sync.py`) se lee **una sola vez** al principio de
`sync_memo` y se reutiliza para todas las comprobaciones de esa llamada. Es un
check-then-act clásico: dos requests concurrentes para la misma memo (doble clic con red
lenta, dos pestañas, un reintento de red del propio cliente mientras la primera sigue
viva en el servidor) pueden leer ambas `previous_updates` vacío antes de que ninguna
confirme nada, pasar el dedupe las dos, y crear dos notas/tareas en HubSpot. `track()`
reserva la fila `pending` antes de llamar a HubSpot, pero no hay ningún lock a nivel de
fila que impida que la segunda request reserve la suya propia en paralelo.

Tres opciones evaluadas, con su coste real:

1. **Botón deshabilitado en la UI** (`chrome-extension/popup/popup.js`, ya hace
   `approveSyncButton.disabled = true` de forma síncrona en el handler del click, antes
   de cualquier `await`). Cierra el doble-click en la misma pestaña. No cierra nada más
   (dos pestañas, reintento de red, dos clientes distintos) - es mitigación de UX, no una
   garantía. Coste: ya está, prácticamente gratis mantenerlo.
2. **`SELECT FOR UPDATE` / `pg_advisory_lock` sobre la memo, durante todo `sync_memo`**.
   Descartada. Todo el acceso a Supabase hoy pasa por el cliente PostgREST
   (`supabase-py`), sin conexión ni transacción compartida entre llamadas - mantener un
   lock durante los 10-30+ segundos que dura un `sync_memo` completo (varias llamadas
   HTTP secuenciales a HubSpot) exigiría abrir la primera conexión Postgres cruda del
   backend y mantenerla viva de un extremo a otro. Eso ata el tamaño del pool de
   conexiones a la latencia de HubSpot: cambiaría "nota duplicada, poco probable" por
   "pool de conexiones agotado bajo carga" - el mismo tipo de riesgo de escala que
   estamos evitando, no uno menor.
3. **Índice único parcial** en `crm_updates (memo_id, action_type) WHERE status IN
   ('pending', 'success')` - **elegida**. Mueve la exclusión mutua al motor de la base
   de datos: la segunda reserva de `track()` para la misma acción de la misma memo
   recibe un `unique_violation` (23505), no una carrera "probablemente" evitada. Coste
   real, no aproximado: (a) una migración con el índice; (b) `track()` debe capturar ese
   `unique_violation` en el paso de reserva y tratarlo como dedupe-skip, no como error
   500; (c) el TTL de filas `pending` huérfanas deja de poder ser solo de lectura -
   `_refresh_crm_updates_stale_pending_gauge` (hoy solo cuenta para el gauge) tendría que
   pasar a hacer `UPDATE ... SET status='failed'` sobre las filas que superan el TTL,
   para que salgan del índice y no bloqueen reintentos legítimos para siempre; (d)
   `create_line_item` queda fuera de este primer corte - es la única acción con varias
   filas legítimas por memo (varios productos), así que el índice tal cual bloquearía el
   segundo producto de una memo, no la segunda request duplicada - necesitaría una clave
   propia (por item, no solo por memo+acción) como trabajo aparte.

**Decisión (2026-08-14): se implementa, pero después de la verificación manual de este
documento, no antes.** Si la sección 7 (atomicidad de la nota) revela que HubSpot no
rechaza el POST-con-asociaciones entero cuando una es inválida, la forma de "éxito" de
esa acción concreta cambia, y con ella lo que `track()` necesita capturar como
`unique_violation` para esa fila - no tiene sentido construir el índice sobre un
contrato que puede moverse. No bloqueante para desplegar esta ronda: el volumen y patrón
de uso actuales (aprobación manual desde el popup, ya con el botón deshabilitado) hacen
la carrera poco probable, no imposible - queda como deuda explícita, no como "no pasa
nada".

### 11.B. `pending` huérfana ambigua: no distingue "nunca llamé a HubSpot" de "llamé y no sé qué pasó"

Con el diseño actual de `track()`, un `pending` huérfano (fila reservada, proceso muerto -
típicamente un `SIGKILL` de despliegue - antes de que se ejecute `mark_success` o
`mark_failed`) puede significar dos cosas incompatibles, y hoy no hay forma de saber cuál:

1. El proceso murió **antes** de llamar a HubSpot (formateando el payload, por ejemplo).
   No hay efecto secundario en HubSpot. Reintentar es seguro.
2. El proceso murió **durante o justo después** de la llamada a HubSpot, sin llegar a
   ejecutar el código que marca la fila. HubSpot puede haber procesado la petición
   igualmente. Reintentar puede crear un duplicado (`create_note`, que no tiene
   comprobación secundaria contra HubSpot antes de crear, a diferencia de
   `create_tasks`/upserts).

El TTL de filas `pending` (`CRM_UPDATES_PENDING_TTL_MINUTES`) y el gauge asociado
(`_refresh_crm_updates_stale_pending_gauge`) tratan hoy ambos casos igual: solo cuentan,
no distinguen, y `is_action_already_done` nunca trata una `pending` post-cutover como
"hecha" sea cual sea su antigüedad - así que el caso 2 se reintenta automáticamente igual
que el caso 1, con riesgo real de nota duplicada para `create_note` específicamente.

**Diseño propuesto (no implementado): tercer estado `in_flight`.**
`track()` pasaría de reservar `pending` → confirmar `success`/`failed` a reservar
`pending` → marcar `in_flight` justo antes de la llamada HTTP a HubSpot (escritura
`await`eada, no en paralelo) → confirmar `success`/`failed`. Semántica del huérfano:

- `pending` huérfana = nunca se llamó a HubSpot = segura, `is_action_already_done` la
  sigue tratando como "no hecha" (reintento automático correcto, y ahora sin el agujero
  del caso 2, porque ese caso ya no puede quedar clasificado como `pending`).
- `in_flight` huérfana = ambigua = `is_action_already_done` la trata como "hecha" (bloquea
  el reintento automático) y sale en un gauge/alerta propio, separado del de `pending`,
  para revisión manual - no se autorresuelve sola, alguien tiene que mirar HubSpot y
  decidir el estado final a mano.

Verificado antes de proponerlo, no asumido:
- `retrying` (valor ya admitido por el `CHECK` de `status`) **no sirve tal cual**: no se
  usa desde ningún sitio hoy (`mark_retrying` es código muerto de un diseño de
  reintento-con-backoff no relacionado), y `is_action_already_done` lo agrupa junto a
  `failed` como "no hecho" - reutilizarlo sin cambiar esa función produciría el reintento
  automático que justamente se quiere evitar. Hace falta un valor nuevo (`in_flight`), vía
  migración aditiva al `CHECK`, dejando `retrying` libre para su significado original.
- Coste de escritura: +1 `UPDATE` por acción rastreada (3 escrituras en vez de 2). A 50
  syncs/día, entre +200 y +300 filas de más al día (`UPDATE` de una sola fila por PK,
  sub-milisegundo) - no es un problema de volumen a este caudal ni a 10x. El coste real es
  de latencia en el camino crítico (~10-50ms por escritura extra, 3-6 veces por sync),
  irrelevante frente a los varios segundos que ya dominan una sync por las llamadas HTTP a
  HubSpot.
- Alternativa evaluada en profundidad, no descartada de pasada: ver 11.C.

**Estado: diseñado, no implementado.** Igual que 11.A, no bloquea el despliegue ni la
verificación manual de esta ronda: la ventana existe hoy en producción, con o sin este
deploy, y el paso 3 de la sección 0 (comprobación de que no haya syncs en vuelo) ya reduce
- no elimina - la probabilidad de golpear esta ventana justo durante el despliegue que
estamos verificando.

### 11.C. Alternativa evaluada para 11.B: marcador único por memo + búsqueda en HubSpot antes de crear

Mismo patrón que `create_tasks` ya usa con `existing_subjects`: en vez de fiarnos del
estado de nuestra propia fila en `crm_updates`, preguntar a HubSpot (la fuente de la
verdad) si la nota de esta memo ya existe antes de crearla. Si funciona sin agujeros,
evitaría el estado `in_flight`, la migración del `CHECK` y la cola de revisión manual de
filas huérfanas bloqueadas de 11.B. Evaluado con la documentación oficial de HubSpot, no
asumido:

1. **Qué marcador.** Un comentario HTML embebido en `hs_note_body` es la idea obvia, pero
   es frágil: desde julio de 2024 HubSpot sanea el HTML de las propiedades de texto
   enriquecido (incluida `hs_note_body`) para prevenir XSS, y ese proceso también
   *canoniza* el HTML para que se parezca a lo que produciría el editor de HubSpot - que
   nunca genera comentarios HTML. No hay confirmación documentada de si los limpia o no;
   solo una llamada real (crear una nota con un comentario y releerla) lo confirmaría.
   Alternativa más sólida, verificada: las notas son un objeto CRM de primera clase
   (`objectTypeId = 0-46`) y admiten propiedades personalizadas vía la Properties API
   (`POST /crm/properties/{version}/0-46`), igual que contactos o empresas. Un campo
   propio (p. ej. `vocify_memo_id`) guardado como propiedad de la nota - no dentro de
   `hs_note_body` - resuelve único-por-memo e invisible-en-la-timeline sin depender del
   comportamiento no documentado del saneador. Coste añadido: aprovisionar esa propiedad
   una vez por portal de cliente (no por nota), trabajo conocido, no un riesgo nuevo.
2. **Coste.** Una búsqueda extra (`POST /crm/objects/{version}/notes/search`) antes de
   cada nota. Límite documentado: 5 req/seg por cuenta de HubSpot del cliente - a 50
   syncs/día de un solo usuario, irrelevante. Latencia: una llamada de red más
   (~200-500ms), del mismo orden que las que ya se hacen en secuencia.
3. **Qué NO cierra - confirmado, no asumido.** La Search API de HubSpot es
   documentadamente eventualmente consistente: *"It may take a few moments for newly
   created or updated CRM objects to appear in search results"* (documentación oficial).
   Reportes de su propia comunidad de desarrolladores hablan de retrasos de varios
   segundos a uno o dos minutos, con casos donde ni 20-30 segundos de espera bastaron.
   Consecuencia según el escenario:
   - **Carrera de dos requests casi simultáneas (11.A): NO la cierra.** Ambas buscan antes
     de que ninguna haya creado nada, ambas ven cero resultados, ambas crean. Es el mismo
     check-then-act, solo movido de `crm_updates` a la Search API de HubSpot.
   - **Fila huérfana por caída de proceso (11.B): la mitiga, no la garantiza.** Un
     reintento tras una caída suele llegar minutos u horas después (reaprobación manual),
     tiempo de sobra para que el índice se asiente. Pero "suele" no es "siempre" - un
     reintento dentro de la ventana de indexación puede no ver la nota ya creada.
4. **¿Sigue haciendo falta `in_flight`?** Sí. No son sustitutos, son complementarios:
   `in_flight` da una garantía determinista (bloquea con certeza cuando hay ambigüedad,
   al coste de necesitar revisión humana cuando se dispara); la búsqueda da una mitigación
   probabilística (reduce, no elimina, el riesgo de 11.B, y no toca 11.A en absoluto).
   Combinarlas es la mejor opción, no elegir una: usar la búsqueda como comprobación
   barata de refuerzo (igual que `existing_subjects` en tareas) reduce cuántas veces una
   fila `in_flight` huérfana necesita ojos humanos, pero `in_flight` sigue siendo la única
   de las dos que da una garantía dura frente a duplicar.

**Estado: evaluado, no implementado.** Ninguna de las dos vías (`in_flight` o
búsqueda-antes-de-crear) bloquea el despliegue ni la verificación manual de esta ronda.

**Decisión final (2026-08-14), orden de implementación cuando llegue el momento:**

1. `in_flight` (11.B) - la garantía dura. Entra después de la verificación manual.
2. Índice único parcial (11.A) - cierra la carrera. También después de la verificación
   manual.
3. Marcador como propiedad personalizada de la nota (11.C) - el último de los tres, y
   solo si sigue aportando algo una vez puestos los otros dos. Añade una llamada de
   aprovisionamiento por portal de cliente (crear la propiedad la primera vez), y esa
   complejidad extra tiene que justificarse frente a lo que ya cubran `in_flight` + el
   índice único antes de construirla.

Ninguno de los tres se implementa todavía. El diseño queda parado aquí hasta después de
la verificación manual de este documento - la prueba de atomicidad de la sección 7 puede
cambiar el contrato de "éxito" de `create_note` y con él parte de este análisis.

## 12. ROLLBACK - qué hacer si algo falla después de que la app arranque bien

Esto es para el caso en que el arranque va bien (`Application startup complete.` en los
logs) pero algo falla **dentro** de una sync real - no para un fallo de arranque (ese ya
lo cubre la sección de despliegue: la app ni siquiera llega a servir tráfico, no hace
falta rollback, Railway sigue con la versión anterior).

### ¿Railway tiene botón de rollback al despliegue anterior?

Sí, confirmado contra la documentación oficial de Railway (no lo he mirado en tu
dashboard concreto, así que verifica que el botón aparece antes de necesitarlo, no
durante el incidente):

- Service → pestaña **Deployments** → busca el despliegue del commit `3e90075` (el
  último que corría antes de este push) → menú de los tres puntos → **Rollback**.
- **Rollback** restaura la imagen Docker y las variables de ese despliegue tal cual
  eran, **sin reconstruir** - tarda segundos, no minutos. Es la opción a usar en un
  incidente real.
- Solo está disponible si ese despliegue sigue dentro de la ventana de retención de tu
  plan de Railway. Si no aparece la opción (fuera de ventana), usa **Redeploy** sobre
  ese mismo despliegue en su lugar: reconstruye desde el código original de ese commit y
  llega al mismo resultado, pero tarda más (hay build de por medio).
- Dato relevante para el timing del propio rollback: por defecto Railway da **0
  segundos** de gracia al contenedor saliente antes de mandarle `SIGKILL` (variable
  `RAILWAY_DEPLOYMENT_DRAINING_SECONDS`, no configurada aquí). Cualquier `sync_memo` en
  vuelo en el momento exacto del cambio de contenedor se corta en seco, no termina con
  gracia - relevante para el punto 3 de abajo.

### ¿El código de 3e90075 funciona igual con las migraciones 019 y 020 ya aplicadas?

Sí, confirmado leyendo el propio `sync.py` de ese commit (no es una suposición):

- **019 (backfill de `status`)**: el código de `3e90075` no lee la columna `status` en
  ningún sitio. Su dedupe (`tasks_already_synced`, `note_already_created`) comprueba
  solo si existe una fila con ese `action_type` en `previous_updates` - nunca filtra por
  estado. Para ese código, `status='success'` o `status='pending'` es exactamente la
  misma fila. 019 es invisible para el código viejo.
- **020 (CHECK con `line_item`)**: el código de `3e90075` ya intenta insertar
  `resource_type='line_item'` desde la migración 015 - antes de la 020 esa inserción
  fallaba (violaba el CHECK) y se registraba como advertencia genérica. Con la 020
  aplicada, esa misma inserción simplemente empieza a funcionar. Es una mejora estricta
  para el código viejo, no un cambio de comportamiento que pueda romper nada.

Ninguna de las dos migraciones necesita revertirse para que el rollback funcione.

### ¿Se re-sincronizarían las memos que ya se sincronizaron con `track()`?

Depende de la acción, comprobado línea por línea contra `3e90075`, no por intuición:

- **Empresa, contacto, deal, line items**: el código viejo **nunca** comprobaba
  `previous_updates` antes de estos pasos - los ejecuta sin condición cada vez (son
  upserts idempotentes contra HubSpot por diseño: buscan por email/dominio antes de
  crear). El rollback no cambia nada aquí porque el código viejo ya se comportaba así
  antes de que existiera `track()`.
- **Tareas** (`create_tasks`/`merge_tasks`): el chequeo viejo es
  `any(u.action_type in (...) for u in previous_updates)` - solo mira que exista una
  fila con ese `action_type`, sin mirar su contenido. Las filas que `track()` deja en
  `'success'` sí tienen ese `action_type`, así que el código viejo las verá como "ya
  sincronizado" y **no** recreará tareas. No hay riesgo de duplicado aquí.
- **Nota** (`create_note`): el chequeo viejo es más estricto -
  `data.deal_id == deal_id`, no solo presencia de la fila. Las filas de `track()` en
  `'success'` sí llevan `data={"note_id":..., "deal_id":..., ...}` con esa forma, así
  que también coinciden - **no** se recreará la nota para una memo ya sincronizada
  correctamente antes del rollback.
- **La única ventana real de riesgo**: una fila que `track()` dejó en `'pending'` con
  `data={}` (reservada pero nunca confirmada - proceso matado a mitad, ver el punto de
  arriba sobre `SIGKILL` sin gracia). Para tareas, esa fila sin datos igual cuenta como
  "ya sincronizado" para el chequeo viejo (mira solo `action_type`) - resultado: esa
  acción concreta **no se reintenta sola**, se queda huérfana hasta limpiarla a mano; es
  una sincronización perdida, no una duplicada. Para la nota, esa fila con `data={}` no
  coincide con `data.deal_id == deal_id` - el código viejo **sí** intentaría crear la
  nota otra vez. Si el `POST` a HubSpot de ese intento interrumpido ya había tenido
  éxito antes de que el proceso muriera (ventana de milisegundos entre la respuesta de
  HubSpot y la escritura de `mark_success`), ahí sí habría una nota duplicada. Si murió
  antes de llamar a HubSpot (la mayor parte de esa ventana), el reintento es correcto,
  no un duplicado.
- **Mitigación práctica para el momento del rollback en sí**: antes de pulsar Rollback,
  comprueba si hay filas muy recientes en `crm_updates`
  (`created_at > now() - interval '2 minutes'` y `status='pending'`). Si las hay, espera
  a que se resuelvan (deberían pasar a `'success'`/`'failed'` en segundos) antes de
  hacer el rollback, en vez de revertir literalmente encima de una sync en vuelo. Reduce
  esta ventana ya estrecha a prácticamente cero sin tocar código.

## 13. Qué NO cubre esta verificación

- **La carrera real** entre dos requests concurrentes para la misma memo (dos pestañas,
  doble click con red lenta, o dos clientes distintos). Ver la sección 11 para el
  análisis completo y la decisión tomada. La sección 6 de este documento solo cubre el
  reintento **secuencial** (aprobar, esperar, aprobar otra vez), que es un caso distinto
  y ya funciona por el dedupe de `crm_updates`.
- Rate limits reales de HubSpot con el volumen de ~50 syncs/día.
- Consistencia eventual de HubSpot (asociar una tarea a un contacto creado en el mismo
  request).
- El caso más sutil de la sección 7: un ID que existe pero al que le falta permiso de
  escritura solo para ese tipo de objeto (no probado, requeriría quitar un scope a
  propósito).
