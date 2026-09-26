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
4. **Permiso de emails en HubSpot (`sales-email-read`).** Sin él, la tarjeta de Hoy «no te ha respondido» (`HOY_NO_REPLY_ENABLED`) nunca sale y Ask tampoco puede leer el contenido de los emails. Ya está como opcional en `hubspot-app/src/app/app-hsmeta.json` y en `HUBSPOT_OPTIONAL_SCOPES` (commit local, sin subir). Orden:
   1. `cd hubspot-app && hs project upload` (cuenta de desarrollador de HubSpot).
   2. Después, push del commit y merge a producción.
   3. Cada cliente pulsa «Refresh permissions» en Integraciones (nunca desconectar: borra su configuración CRM).
   En Pipedrive haría falta `mail:read`.
