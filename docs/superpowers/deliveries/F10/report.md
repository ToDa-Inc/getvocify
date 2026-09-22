# Informe F10

Estado: la nota humana se guarda antes de tener memo. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Misma `annotation_id` es una nota; el reintento no mueve el `offset_ms`; una revisión vieja responde conflicto; otro autor no pisa el texto | `tests/intelligence/test_annotations.py` |
| `PUT /captures/{id}/annotations/{annotation_id}` | el mismo archivo |
| Migración `044` con notas y patrones | Postgres aislado: una de dos revisiones gana y el offset sigue en 134000 |
| F03 | Suspendida en `docs/superpowers/deliveries/F03/report.md`. No hay código de preparación. |

## No verificado

- El `PUT` de la ruta vive en memoria del proceso. La revisión condicional de Postgres está en `revise_statement`, no la llama la ruta.
- No hay clasificación de patrones ni la nota en la revisión de la web, el desktop o la extensión.
