# Spec · F17 — Cuentas de SDR y AE, creadas por el head of sales

> Pieza 2 de 6 del bloque «procesos SDR / AE / General». La 1 es F16 (el estado del CRM manda en la cola). Las siguientes (traspaso SDR → AE, Hoy por rol, playbook y feedback por proceso, vista de head of sales) tienen su propio spec.

## 1. Job to be done
El head of sales quiere dar de alta a su equipo diciendo qué hace cada uno —prospectar, cerrar, o las dos cosas— para que Vocify le hable a cada comercial de su trabajo y no del de otro.

## 2. Audiencia y mensaje
- [x] Head of sales. Mensaje: «tu equipo, tal y como lo tienes montado».
- El comercial no elige su rol ni lo ve como una decisión suya: lo ve como un dato de su cuenta.

## 3. Decisión de producto que esta pieza fija
**Los roles SDR, AE y head of sales son de Vocify, no del CRM.** HubSpot y Pipedrive no tienen ese concepto y Vocify nunca lo deduce de ellos. El head of sales los asigna al crear cada cuenta. El correo de la invitación es el mismo que esa persona usa en el CRM: eso sirve para emparejar al usuario con su propietario en el CRM (ya existe hoy), no para averiguar su rol.

## 4. Vocabulario
| Concepto | Dónde vive | Valores |
|---|---|---|
| Permiso | `company_members.role` (ya existe) | `owner`, `admin`, `member` |
| Rol comercial | `company_members.sales_role` (nuevo) | `sdr`, `ae`, `general` |

Son independientes. El head of sales es `owner` o `admin`; su rol comercial suele ser `general`, y puede no llamar nunca. Un `member` puede ser `sdr` o `ae`.

## 5. Métrica de calidad (decide el GA)
| Métrica | Umbral para GA | Cómo se mide |
|---|---|---|
| Cuentas del equipo con rol comercial asignado a propósito (no por defecto) | 100 % en las empresas con el flag | Consulta sobre `company_members` tras el alta |
| Comerciales que ven su rol mal puesto | 0 | Dogfooding: cada miembro confirma el rol que aparece en Equipo |

## 6. Comportamiento

### Invitar a alguien (Equipo, solo owner/admin)
1. Junto al permiso que ya se elige hoy (miembro / administrador), el head of sales elige el rol comercial: **SDR**, **AE** o **Ambos**.
2. Por defecto viene **Ambos**, que es cómo se comporta Vocify hoy.
3. La invitación guarda el rol comercial. Al aceptarla, la cuenta nace con él.
4. El email de invitación no cambia. El rol no se le pregunta a quien acepta.

### Equipo, después del alta
1. Cada miembro aparece con su rol comercial junto al permiso.
2. El owner o el admin puede cambiarlo sin tocar el permiso, y al revés.
3. Un miembro ve la lista y su propio rol, pero no puede cambiar ninguno.

### Cuentas que ya existen
1. Al encender el flag, todas las cuentas quedan en **Ambos**. Nadie cambia de comportamiento.
2. El head of sales las va cambiando desde Equipo cuando quiere.

### Lo que el rol hace en esta pieza
Se guarda y se muestra, y la app lo expone en la sesión (`/auth/me`) para que las piezas siguientes lo usen. **En esta pieza no cambia ninguna cola, ningún Hoy, ningún playbook ni ninguna visibilidad de notas.** Un SDR y un AE ven hoy exactamente lo mismo que antes.

### Edge cases
| # | Caso | Comportamiento esperado |
|---|---|---|
| E1 | Flag apagado | No hay selector en Equipo, la API no devuelve el rol y nada lee la columna |
| E2 | Empresa antigua al encender el flag | Todos en `general`; ningún comportamiento cambia |
| E3 | Invitación creada antes del flag y aceptada después | La cuenta nace en `general` |
| E4 | Valor desconocido en la columna (dato manipulado) | Se trata como `general`; nunca rompe la sesión |
| E5 | Un `member` intenta cambiar el rol de otro por API | 403, mismo guard que el cambio de permiso |
| E6 | Un `admin` cambia el rol comercial del `owner` | Permitido: el rol comercial no es un permiso |
| E7 | El owner se pone a sí mismo `sdr` | Permitido; sigue siendo owner |
| E8 | Invitación con rol comercial inválido | 400 al crearla, con el valor rechazado |
| E9 | Cambiar el rol comercial de un miembro `disabled` | Permitido; no lo reactiva |
| E10 | Dos administradores cambian el mismo miembro a la vez | Gana la última escritura; la lista se refresca tras guardar |
| E11 | El correo del miembro no existe como propietario en el CRM | El rol se asigna igual; el emparejamiento con el CRM es independiente y ya avisa por su cuenta |
| E12 | Quitar a un miembro | Se borra su fila; el rol se va con ella |

## 7. Fuera de alcance
- Traspaso del contacto del SDR al AE (pieza 3, usa los estados de F16).
- Hoy, cola, playbook, feedback y captura distintos por rol (piezas 3-5).
- Vista de head of sales con todo el equipo (pieza 6).
- Un asistente de onboarding con pasos. El alta sigue siendo la pantalla de Equipo que ya existe.
- Cualquier lectura del rol desde HubSpot, Pipedrive o Salesforce.
- Roles nuevos más allá de estos tres.

## 8. Prompts
Ninguno. Esta pieza no genera texto con IA.
