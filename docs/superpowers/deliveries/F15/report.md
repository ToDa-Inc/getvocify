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
| Un miembro recibe 403 sin cifras. El texto del chat no amplía el filtro | `tests/team_insights/test_permissions.py` |

| Los nombres van por orden alfabético. Un filtro vacío no es un cero. Sin cobertura, la tasa de cierres no se calcula. Un miembro no ve cifras | `src/lib/team-insights.test.ts` 2 passed; `tsc --noEmit` |

## No verificado

- La página está en `/dashboard/insights`. No se recorrió en el navegador. La gestión de miembros sigue en Ajustes.
- La actividad del periodo no llega a esa página, así que no se pintan intentos en cero. La política de base de datos no está en la migración. El chat de WhatsApp no usa el filtro nuevo.
