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

| El resumen parcial y el listo comparten revisión; sin audio la cita sigue y no hay reproducción; un fallo no inventa secciones | `src/lib/post-brief.test.ts` 3 passed; `tsc --noEmit` |

## No verificado

- La preferencia no está en Ajustes. El memo pide el resumen, pero no hay filas, así que el bloque no aparece. No se recorrió en el navegador.
- El botón de reproducir no mueve el audio. El trabajo no se encola desde el score, los patrones o la reunión.
