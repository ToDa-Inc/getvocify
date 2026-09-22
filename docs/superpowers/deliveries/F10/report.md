# Informe F10

Estado: la nota humana se guarda antes de tener memo. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Misma `annotation_id` es una nota; el reintento no mueve el `offset_ms`; una revisión vieja responde conflicto; otro autor no pisa el texto | `tests/intelligence/test_annotations.py` |
| `PUT /captures/{id}/annotations/{annotation_id}` | el mismo archivo |
| Migración `044` con notas y patrones | Postgres aislado: una de dos revisiones gana y el offset sigue en 134000 |
| Un obstáculo no es una objeción de venta; la nota de ironía no se atribuye al prospecto; la revisión nueva sustituye la frecuencia | `tests/intelligence/test_patterns.py` 4 passed |
| La revisión dice «no se detectaron» solo con lectura completa y vacía; una nota sin turno no se reproduce; categoría, tipo y resolución en español sin tocar claves | `src/lib/interaction-objections.test.ts` 3 passed; `tsc --noEmit` |
| `InteractionObjections` y `CoachingScore` renderizan todo el copy visible desde `product-catalog.ts` (EN/ES vía `t.product`) | revisión de componentes |
| La nota en la extensión guarda el `offset_ms` del audio en revisión cuando hay reproducción | `shared/ui/note.test.js` |
| F03 | Suspendida en `docs/superpowers/deliveries/F03/report.md`. No hay código de preparación. |

## No verificado

- El `PUT` guarda la nota en `interaction_annotations`. Una revisión vieja no cambia el texto ni el `offset_ms`.
- El detalle del memo lee `GET /memos/{id}/objections`. Una fila sustituida no se muestra. Sin filas no se afirma que no hubo objeciones.
- La extracción guarda las objeciones como patrones. Una extracción posterior sin ellas deja de contarlas. Otro patrón no se toca.
- La revisión de la extensión tiene el campo de nota. El escritorio no tiene esa pantalla.
