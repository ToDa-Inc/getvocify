# Vocify · Coaching coherente con el playbook (29 sep 2026)

> Aplica `vocify-ux-coherence` (SKILL.md + composition.md). Complementa `2026-09-29-playbooks-v2.md` y `2026-09-28-live-copilot-playbook.md`. Trabajo en `staging`, sin commits hasta revisión de Dani.

**Objetivo:** que el playbook sea la única vara de medir en los tres momentos (en directo, justo después y en la semana) y que el comercial reciba, justo al colgar, **una cosa que hizo bien y una que cambiar, con la frase del playbook**, en la superficie donde ya está.

**Reparto con la sesión «Post-call navigation tabs» (en paralelo):** ella construye las pestañas de la revisión (`shared/ui/components/review-tabs.js`) y monta el contenido en extensión, desktop y `MemoDetail.tsx`. Aquí se construye el contenido de la pestaña «Coaching»: backend, `<v-debrief>` (`shared/ui`) y el interior de `PostInteractionBrief.tsx`. `sync-shared.mjs` lo corre esa sesión una vez, al final.

---

## 1. Estado actual (auditado hoy)

| Superficie | Qué hay | Problema |
|---|---|---|
| Backend · C04 (`intelligence_v6.md`) | Marca cada paso met/missed/n.a./unknown contra `criterion`; `met` exige palabras del comercial | Los criterios de plantilla y del prompt de estructurar incluyen el resultado («…y el prospecto acepta»): un «no» del prospecto = paso fallado. Castiga el resultado, no la ejecución |
| Backend · score (`score_assembly.py`) | `value = round(adherence*10)` | 1 paso cumplido + 4 desconocidos = 10/10 «ready» (cobertura 20 %). Objeciones cuentan aunque el playbook no diga cómo responderlas |
| Backend · debrief (`coaching/briefs.py`) | strength, improvement, missed, phrases, progress | La mejora desaparece si la llamada no tuvo objeciones. «Cómo lo dice el playbook» enseña el criterio, nunca `example`. `next_step_agreed = bool(commitments)` |
| Backend · coaching semanal (`rep_focus.py`) | Un foco por semana | Solo `discovery` y `closing`: inbound, discovery de AE y negociación no cuentan |
| Backend · copiloto en vivo (`copilot/prompts.py`, `load_grounding.py`) | Tarjeta de objeción «respaldada» | El modelo solo recibe ids (`objection:price`), nunca la respuesta aprobada. Sin `capture_id` exige exactamente 1 playbook publicado: con v2 (varios tipos) no hay respaldo |
| Dashboard (`PostInteractionBrief.tsx`) | Debrief en `MemoDetail` | Volcado de listas sin jerarquía (`<p>`, `<h3>`, `<ul>` sin estilo). Solo sondea en `pending` |
| Extensión | Revisión tras la llamada con follow-up (`v-followup`) | No enseña coaching |
| Desktop (app nativa + dashboard embebido) | Tras Stop navega a `MemoDetail` (rama `feat/desktop-meeting-recorder`) | Recibe el mismo debrief que el dashboard; el checklist «0 de N» solo existe en la UI SwiftUI legacy (`VOCIFY_USE_LEGACY_UI=1`) |

## 2. Recorrido

1. **Durante la llamada** (atención mínima, mirada de reojo): solo una línea cuando el prospecto objeta **y** el playbook tiene respuesta. ★ Crítico: nunca una tarjeta «del playbook» que no lo es.
2. **Al colgar** (prisa, siguiente llamada): revisa CRM y follow-up. El coaching llega unos segundos después, sin pedirlo. ★ Crítico: leerlo en 3 s. Un acierto, un cambio, la frase para la próxima.
3. **En la semana** (Coach): un foco. El debrief de cada llamada lo nombra cuando toca («Foco de la semana»), así el día a día y la semana dicen lo mismo.

## 3. Diseño

### 3.1 El bloque `coach` (lo decide el backend, las superficies solo pintan)

```
coach: {
  kept: {step_id, label, quote} | null,          // el foco si se cumplió; si no, el primer paso cumplido con cita
  fix:  {kind: "step"|"objection", id, label, criterion, say, focus} | null,
  progress: [adherencia…]                        // últimas 5 del mismo tipo (ya existe como `progress`)
}
```

Prioridad de `fix`: (1) el paso foco de la semana si se falló, (2) el primer paso fallado en el orden del playbook, (3) una objeción con respuesta en el playbook que quedó sin responder. `say` = `example` del paso o `guidance` de la objeción; nunca el criterio. Solo con `DEBRIEF_V2_ENABLED` (igual que el resto de v2).

### 3.2 Tarjeta (misma en dashboard, extensión y desktop)

```
Coaching                                           ○ ○ ● ● ●
✓  Apertura con permiso   «¿Tienes 30 segundos?»
→  Reunión con día y hora                    Foco de la semana
   Propone día y hora concretos.
   Prueba con: «¿Te va bien el jueves a las 10?»
Reunión agendada · No                                  Detalle ›
```

| Elemento | Control | Capa | Peso | Por qué no otro |
|---|---|---|---|---|
| Acierto (✓ + paso + cita) | Texto | Superficie | `text-sm`, cita en cursiva | Es la mitad del mensaje; no requiere acción |
| Cambio (→ + paso) | Texto | Superficie | `text-[15px] text-foreground` | Protagonista: es lo que el comercial se lleva |
| Criterio | Texto | Superficie | `text-sm text-muted-foreground` | Dice qué cuenta como hecho, una línea |
| «Prueba con» | Cita | Superficie | cursiva | La frase decible; si no hay, no se pinta |
| «Foco de la semana» | Chip (`capsLabel`) | Superficie | Mínimo | Une la llamada con Coach sin texto extra |
| Tendencia | 5 puntos | Superficie; % en tooltip (`title`) | Mínimo | Evolución sin número ni ranking |
| Resultado (reunión / siguiente paso) | Línea `capsLabel` | Superficie | Mínimo | Separa ejecución de resultado |
| Detalle | Enlace ghost «Detalle» → expande | Clic | Enlace | Pasos fallados, momentos con minuto (clic = reproducir), objeciones. No merece superficie |
| Nota numérica | — | Nunca aquí | — | Educa el foco, no la nota; la nota vive en `CoachingScore` |

- **Sin acción primaria:** la tarjeta se lee; la acción de la pantalla sigue siendo confirmar el CRM / enviar el follow-up.
- **Estados:** preparando → una línea `VocifySpinner` «Preparando tu feedback…» (solo dashboard; en extensión la pestaña no aparece hasta tener algo). Sin conversación (buzón) → no se pinta. Sin playbook → «Sin playbook para este tipo de llamada» (una línea). Poca evidencia → se pinta lo que hay con cita; sin acierto ni cambio → «Sin datos suficientes para dar feedback».
- **Volumen:** siempre 1 acierto + 1 cambio. Detalle: hasta 5 momentos, 3 objeciones (límites que ya pone el backend).

### 3.3 Mapa de densidad

| Superficie | Hover | Clic | Nunca aquí |
|---|---|---|---|
| Acierto, cambio, frase, foco, tendencia, resultado | % de cada punto | Pasos fallados, momentos, objeciones | Nota 0–10, ids, criterios de pasos cumplidos, ranking |

## 4. Plan técnico

**A · En vivo (backend)**
- `copilot/prompts.py` + `prompts/copilot_suggest_v2.md`: el modelo recibe `id · categoría · respuesta aprobada`; con respuesta aprobada, `say_this` es esa respuesta adaptada a lo que dijo el prospecto (sin hechos nuevos).
- `copilot/grounding.py`: «respaldada» exige `source_id` de una entrada publicada.
- `copilot/load_grounding.py`: sin `capture_id`, el playbook sale del enrutado del comercial (`captures.playbook_fields_for_capture`: rol, canal, contacto), no de «el único publicado». `api/copilot.py` pasa el usuario.

**B · Evaluación y nota (backend)**
- Criterios = lo que hace el comercial: `playbook_structure_v1.md`, `playbook_split_v1.md`, plantillas de `playbooks/catalog.py` y `src/lib/playbook-editor.ts`.
- `intelligence_v6.md`: un criterio que nombra la reacción del prospecto se cumple cuando el comercial hizo su parte. Se corrige en sitio, sin subir versión ni releer llamadas pasadas: `PLAYBOOK_OBSERVATIONS_ENABLED` está encendido en 1 empresa (lectura del 30 sep; el SQL de activación decía apagado) y aún no hay llamadas con observaciones, así que no hay notas viejas que queden incoherentes.
- `score_assembly.py`: sin nota si la cobertura de pasos es < 50 % (`insufficient_evidence`, estado ya diseñado); las objeciones solo cuentan si el playbook tiene respuesta para su categoría; `improvements_cited` marca mejoras que vienen de observaciones citadas.
- `coaching/rep_focus.py` + `api/coaching.py`: cada flujo usa el tipo publicado con más llamadas del comercial (discovery/inbound; closing/ae_discovery/negotiation).

**C · Debrief (backend)**
- `coaching/briefs.py`: mejora citada visible sin objeciones; frases = `example`/`guidance`; `next_step_agreed` = reunión aceptada o compromiso de llamada/reunión con fecha; bloque `coach` (3.1) con el foco semanal (`rep_focus`).

**D · Superficies**
- `shared/ui/components/debrief.js` (render puro, test en node) + `v-debrief.js` + claves `debrief*` en `shared/ui/i18n.js` + bloque `.v-debrief*` al final de `vocify-ui.css`. Montaje: sesión de pestañas.
- `src/lib/post-brief.ts` + `PostInteractionBrief.tsx`: misma tarjeta en React, sondeo mientras `pending` o `waiting`. Copy en `product-catalog.ts`.

## 5. Edge cases

| Caso | Qué ve | Cómo sigue |
|---|---|---|
| Buzón / sin respuesta | Nada (estado `skipped`) | — |
| Tipo sin playbook publicado | Una línea: sin playbook para este tipo | Manager publica en Proceso de venta |
| Todo cumplido | Solo ✓ y la tendencia | — |
| Nada cumplido, nada citado | «Sin datos suficientes para dar feedback» | Siguiente llamada |
| Paso fallado sin `example` | Cambio + criterio, sin «Prueba con» | El manager añade la frase en el playbook |
| Job falla | Estado `failed` actual | Reintento del job |
| Playbook cambió después | Se usa la versión fijada en la llamada | — |
| Sin foco semanal (poco volumen) | Sin chip | — |

## 6. Fuera de este cambio (decisiones pendientes)

- `MEETING_SYSTEM_PROMPT` y el panel en vivo del desktop viven en `feat/desktop-meeting-recorder` (490 commits por detrás de `staging`): unir esa rama es la decisión pendiente n.º 2 del plan del copiloto.
- Checklist en vivo real (§4.1 del plan del copiloto): necesita el panel del desktop unido primero.
- Encender `PLAYBOOK_OBSERVATIONS_ENABLED` tras correr los evals (`scripts/eval_intelligence.py --v4`) tres veces en verde.
- Tipos propios (sin rol de catálogo) en el foco semanal.
