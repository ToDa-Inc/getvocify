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

## No verificado

- La preferencia no está en Ajustes y el resumen no está en el memo.
- El trabajo no se encola todavía desde el score, los patrones o la reunión: la función existe y deduplica, pero nadie la llama.
