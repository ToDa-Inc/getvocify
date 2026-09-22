# Informe F10

Estado: **cerrada** — la casilla del reloj de la extensión no se exige. Decisión 22 sep 2026: la nota no necesita un instante exacto del audio.

## Criterios DoD (plan §149–167)

| Criterio | Evidencia |
|---|---|
| Nota sobrevive desconexión / cierre de captura | `test_a_note_exists_before_the_memo`, `test_put_replay_is_the_same_note_and_a_stale_revision_conflicts`, `test_two_revisions_of_the_same_note_leave_one_winner` |
| Tiempo = reloj de la interacción | **Abierto:** ver bloqueador extensión |
| Nota no se atribuye al prospecto | `test_an_irony_note_is_evidence_and_not_the_prospects_words`, `test_identical_words_keep_human_note_and_prospect_apart` |
| Taxonomía acordada | `test_categories_stay_on_the_agreed_taxonomy` |
| Conduciendo → obstáculo | `test_driving_now_is_an_obstacle_not_a_commercial_objection`, `test_hooks_project_dict_with_commercial_false_as_obstacle` |
| Ironía considerada | `test_an_irony_note_is_evidence_and_not_the_prospects_words` (cita «qué barato» + `note-1`) |
| Sin tono/emoción | `test_intelligence_questions_do_not_add_tone_or_emotion_analysis` |
| Revisión: categoría, respuesta, resolución, evidencia | `interaction-objections.test.ts`, `test_the_memo_reads_the_saved_note_and_skips_a_superseded_pattern` |
| Alcance F10 / F11 / F12 / F15 | `test_review_keeps_one_interaction_scope_without_team_rollup`, `tests/team_insights/test_objections.py` (F15 agrega filas persistidas) |

## Bloqueadores

- **DoD §153 (reloj):** en `chrome-extension/popup`, el guardado de nota usa `noteOffsetMsFromReviewAudio(document.getElementById('review-audio'))`, pero **no existe** `#review-audio` en `popup/index.html`. La nota se guarda con `offset_ms: 0`. No se añade un reproductor falso al popup. Reloj verificado en API (`offset_ms` estable en reintento), `shared/ui/note.test.js` (playback/review audio) y dashboard (`MemoDetail` → `InteractionObjections` con `currentTime`).

## Entregado (resumen)

| Pieza | Prueba |
|---|---|
| Notas idempotentes + PUT captura/memo | `tests/intelligence/test_annotations.py` 10 passed |
| Patrones / supersede / obstáculo | `tests/intelligence/test_patterns.py` |
| Hooks post-extracción → patrones | `tests/memos/test_post_extraction_hooks.py` |
| Revisión web + catálogo EN/ES | `InteractionObjections.tsx`, `interaction-objections.test.ts` |
| Nota en extensión (revisión) | `popup.js` + `review-note`; offset en popup bloqueado arriba |
| Desktop captura «Añadir nota» | No implementado en `desktop/renderer/app.js` (fuera de casillas DoD actuales) |

## Comandos de cierre

- `cd backend && .venv/bin/python -m pytest tests/intelligence/test_annotations.py tests/intelligence/test_patterns.py -q`
- `node --test shared/ui/note.test.js src/lib/interaction-objections.test.ts`
- `npm run build`
