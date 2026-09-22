# Informe F15

Estado: una venta de equipo no se atribuye dos veces. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Un deal con dos responsables y ninguno principal cuenta una vez, sin atribución | `tests/team_insights/test_outcomes.py` |
| Cambiar el responsable añade una observación y no reescribe el informe ya guardado | el mismo archivo |
| EUR y USD no se suman | el mismo archivo |
| Migración `049`: repetir la misma observación no duplica; una posterior se conserva | Postgres aislado, 3 passed |

No se inventa un estado anterior si no hay historia.

| Dos comerciales 1/1 y 1/9 dan 2/10, no la media de sus porcentajes | `tests/team_insights/test_aggregate.py` |
| La actividad del equipo cuenta solo la semana Madrid en curso; sin `observed_at` no entra | el mismo archivo |
| La adherencia del equipo suma solo scores con `created_at` en la semana Madrid en curso; semana vacía → null | el mismo archivo |
| Un miembro recibe 403 sin cifras. El texto del chat no amplía el filtro | `tests/team_insights/test_permissions.py` |

| Los nombres van por orden alfabético. Un filtro vacío no es un cero. Sin cobertura, la tasa de cierres no se calcula. Un miembro no ve cifras | `src/lib/team-insights.test.ts` 2 passed; `tsc --noEmit` |

| Objeciones activas por categoría en `GET /team/adherence`; superseded y obstacle no cuentan; etiquetas ES y solo semana Madrid (`observed_at`/`created_at`) | `tests/team_insights/test_objections.py` |

## No verificado

- La página está en `/dashboard/insights`. No se recorrió en el navegador. La gestión de miembros sigue en Ajustes.
- La actividad del periodo llega en `GET /team/adherence` (`attempts`, `connected`, `meetings`); la página ya no pinta intentos en cero cuando esos campos faltan. La política de base de datos no está en la migración.
- `get_team_metrics` rechaza a un miembro antes de armar cifras. El texto no amplía el filtro. No está comprobado el recorrido de WhatsApp de punta a punta.
