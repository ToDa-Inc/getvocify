# Pendientes (27 sep 2026)

## Lista 2 en staging (27 sep)

Todas las entregas E1–E10 están en `staging` (`feat/lista-2`). En Vocify (`70b7ffd2-c360-4d4f-a339-4affec769f7a`) los flags de Lista 2 están encendidos; el email diario y `HOY_NO_REPLY_ENABLED` siguen apagados. F16 (casa del comercial) verificado en el navegador: Hoy, Falta tu OK, A quién llamar y el menú corto.

Antes de merge a `main`:

- Definir el playbook de Vocify en Ajustes → Proceso. Sin él no hay «qué decir», ni adherencia, ni coaching.
- Las llamadas del marcador las procesa producción (`api.getvocify.com`), no staging. Staging y producción comparten base de datos: los flags y el backfill de C04 de Toni también están en producción, solo para Vocify.
- El backfill de C04 (`scripts/backfill_intelligence.py`) y la reproyección (`scripts/reproject_patterns.py`) solo se han corrido para Toni. El resto del equipo las tendrá en conversaciones nuevas, o hay que backfillearlas.
- El follow-up de Tomás usa relleno de IA («veo una gran oportunidad»): tocar el prompt y correr sus evals.
- «Cómo abrir» en cold call sigue pendiente: el playbook no tiene paso de apertura.
- `sales-email-read` sigue fuera de alcance (tarjeta «no te ha respondido»).
- Encender `REPORTING_DAILY_EMAIL_ENABLED` solo cuando el founder haya revisado el flujo.

Quedan de la corrección de errores de la revisión reunión-vs-código.

1. ~~**Recargar OpenRouter y correr evals.**~~ Hecho el 26 sep: C04 16/16 en tres pasadas, F07 15/15 en dos.
2. ~~**Commitear.**~~ Hecho en `staging` por tema. Falta desplegar a producción (merge a `main`) cuando se haya revisado staging. Migraciones 050–053 ya ejecutadas.
   **Email diario:** va detrás de `REPORTING_DAILY_EMAIL_ENABLED`, apagado para todos. Encenderlo por empresa cuando se haya revisado el flujo.
   **Etapa del deal:** con `DEAL_STAGE_CONFIRM_ENABLED` el comercial confirma la etapa en la revisión de la nota y aceptar una reunión ya no la mueve. Apagado para todos. El cambio en la extensión (`review-insights.js`) necesita publicar una versión nueva.
3. **Encender la inteligencia** en cada cliente nuevo. En Vocify ya está encendida (SQL de activación, 27 sep). Sin ella no funcionan la prioridad 1 («confirmó el problema»), la reunión detectada por el modelo ni la etapa sugerida. Se enciende por empresa (ver `docs/features/MASTER_PLAN.md`, «Activar un flag para un cliente»):

   ```sql
   INSERT INTO company_feature_flags (company_id, flag, enabled)
   VALUES ('<company_id>', 'INTELLIGENCE_EXTRACT_ENABLED', true)
   ON CONFLICT (company_id, flag) DO UPDATE SET enabled = true, updated_at = NOW();
   ```

   Los memos antiguos solo la tendrán si se corre `scripts/backfill_intelligence.py <user_id> [limit]`, que tiene coste de LLM. Probar antes con pocos memos.
4. **Permiso de emails en HubSpot (`sales-email-read`).** Sin él, la tarjeta de Hoy «no te ha respondido» (`HOY_NO_REPLY_ENABLED`) nunca sale y Ask tampoco puede leer el contenido de los emails. Añadirlo primero en la configuración de la app en el portal de desarrollador de HubSpot (si solo se añade en `HUBSPOT_OAUTH_SCOPES` y no en la app, el OAuth falla para todos). Después, añadirlo en `backend/app/services/hubspot/oauth.py` y que cada cliente reconecte HubSpot. En Pipedrive haría falta `mail:read`.

## Inicio, tipos de interacción y Ajustes (30 sep, `feat/home-dashboard`)

Pendiente tras las tareas 1–9. Diseño en `docs/superpowers/specs/2026-09-30-dashboard-home-and-interaction-types-design.md`.

- **Sin veredicto de Reticle.** El puerto 4400 lo tiene otro proceso, así que ninguna tarea pudo usar `reticle_*`. Lo visto en el navegador fue como owner, sin veredicto. Y `.reticle/intent.json` (~L205 y ~L230) sigue registrando `/dashboard/process` y el flujo de Preguntar en la barra superior: hay que regrabarlos con Cmd/Ctrl+K y `/dashboard/settings/playbooks`.
- **Cambiar el tipo con datos reales no se ha probado.** El cambio de tipo (menú del chip, incluida «Interna») solo se ejercitó contra un stub en el navegador, nunca contra la API real.
- **Vista del comercial sin ver en vivo:** el carril de Inicio (incluidos «Todo al día» e «Información incompleta»), Coaching → Playbook y el primer uso de una cuenta nueva. Las señales del equipo tampoco se han visto con datos reales (la cuenta no tenía actividad).
- **Ningún memo tiene tipo todavía** (0 de 329 en staging). Los tipos salen al publicar playbooks y con `PLAYBOOK_ROUTING_ENABLED` y `SALES_ROLES_ENABLED` encendidos, que rutean las capturas. La detección de «Interna» por IA solo corre en los memos que se extraen de nuevo; no hay backfill.
- **`INTERNAL_DETECTION_ENABLED` existe y está apagado para todos.** Sin él, la extracción sigue devolviendo `customerPresent` pero ningún memo se marca «Interna» solo; marcarlo a mano (chip o «cambiar» en el memo) funciona siempre. Encenderlo por empresa después de mirar unas cuantas transcripciones reales (cuántas salen `customerPresent` false y cuántas null). No se ha corrido ningún eval de esta regla.
- **Notas de voz (R4):** hecho en la web. La grabadora del dashboard (Grabar, «Graba tu primera llamada» de Inicio y la grabadora de Hoy, todas con `VoiceRecorderWidget`) envía `interaction_kind=voice_note` a `upload-and-extract` y, si no hay transcripción en vivo, a `/memos/upload`. Un audio subido como archivo y una transcripción pegada siguen sin tipo (se deriva, `call`). La extensión de Chrome y la app de escritorio siguen enviando las notas de voz como `call`.
- **Grabaciones de llamadas de HubSpot sin pantalla.** Con `ActivityPanel` se fue la única lista de `/crm/hubspot/recordings` y el botón que llamaba a `/crm/hubspot/calls/{id}/process`. Solo lo usaban comerciales de empresas con `REP_WORKSPACE_ENABLED` apagado; el webhook sigue procesando las grabaciones. Si una empresa lo necesita, se rehace en Interacciones.
- **Dos instancias de Preguntar comparten un id de conversación en `sessionStorage`** (la de Inicio y la hoja de Cmd/Ctrl+K): una pregunta enviada desde la hoja no aparece en el hilo de Inicio hasta que la pestaña vuelve a tener el foco.
- **Esc en modo chat descarta un seguimiento a medio escribir** en Inicio (vuelve a la portada sin guardar el borrador).
- **Interacciones ya no tiene búsqueda de texto** (la lista pagina en el servidor). Si hace falta, va en el backend.
- **Código muerto:** se borraron `TodayPanel` y `ActivityPanel`. Quedan exports sin uso en `src/lib/today-queue.ts`, `today.ts` y `activity-authors.ts`, `activity-feed.ts` solo lo usa su test, y `next-themes` sigue como dependencia sin usar.
- **Modo oscuro, mejoras:** los bordes quedan por debajo de 3:1 (en claro también); tres textos con opacidad reducida (`foreground/40` en el reproductor, `muted-foreground/50` y `/60`) siguen por debajo de 4,5:1 en oscuro, y ya lo estaban en claro; el logotipo se invierte con un filtro CSS y necesita un asset claro.
