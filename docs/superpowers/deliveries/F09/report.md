# Informe F09

Estado: la adherencia determinista está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `compute_adherence`: unknown no es fallo; `not_applicable` queda fuera; sin pasos aplicables la adherencia es null y no hay `value` | `tests/coaching/test_metrics.py` |
| Agregar equipos suma conteos, no promedia porcentajes | el mismo archivo, 3 passed |

## No verificado

- No hay migración `045`, ni rúbrica, ni `GET` de score, ni la tarjeta en el memo.
- No se ha comprobado que un resultado de CRM no cambie la nota: todavía no existe `value`.
