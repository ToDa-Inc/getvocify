# Informe F0 / F0.1

Estado: contrato C04 y cola C05 empezados en `feat/vocify-v1`. No cerrado: `INTELLIGENCE_WORKER_PUBLISH` sigue apagado, así que el arranque no llama a `claim_memo_job`. Con el flag y `OPENROUTER_API_KEY`, la pasada clasifica con Jev, escribe `extraction.intelligence` y publica en el mismo tick. Sin clave no reclama. Un fallo al escribir no publica. La inteligencia guardada no cambia la revisión.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| `IntelligenceV1` opcional; `null` no es `false`; cita fuera de la fuente no cuenta | `b1f8d9e` | `tests/intelligence/test_contracts.py` |
| `classify_questions`; silencio de Jev es `unknown`; el final de una transcripción larga se conserva | `4459ab7` | `tests/intelligence/test_classification.py` |
| `memo_jobs`, un claim, lease vencido no publica, revisión vieja no pisa la nueva | `c5a0599` | `tests/intelligence/test_jobs.py` contra PostgreSQL |
| Encolado tras extracción, reextracción y WhatsApp; barrido de un trabajo perdido | `4561e9b` | `tests/intelligence/test_recovery.py` |
| Misma revisión no se interpreta dos veces | `acdb98e` | `tests/intelligence/test_interpret.py` |
| Claim vacío no clasifica; memo ausente no publica; job y run van juntos a `publish_memo_job` | `9af9f3c` | `tests/intelligence/test_recovery.py` |
| Silencio de Jev sigue en unknown y la cita tardía entra en el estado; sin clave el tick no reclama | `e87aa05` | `tests/intelligence/test_classification.py`, `tests/intelligence/test_recovery.py` |
| La inteligencia queda en la extracción sin cambiar la revisión; un fallo al escribir no publica | este commit | `tests/intelligence/test_recovery.py` |

## Siguiente

Activar `INTELLIGENCE_WORKER_PUBLISH` en el proceso que deba consumir la cola. Hasta entonces el arranque no reclama trabajos.
