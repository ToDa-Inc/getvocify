# Spec · <ID> — <Nombre de la feature>

> Máx 2 páginas. Si necesita más, la feature es demasiado grande: partir.

## 1. Job to be done
Una frase: "Cuando [situación], el [rep / head of sales] quiere [resultado] para [beneficio]."

## 2. Audiencia y mensaje
- [ ] Rep («solo vendes») / [ ] Head of sales («tu método, tu visibilidad») / [ ] Ambos
- Cómo se anuncia esta feature en 1 frase de marketing:

## 3. Métrica de calidad (decide el GA)
| Métrica | Umbral para GA | Cómo se mide |
|---|---|---|
| ej.: % follow-ups enviados sin editar | ≥ 60% v1 | evento `email_sent` con diff vs. draft |

## 4. Comportamiento
### Flujo principal (happy path)
1. …

### Edge cases (enumerar TODOS los conocidos)
| Caso | Comportamiento esperado |
|---|---|
| Audio inservible / STT falla | |
| Contacto no existe en CRM | |
| Interaction en otro idioma | |
| Duplicado / re-proceso | |

## 5. Qué NO hace la v1 (recorte explícito)
- …

## 6. Dependencias
- Pipeline: ¿qué campos de `extracted` necesita? ¿Existen ya?
- Features previas: …
- Terceros/APIs: …

## 7. Evals (si hay LLM)
- Dataset: `backend/evals/<ID>/` — nº de casos mínimos: 20
- Criterio de corrección por campo (exacto / judge / humano)
