# Pendientes (26 sep 2026)

Quedan de la corrección de errores de la revisión reunión-vs-código.

1. ~~**Recargar OpenRouter y correr evals.**~~ Hecho el 26 sep: C04 16/16 en tres pasadas, F07 15/15 en dos.
2. ~~**Commitear.**~~ Hecho en `staging` por tema. Falta desplegar a producción (merge a `main`) cuando se haya revisado staging. Migraciones 050–053 ya ejecutadas.
   **Email diario:** va detrás de `REPORTING_DAILY_EMAIL_ENABLED`, apagado para todos. Encenderlo por empresa cuando se haya revisado el flujo.
   **Etapa del deal:** con `DEAL_STAGE_CONFIRM_ENABLED` el comercial confirma la etapa en la revisión de la nota y aceptar una reunión ya no la mueve. Apagado para todos. El cambio en la extensión (`review-insights.js`) necesita publicar una versión nueva.
3. **Encender la inteligencia** después de desplegar. Sin ella no funcionan la prioridad 1 («confirmó el problema»), la reunión detectada por el modelo ni la etapa sugerida. Se enciende por empresa (ver `docs/features/MASTER_PLAN.md`, «Activar un flag para un cliente»):

   ```sql
   INSERT INTO company_feature_flags (company_id, flag, enabled)
   VALUES ('<company_id>', 'INTELLIGENCE_EXTRACT_ENABLED', true)
   ON CONFLICT (company_id, flag) DO UPDATE SET enabled = true, updated_at = NOW();
   ```

   Los memos antiguos solo la tendrán si se corre `scripts/backfill_intelligence.py <user_id> [limit]`, que tiene coste de LLM. Probar antes con pocos memos.
4. **Permiso de emails en HubSpot (`sales-email-read`).** Sin él, la tarjeta de Hoy «no te ha respondido» (`HOY_NO_REPLY_ENABLED`) nunca sale y Ask tampoco puede leer el contenido de los emails. Añadirlo primero en la configuración de la app en el portal de desarrollador de HubSpot (si solo se añade en `HUBSPOT_OAUTH_SCOPES` y no en la app, el OAuth falla para todos). Después, añadirlo en `backend/app/services/hubspot/oauth.py` y que cada cliente reconecte HubSpot. En Pipedrive haría falta `mail:read`.
