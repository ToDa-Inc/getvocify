# Design · F17 — Cuentas de SDR y AE

Contrato: `spec.md`. Esta pieza guarda y muestra el rol comercial. No cambia colas, Hoy, playbooks ni visibilidad.

## Datos

Migración `055_sales_roles.sql` (rollback `055_sales_roles.down.sql`). También `backend/full_reset.sql`.

```sql
sales_role TEXT NOT NULL DEFAULT 'general'
CHECK (sales_role IN ('sdr', 'ae', 'general'))
```

En `company_members` y en `company_invitations`. Las filas que ya existen quedan en `general`.

`role` (owner | admin | member) no se toca. El head of sales es quien tiene `owner` o `admin`. SDR y AE son `member` con `sales_role` `sdr` o `ae`. `general` es «Ambos».

## Flag

`SALES_ROLES_ENABLED` en `backend/app/config.py`, default `false`. Override por empresa en `company_feature_flags`, leído con `is_enabled`. Una línea en `docs/features/MASTER_PLAN.md`.

Flag apagado: el JSON no incluye la clave `sales_role` (ni `null`). La UI no pinta el selector. La columna existe igual, en `general`.

Flag encendido: las respuestas de miembros, invitaciones pendientes y la sesión (`CompanySummary` en auth) incluyen `sales_role`. `GET /company/members` incluye `sales_roles_enabled: true`. Apagado, esa clave es `false` y los objetos no llevan `sales_role`.

## API

- `POST /company/invites` acepta `sales_role` opcional (`sdr` | `ae` | `general`). Sin valor, `general`. Valor inválido: 400. Flag apagado: se ignora y se guarda `general`. El email de invitación no cambia.
- `accept_invite` copia `sales_role` de la invitación. Si falta o no es uno de los tres, la cuenta nace en `general`.
- `PATCH /company/members/{member_id}/sales-role` con `{ "sales_role": "sdr"|"ae"|"general" }`. Lo pueden llamar owner y admin (`require_manage_role`), también sobre el owner y sobre sí mismos. Un `member` recibe 403. No cambia `role` ni reactiva a un `disabled`. El `PATCH` de permiso que ya existe sigue siendo solo del owner.
- Un valor leído que no sea uno de los tres se trata como `general` (`normalize_sales_role` en `backend/app/services/sales_role.py`).

## UI

`src/pages/dashboard/TeamPage.tsx`, solo si `salesRolesEnabled`.

Junto al selector de permiso que ya existe (pastillas member/admin), otro grupo igual: **SDR**, **AE**, **Ambos**. Por defecto Ambos. Cada fila de miembro y cada invitación pendiente muestran el rol comercial. Owner y admin lo cambian ahí, sin tocar el permiso. Un miembro lo ve y no lo edita.

Textos en `src/lib/product-catalog.ts` (es y en). El aviso del correo (`HUBSPOT_INVITE_EMAIL_HINT`) se queda: el correo de la invitación es el del usuario en HubSpot, y eso no asigna el rol.

Peso secundario, dentro de Equipo. Sin pantalla nueva.

## Fuera

No leer el rol de HubSpot, Pipedrive ni Salesforce. No cambiar Hoy, la cola, los playbooks ni quién ve qué notas.
