# Informe F15

Estado: una venta de equipo no se atribuye dos veces. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Un deal con dos responsables y ninguno principal cuenta una vez, sin atribución | `tests/team_insights/test_outcomes.py` |
| Cambiar el responsable añade una observación y no reescribe el informe ya guardado | el mismo archivo |
| EUR y USD no se suman | el mismo archivo |
| Migración `049`: repetir la misma observación no duplica; una posterior se conserva | Postgres aislado, 3 passed |

No se inventa un estado anterior si no hay historia.

| Dos comerciales 1/1 y 1/9 dan 2/10, no la media de sus porcentajes | `tests/team_insights/test_aggregate.py` |
| La actividad del equipo cuenta solo la semana Madrid en curso; sin `observed_at` no entra | el mismo archivo |
| La adherencia del equipo suma solo scores con `created_at` en la semana Madrid en curso; semana vacía → null | el mismo archivo |
| Un miembro recibe 403 sin cifras. El texto del chat no amplía el filtro | `tests/team_insights/test_permissions.py` |

| Los nombres van por orden alfabético. Un filtro vacío no es un cero. Sin cobertura, la tasa de cierres no se calcula. Un miembro no ve cifras | `src/lib/team-insights.test.ts` 2 passed; `tsc --noEmit` |

| Objeciones activas por categoría en `GET /team/adherence`; superseded y obstacle no cuentan; claves estables (`price`, …) y solo semana Madrid (`observed_at`/`created_at`); etiquetas de equipo y memo salen del catálogo EN/ES | `tests/team_insights/test_objections.py` |
| Textos de equipo, resumen post-interacción y objeciones en memo salen de `product-catalog.ts` (EN/ES vía `t.product`); libs reciben el catálogo como argumento | `src/lib/team-insights.test.ts`, `src/lib/post-brief.test.ts`, `src/lib/interaction-objections.test.ts` |
| La página de equipo lista nombres de categoría en el idioma de la app o «No hay objeciones esta semana.»; sin claves crudas, ceros ni ranking | `src/lib/team-insights.test.ts` |
| Objeciones por recuento (barra + número) y adherencia con barra met/applicable cuando hay datos | `src/lib/team-insights.test.ts` |

## Muestra pequeña y cobertura CRM (2026-09-22)

`GET /team/adherence` expone `sample_limited` cuando la semana Madrid tiene entre una y cuatro conversaciones puntuadas (cero no cuenta como limitada); la página muestra «Con menos de cinco conversaciones no hay conclusión.» junto a los recuentos de adherencia. La cobertura de cierres CRM solo se infiere de `crm_coverage` (`complete`/`partial`), no del `coverage` de pasos del playbook. Pruebas: `tests/team_insights/test_aggregate.py` y `src/lib/motion-label.test.ts`.

`GET /team/adherence` rellena `crm_coverage`, `won`, `lost` y `unresolved_wins` desde `team_outcome_observations` (última observación por deal; lectura fallida o vacía → no disponible, no cero). Prueba: `tests/team_insights/test_adherence_crm_outcomes.py`.

## Filtros compartidos (2026-09-22)

`GET /team/adherence` comparte `user_id` y `motion` entre actividad, adherencia y objeciones; sin parámetros mantiene el agregado de empresa. La respuesta incluye `reps` ordenados por nombre (`es`), la página `/dashboard/insights` expone Comercial y Tipología con los mismos query params, y un miembro sigue en 403 antes de cualquier cifra. Pruebas: `tests/team_insights/test_adherence_filters.py` y `src/lib/team-insights.test.ts`.

## No verificado

- La página está en `/dashboard/insights`. No se recorrió en el navegador. La gestión de miembros sigue en Ajustes.
- La actividad del periodo llega en `GET /team/adherence` (`attempts`, `connected`, `meetings`); la vista lista muestra intentos, conversaciones y reuniones con `TeamOverview` (`activityLabel`: ausente → «No disponible», cero real → «0»). La política de base de datos no está en la migración.
- `get_team_metrics` rechaza a un miembro antes de armar cifras. El texto no amplía el filtro. No está comprobado el recorrido de WhatsApp de punta a punta.
