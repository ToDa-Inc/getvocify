# Informe F09

Estado: la adherencia determinista está en `feat/vocify-v1`. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| `compute_adherence`: unknown no es fallo; `not_applicable` queda fuera; sin pasos aplicables la adherencia es null y no hay `value` | `tests/coaching/test_metrics.py` |
| Agregar equipos suma conteos, no promedia porcentajes | el mismo archivo, 3 passed |
| Sin playbook o cita inexistente no hay nota; el mismo evidencia con deal ganado o perdido conserva `value` y adherencia; una revisión vieja no pisa la guardada | `tests/coaching/test_scoring.py` 4 passed; migración `045` |
| `publish_memo_score` persiste la nota y llama a `store_memo_score` para materializar el brief (fallo de brief no borra la nota) | `tests/coaching/test_briefs.py` |
| El callback `store` del worker de inteligencia, si el payload trae `score`, persiste nota y brief sin reclasificar | `tests/intelligence/test_score_store_hook.py` |
| Tras clasificar, el store ensambla `score` desde extracción citada (sin LLM) y lo persiste cuando hay objeción o resumen | `tests/intelligence/test_score_assembly.py` |

## No verificado

- `GET /memos/{id}/score` devuelve la nota guardada y no la recalcula. La tarjeta muestra fortaleza y mejora antes del número. `src/lib/coaching-score.test.ts` 2 passed; `tsc --noEmit`.
- El examen de desarrollo está en `backend/evals/F09/cases.json`: llamadas, meetings, objeción, ambigüedad, error de transcripción y silencio. No entra en el producto. Una cita que no está en el texto no se usa. Una reunión fácil no supera a la objeción trabajada. El silencio no inventa nota.
