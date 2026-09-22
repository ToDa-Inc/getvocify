# Informe F0 / F0.1

Estado: contrato C04 y cola C05 verificados en `feat/vocify-v1` con tests deterministas. Cierre parcial: `INTELLIGENCE_WORKER_PUBLISH` sigue apagado por decisión (22 sep 2026), así que no se demuestra claim/clasificación en vivo en el arranque del proceso.

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
| La inteligencia queda en la extracción sin cambiar la revisión; un fallo al escribir no publica | `366897e` | `tests/intelligence/test_recovery.py` |
| Un fallo dobla la espera hasta 120 s; el log lleva kind, estado y revisión, no la transcripción; el reinicio vuelve a pasar | `fb62ac4` | `tests/intelligence/test_recovery.py` |
| DoD: criterios de contrato/recuperación marcados en el plan; regresión 48 pytest + build | (este commit) | `tests/intelligence`, `tests/crm_copilot/test_loop.py`; `npm run build` |

## Bloqueado por decisión

- **Arranque con publish + OpenRouter:** el criterio «Con publish encendido y clave configurada, el arranque del proceso reclama y clasifica jobs pendientes en vivo» queda sin marcar porque `INTELLIGENCE_WORKER_PUBLISH` permanece apagado. El proceso no debe reclamar jobs en arranque salvo que el flag y una clave OpenRouter estén ambos configurados; con el flag off, `install_intelligence_tick` deja `_worker_tick` en `None` (probado).

## Siguiente

Activar `INTELLIGENCE_WORKER_PUBLISH` solo en el proceso que deba consumir la cola y repetir el criterio de arranque en vivo con clave configurada. Hasta entonces la entrega queda **BLOCKED** en ese único criterio.
