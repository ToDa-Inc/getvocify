# Informe F0 / F0.1

Estado: contrato C04 y cola C05 empezados en `feat/vocify-v1`. No cerrado: al arrancar, el proceso llama a `install_intelligence_tick()` sin clasificador, así que no ejecuta `claim_memo_job`. El tick de base ya reclama y publica en la misma pasada cuando hay clasificador y `INTELLIGENCE_WORKER_PUBLISH`; sin fila no clasifica, y sin memo no publica.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| `IntelligenceV1` opcional; `null` no es `false`; cita fuera de la fuente no cuenta | `b1f8d9e` | `tests/intelligence/test_contracts.py` |
| `classify_questions`; silencio de Jev es `unknown`; el final de una transcripción larga se conserva | `4459ab7` | `tests/intelligence/test_classification.py` |
| `memo_jobs`, un claim, lease vencido no publica, revisión vieja no pisa la nueva | `c5a0599` | `tests/intelligence/test_jobs.py` contra PostgreSQL |
| Encolado tras extracción, reextracción y WhatsApp; barrido de un trabajo perdido | `4561e9b` | `tests/intelligence/test_recovery.py` |
| Misma revisión no se interpreta dos veces | `acdb98e` | `tests/intelligence/test_interpret.py` |
| Claim vacío no clasifica; memo ausente no publica; job y run van juntos a `publish_memo_job` | este commit | `tests/intelligence/test_recovery.py` |

## Siguiente

Pasar un clasificador real a `install_intelligence_tick` y activar `INTELLIGENCE_WORKER_PUBLISH` solo cuando ese clasificador llame a Jev. Hasta entonces el arranque no reclama trabajos.
