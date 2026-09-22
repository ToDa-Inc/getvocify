# Informe F11

Estado: el resumen posterior distingue los estados. No está cerrado.

## Entregado

| Pieza | Prueba |
|---|---|
| Buzón y no respuesta quedan `skipped` y no esperan | `tests/coaching/test_briefs.py` |
| Objeciones listas sin score: `partial`, como máximo tres evidencias, sin fortaleza inventada | el mismo archivo |
| Sin playbook: `unavailable` y no se copia un consejo genérico. Error de job: `failed`, no se queda en `pending` | el mismo archivo |
| Un score de otra revisión no se mezcla con los patrones vigentes | el mismo archivo, 4 passed |

| Cambiar el destaque no borra un resumen listo; aplazar 30 minutos no retrasa el trabajo; una revisión vieja no pisa la nueva | `tests/coaching/test_brief_preferences.py` 3 passed; migración `047` |
| Preferencias de destaque persisten en `brief_preferences` (upsert por `user_id`); lectura fallida cae a memoria sin 500 | `tests/coaching/test_brief_preferences.py` |

| El resumen parcial y el listo comparten revisión; sin audio la cita sigue y no hay reproducción; un fallo no inventa secciones | `src/lib/post-brief.test.ts` 3 passed; `tsc --noEmit` |
| Reproducir tramo busca el audio del memo en el offset de la evidencia | `src/lib/post-brief.test.ts` |

| GET brief aplica la preferencia de destaque sin tocar status ni secciones; `not_started` no inventa `highlight` | `tests/coaching/test_brief_http.py` |
| «Se destaca a las …» usa la zona de la preferencia (`highlight.timezone`), no la del navegador; inmediato sin línea extra | `src/lib/post-brief.test.ts` |

| Tras guardar score, `publish_memo_score` materializa fila en `post_interaction_briefs` vía `store_memo_score` (buzón `skipped`; misma revisión no duplica fila) | `tests/coaching/test_briefs.py` |

## No verificado

- Si todavía no hay fila, el memo muestra «El resumen todavía no está listo» y no dice que falte el proceso ni que el trabajo esté en curso. La preferencia de destaque está en Ajustes → Resúmenes.
- La sección del resumen en el memo siempre está en el DOM: carga y error muestran solo el título (`postBriefFetchTitle`); con datos, el mismo `briefSurface` de antes.
