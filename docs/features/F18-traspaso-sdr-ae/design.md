# Design · F18–F21 — Hoy por rol

Las cuatro piezas comparten `SALES_ROLES_ENABLED`. Apagado, no cambian F16.

## Carriles

`backend/app/services/hoy/lanes.py`

- `ended` → no se muestra.
- `booked` → carril `meetings`.
- cualquier otro estado, incluido vacío → carril `calls`.

Quién ve qué (`visible_lanes(sales_role, permission)`):

| Permiso | Rol | Carriles |
|---|---|---|
| owner, admin | cualquiera | calls, meetings |
| member | sdr | calls |
| member | ae | meetings |
| member | general u otro | calls, meetings |

`keep(lane, lanes)` es falso si el carril es `None`.

Motions (`motions_for(sales_role, permission)`):

| Quién | Motions |
|---|---|
| owner, admin, general | discovery, qualification, closing |
| sdr | discovery, qualification |
| ae | closing |

El mismo criterio en `src/lib/hoy-lanes.ts` para pintar. La API manda; el cliente solo agrupa.

## API

`GET /today` y `GET /contact-priorities`, solo con el flag encendido:

- Cada ítem lleva `lane`: `calls` o `meetings`.
- Se descartan los que el viewer no puede ver.
- La cola de llamadas (`candidates`) es solo `calls`. Las reuniones van en `meetings` en la misma respuesta.
- Owner/admin: las señales se leen por `company_id`, no por `user_id`, y cada ítem lleva `rep_name` (nombre del miembro, o el email si no hay nombre). Un member sigue filtrado por su `user_id`.
- La reunión incluye `booking_memo_id` de la nota más reciente de la empresa con ese `contact_id`, si existe.

Tope: 7 por carril.

## UI

En el panel de Hoy, si la respuesta trae los dos carriles o el usuario es Ambos/admin, dos títulos: «Llamadas» y «Reuniones» (`todayLaneCalls`, `todayLaneMeetings` en el catálogo, es y en). Un solo carril no añade título. Peso igual al bloque de Hoy que ya existe; no hay pantalla nueva.

Proceso filtra los motions con `motions_for`. El bloque de etapas no se mueve.

## Captura

Si el flag está encendido y el body no trae `sales_motion_key`, `captures` guarda el primer motion de `motions_for` para un SDR o un AE. Ambos, owner y admin no reciben uno por defecto.
