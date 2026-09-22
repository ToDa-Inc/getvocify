# Informe F05

Estado: el motor puro de señales está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `signals_for_contact`, `rank_cards`, `reconcile`, `reason`, `due_label` con los umbrales de S: 10 días, siete tarjetas, un compromiso futuro calla el enfriamiento | `tests/hoy/test_signals.py` |
| Una objeción `resolved` o un interés desconocido no abre tarjeta, aunque quede texto legacy | el mismo archivo |

`rank_cards` no sustituye a `rank_candidates` de F04.

## No verificado

- No hay migración `043`, ni persistencia, ni `GET /today`, ni panel en el inicio.
- F04 sigue abierta: el recorrido de páginas no usa el token de la conexión, y el inicio no se recorrió en el navegador.
