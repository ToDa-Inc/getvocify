# Informe F09

Estado: la adherencia determinista está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `compute_adherence`: unknown no es fallo; `not_applicable` queda fuera; sin pasos aplicables la adherencia es null y no hay `value` | `tests/coaching/test_metrics.py` |
| Agregar equipos suma conteos, no promedia porcentajes | el mismo archivo, 3 passed |
| Sin playbook o cita inexistente no hay nota; el mismo evidencia con deal ganado o perdido conserva `value` y adherencia; una revisión vieja no pisa la guardada | `tests/coaching/test_scoring.py` 4 passed; migración `045` |

## No verificado

- `GET /memos/{id}/score` devuelve la nota guardada y no la recalcula. La tarjeta muestra fortaleza y mejora antes del número. `src/lib/coaching-score.test.ts` 2 passed; `tsc --noEmit`.
- No hay un conjunto de 20 conversaciones anotadas. No se inventa. El ensamblado no llama a un modelo. La pantalla no se recorrió en el navegador.
