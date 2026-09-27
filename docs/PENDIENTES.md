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
