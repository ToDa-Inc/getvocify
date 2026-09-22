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

## No verificado

- Un miembro todavía no recibe 403 en un endpoint de equipo: no hay API.
- No hay página de equipo ni barras. El chat no está limitado.
