# Coaching · «Mis llamadas» y diagnóstico de datos (13 oct 2026)

Notas para quien siga con Coaching. Lo que dice «verificado» se comprobó leyendo producción en
solo lectura (consultas y los handlers GET llamados desde un script, sin arrancar el backend).
Lo que dice «leído en código» no se comprobó con datos.

## 1. Qué cambia en este commit

Solo frontend, sin tocar endpoints.

- `src/features/coaching/rep/CoachingInteractions.tsx` (Coaching → Mis llamadas): cada llamada es
  una tarjeta que abre la llamada. Arriba fecha · hora · duración y el resumen (2 líneas); debajo la
  tile «Pasos hechos» (x/y) y, solo si hubo reunión, la tile «Reunión · Sí»; al final una línea
  «Se escapó: …» con los pasos no hechos. Las llamadas sin conversación (buzón, no contesta) van
  plegadas al final en una línea cada una. Los filtros no cambian.
  Se quitan los chips de paso con emojis, los párrafos de consejo por paso y la mezcla de llamadas
  sin conversación con las reales.
- `src/lib/rep-coaching.ts`:
  - `stepsDone` cuenta `improvable` como hecho, igual que el backend (`rep_coaching.step_rates`).
    Antes el frontend lo ignoraba y una llamada con 3 mejorables y 2 fallados salía «0 de 2».
  - Nuevos `countTone` (todo / nada / parte: los únicos tres colores, sin umbrales inventados) y
    `cleanSummaryLine` (quita el markdown «Resultado:**» que deja la extracción).
  - Se borra `stepsDoneLine` (ya no se usa).
- `src/lib/product-catalog.ts`: claves `coachCard*` y `coachNoConversation` en ES y EN; se borra
  `coachStepsDone` (sin uso).
- Tests: `src/lib/rep-coaching.test.ts` (20 en verde).

**Por qué la reunión solo se pinta cuando es «Sí».** `meeting_agreed` sale de `memos.rep_outcome`
+ etapa del CRM, y `rep_outcome` no existe en producción (ver §3). Pintar «No» en rojo afirmaría
algo falso en llamadas donde el resumen dice que se aceptó una reunión.

## 2. Cómo se verificó (y qué no)

- Renderizado con los componentes reales y las respuestas reales de un SDR (45 llamadas, 32 con
  conversación) en un arnés local que responde a la API desde un volcado. 32 tarjetas, 13 plegadas.
- `tsc` y `lint:ui` limpios en los archivos tocados; `vite build` OK. El repo ya tenía 33 errores de
  tipos (sobre todo `HubSpotSyncPreview.tsx`) y 12 de `lint:ui` en otros archivos; no son de esto.
- **No verificado:** con Reticle ni en la app real con sesión (el backend local apunta a
  producción), modo oscuro, otras empresas, el rol AE («Mis reuniones» usa este mismo componente).

## 3. Diagnóstico de datos (verificado)

Estas son las razones principales por las que Coaching se siente confuso; casi ninguna es de diseño.

| # | Hallazgo | Evidencia | Efecto en pantalla |
|---|---|---|---|
| 1 | Al republicar un playbook cambian los `step_id`; las llamadas se puntuaron con los anteriores y el agregado solo cuenta los actuales | En el SDR revisado, 31 de 32 conversaciones usan los pasos del playbook anterior | Resumen dice «Vas bien: ningún paso se repite como fallo» con los 7 pasos en «—», y Mi proceso «Aún no hay datos», aunque un paso se escapó en 11 de 32 llamadas |
| 2 | La columna `memos.rep_outcome` (migración `062`) no existe en producción | La consulta falla con `column memos.rep_outcome does not exist` | «Reuniones acordadas» = 0 y el filtro «Solo con reunión» vacío; la extracción marca `meeting.agreed = true` en 6 de esas 32 llamadas |
| 3 | La tabla `brief_seen` no existe en producción | Log: `bell feedback: brief_seen unavailable, treating as empty` | Marcar feedback como visto no persiste |
| 4 | La pestaña Playbook del comercial abre un tipo que su rol no puede leer | `GET /playbooks` le lista los 3 tipos publicados (rama de tipos por canal) y `GET /playbooks/closing/editor` responde 404 | «No se pudo cargar el proceso» al abrir la pestaña |
| 5 | «Prueba con» en la tarjeta de la llamada muestra la guía entera de la objeción | `coach.fix.say` = `guidance` del playbook (un párrafo) | No es una frase que se pueda decir |
| 6 | El checklist de pasos de la llamada viene vacío | `POST /copilot/checklist` devuelve `steps: []` (sin `playbook_version_id`) en 44 de 45 llamadas | La lista de pasos de la tarjeta «Proceso» no aparece |
| 7 | Un tercio de los veredictos por paso en conversaciones reales son «no alcanzado» (la llamada terminó antes) | 62 de 193 en ese SDR (136 de 271 si se cuentan también buzones y no contesta) | Las vistas por paso se ven vacías |
| 8 | Nota 0–10 poco fiable | De 246 llamadas puntuadas, 114 tienen nota; 33 de esas se apoyan en 1–3 pasos y 30 son exactamente 0 o 10 | El «7/10» de la tarjeta dice poco |
| 9 | Los «momentos» y el audio del debrief nunca salen | `highlights` vacío en 246 de 246 briefs; `audio_available` falso en todos (`score_jobs.py` mira `audio_path` / `recording_url`, la columna real es `recording_path`) | «Detalle → Momentos» y «Escuchar» no funcionan |
| 10 | La transcripción post-llamada pierde los tiempos | `deepgram_batch.format_deepgram_transcript` ordena por `start` y lo descarta | No se puede saltar al minuto de un paso; solo se puede ubicar por turno |
| 11 | Categoría de objeción sin etiqueta | La extracción devuelve `bad_moment`; la UI no la tiene y cae en «Otra» | — |
| 12 | Filas de puntuación que se acumulan | `memo_scores`: 472 filas para 246 memos | Los lectores eligen la «actual» con reglas distintas (ver §4) |

## 4. Leído en código, no verificado con datos

- Hay al menos seis definiciones de «% del proceso» (adherence del score, nota, rep engine,
  checklist, insights del playbook, process health) y la definición de «conversación» difiere entre
  coaching (≥ 30 s) y equipo/informes.
- La tendencia del debrief mezcla valores con y sin el mínimo de cobertura (`briefs.py` `progress`
  vs `coach.adherence`).
- Lectores que desempatan revisiones de forma distinta (`revision_seq` vs `created_at`).
- En un caso, la «respuesta» guardada de una objeción parecían palabras del prospecto, no del
  comercial. No se confirmó con audio.

## 5. Prototipo local (no subido)

Hay un prototipo en `src/prototypes/coaching/` + `prototypes/coaching/index.html` que no se sube:
lee un volcado git-ignorado (`*.json.local`) con datos de clientes. Exploró:

- **Una llamada estilo Caretta**: izquierda, cada paso / objeción / criterio como nombre → respuesta
  agrupados; centro, la transcripción; derecha, dónde pasó cada cosa en la llamada (por turno, porque
  no hay minutos). Clic en cualquiera y los otros dos se sincronizan.
- **Un foco**: una sola conducta elegida por regla (la situación más fallada en ≥ 3 llamadas), la
  frase que dijo y la frase del playbook para la próxima.

Si se quiere retomar, pedirlo y se sube sin los datos.

## 6. Siguientes pasos propuestos (por orden)

1. Que editar el playbook no borre el histórico de coaching (hallazgo 1). Es lo que más rompe hoy.
2. Aplicar en producción `062_sdr_followup_cadence.sql` y crear `brief_seen` (hallazgos 2 y 3).
   Revisar qué otras migraciones faltan.
3. Pestaña Playbook: abrir en un tipo que el rol del comercial pueda leer (hallazgo 4).
4. Una frase corta y decible por paso y por objeción, separada de la guía (hallazgo 5).
5. Guardar los tiempos de la transcripción para poder escuchar cada momento (hallazgos 9 y 10).

## 7. Decisiones abiertas

- Si «Mis llamadas» debe mostrar también objeciones y cualificación por llamada: hoy
  `/coaching/me/interactions` no las devuelve, así que haría falta cambiar ese endpoint.
- Si se quitan del rep las pestañas Mi proceso y Ejemplos y la nota 0–10.
- Si las llamadas de un playbook anterior cuentan para el foco del comercial.
