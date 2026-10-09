# Informe F11

Estado: **DONE** — las ocho casillas del DoD (plan §151–167) están marcadas con prueba.

## Criterios DoD → prueba

| Criterio | Evidencia |
|---|---|
| Llamada siguiente mientras el brief procesa | `test_deferred_highlight_does_not_delay_brief_processing` (`enqueue_brief` → `available_at: now`; destaque aplazado no toca `waiting`) |
| Cambiar preferencia modifica el destaque | `test_changing_preference_updates_highlight_time_on_read`, `test_changing_the_preference_keeps_a_ready_brief`, `test_member_saves_deferred_and_reads_it_back`; `post-brief.test.ts` (línea de destaque / inmediato) |
| Reinicio del trabajador no deja pending indefinido | `test_terminal_brief_states_never_wait_forever`, `test_store_coaching_from_job_payload_persists_score_and_brief` (`waiting: false`), `test_restart_logs_kind_status_and_revision_without_the_transcript` |
| No conclusiones de revisión antigua | `test_an_old_score_is_not_mixed_with_the_current_revision`, `test_get_brief_uses_the_highest_revision_row`, `test_a_late_older_brief_does_not_replace_the_current_one`, `test_postgres_keeps_the_newer_brief_when_an_older_one_finishes_late` |
| Cada mejora incluye evidencia | `test_improvement_is_omitted_without_evidence_sections` + `_evidence_backed_coaching` en `briefs.py` |
| Contenido breve y utilizable | `test_ready_brief_keeps_one_coaching_line_and_three_evidence_refs` |
| Seis estados visuales; buzón → `skipped` | `post-brief.test.ts` («maps six API statuses…»), `test_a_missing_row_is_not_a_running_job_or_a_missing_playbook` |
| Parcial/retry/audio sin reproducción ficticia | `test_ready_objections_without_a_score_stay_partial`, `retryBrief` + cita sin audio en `post-brief.test.ts` |

## Bloqueadores (no aplican al DoD §151–167)

- **Reticle / navegador:** no se ejecutó `reticle_act_and_wait` sobre `PostInteractionBrief.tsx` (requiere sesión web). Los seis estados se cubren con `post-brief.test.ts` + backend.
- **`INTELLIGENCE_WORKER_PUBLISH`:** permanece desactivado; la recuperación se demostró con tests unitarios del worker (`test_restart_logs…`) y el hook `store_coaching_from_job_payload`, no contra un worker publicando en vivo.

## Comandos de cierre (ejecutados)

- `cd backend && .venv/bin/python -m pytest tests/coaching/test_briefs.py tests/coaching/test_brief_preferences.py tests/coaching/test_brief_http.py tests/coaching/test_brief_preferences_http.py tests/intelligence/test_score_store_hook.py tests/intelligence/test_recovery.py::test_restart_logs_kind_status_and_revision_without_the_transcript -q` → 29 passed
- `node --test src/lib/post-brief.test.ts` → 8 passed
- `npm run build` → ok

## Nota menor (fuera de casillas DoD)

- `PostInteractionBrief.tsx` aún muestra el literal «Reproducir tramo» en el botón de audio; no hay clave en `product-catalog` en este cierre.
