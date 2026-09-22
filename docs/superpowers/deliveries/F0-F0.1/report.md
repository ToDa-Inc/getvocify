# Informe F0 / F0.1

Estado: contrato C04 y cola C05 empezados en `feat/vocify-v1`. No cerrado: el worker no reclama todavía filas de `memo_jobs` en el proceso de la API, porque no hay driver de PostgreSQL en la aplicación. El claim atómico está probado con `psql`.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| `IntelligenceV1` opcional; `null` no es `false`; cita fuera de la fuente no cuenta | `b1f8d9e` | `tests/intelligence/test_contracts.py` |
| `classify_questions`; silencio de Jev es `unknown`; el final de una transcripción larga se conserva | `4459ab7` | `tests/intelligence/test_classification.py` |
| `memo_jobs`, un claim, lease vencido no publica, revisión vieja no pisa la nueva | `c5a0599` | `tests/intelligence/test_jobs.py` contra PostgreSQL |
| Encolado tras extracción, reextracción y WhatsApp; barrido de un trabajo perdido | `4561e9b` | `tests/intelligence/test_recovery.py` |
| Misma revisión no se interpreta dos veces | este commit | `tests/intelligence/test_interpret.py` |

## Siguiente

Conectar `interpret_memo` al claim real cuando el proceso pueda ejecutar `claim_memo_job`, y registrar el handler para que el resultado se publique con `publish_memo_job`.
