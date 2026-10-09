# Copiloto en vivo con playbook — diseño y plan

> Complementa F08 (playbooks), F10 (objeciones) y F12 (asistencia live). No sustituye esos planes: concreta cómo el copiloto del meeting usa el playbook para marcar fases/preguntas y responder objeciones con respaldo. Aplica `vocify-ux-coherence`.

> **Aviso de ramas (2026-09-28, 21:15):** la rama `staging` ya contiene parte de F08/F12 — `services/playbooks/` (store, versions, imports), `POST /copilot/checklist`, `services/copilot/grounding.py` y `evidence_refs`/`source_id` en la respuesta. El panel del meeting, las reglas de visibilidad y el prompt de meetings viven en `feat/desktop-meeting-recorder` (commit `ef68fa93`). Antes de ejecutar este plan hay que unir ambas ramas y reescribir §3–§4 sobre lo que `staging` ya hace, sin duplicarlo.

## 1. Estado actual (auditado el 2026-09-28)

**Backend — `POST /api/v1/copilot/suggest`** (`backend/app/api/copilot.py`, `services/copilot/`):

- Una sola llamada LLM (`COPILOT_MODEL` = `google/gemini-3.5-flash-lite`, OpenRouter, temperatura 0.35, JSON) detecta y redacta a la vez. No hay clasificador separado ni registro de por qué se mostró algo.
- `SYSTEM_PROMPT` está escrito para cold calls telefónicas, con marcos genéricos (acknowledge → isolate → reframe → advance). No existe conocimiento por empresa salvo `product_context`, que ahora el servidor carga de la empresa si el cliente no lo envía.
- Desde esta revisión, `call_mode="meeting"` usa `MEETING_SYSTEM_PROMPT` y `meeting_suggestion()`: silencio salvo objeción clara, `say_this` de una línea ≤ 90 caracteres, sin texto de relleno. Cubierto por `tests/test_copilot_meeting_suggestion.py`. El modo teléfono (página Call Copilot) no cambia.
- No existe `/copilot/checklist` (el SwiftUI legacy lo llama y recibiría 404). No hay playbooks, entradas de objeción ni competidores.
- Sin evaluación de calidad: no hay dataset ni métricas.

**Desktop — panel «Live assist · Beta»** (`src/features/desktop/assist/`, `src/lib/live-assist.ts`):

- Apagado por defecto; rotulado «Not from your playbook yet. General objection help.».
- Reglas de F12 ya aplicadas en cliente y probadas: 4 s mínimo, 10 s máximo, 60 s de espera por categoría, se retira cuando el comercial habla, una tarjeta activa, anteriores plegadas en «Earlier».
- `ASSIST_SOURCES` es el punto de extensión: cada fuente convierte el contexto de la conversación en una tarjeta o en `null`.
- Incumple conscientemente F12 («sin playbook, silencio») mientras sea beta opcional. Al publicarse F08 para una tipología, la tarjeta sin respaldo se retira para esa tipología (§6).

**Extensión:** cold calling; F12 excluye ampliarla. **Dashboard:** no hay sección Playbooks (F08).

## 2. Recorrido del comercial

1. **Antes:** abre Vocify y empieza el meeting (⌘R o Record). *Crítico:* saber si el coaching está activo. Si su tipología no tiene playbook publicado, lo ve sin bloquearle.
2. **Durante:** habla; mira de reojo. *Crítico (máximo listón):* nada distrae sin motivo. Ve en qué fase está, qué preguntas de cualificación faltan y, solo ante una objeción real con respuesta aprobada, una línea que puede decir ya.
3. **Justo después:** Stop → resumen con sus notas + campos CRM. *Crítico:* lo marcado en vivo coincide con la evaluación final o se explica la diferencia.
4. **Manager (Settings):** carga el proceso («Así vendemos en discovery»), revisa lo propuesto, publica. Ve huecos: objeciones oídas sin respuesta aprobada.

## 3. Modelo de datos (sobre la migración 040 de F08)

F08 ya define `interaction_types`, `playbooks`, `playbook_versions` (pasos y criterios) y `playbook_entries` (categoría de objeción y guía). Se concreta:

- **Paso** (`playbook_versions.steps`, JSON validado): `id` estable, `phase` (p. ej. «Descubrimiento»), `kind` (`question` | `milestone`), `label` corto («¿Quién decide?»), `intent` (qué cuenta como cubierto, 1 frase), `required` (bool), orden.
- **Entrada de objeción** (`playbook_entries`): `category` (price, timing, authority, competitor, status_quo, trust, other), `trigger_examples` (frases del cliente), `approved_answer` (texto del manager), `follow_up_question`, `avoid`, `source_ref` (fragmento original).
- **Battle card:** entrada con `category=competitor` y `competitor_name`/alias. Sin tabla nueva en V1.
- **Registro en vivo** (migración nueva, número tras 040): `copilot_events` — captura, versión de playbook, turno disparador, tipo (`step_observed` | `objection_card` | `objection_suppressed` | `gap`), paso/entrada, cita de evidencia, latencia, motivo de supresión. Es la respuesta a «¿por qué apareció esto?» y la fuente de huecos para F10. **Retención (decisión de Dani):** ligado a ese meeting; se ve desde su memo y se borra con él. No hay histórico aparte.

## 4. Motor en vivo

Principio: **detectar, recuperar, validar y solo entonces mostrar**. El LLM nunca decide solo que algo está respaldado.

### 4.1 Seguimiento de fases y preguntas — `POST /api/v1/copilot/checklist` (contrato de F12)

- **Entrada:** `capture_id`, `playbook_version_id` fijado al empezar, `revision`, turnos finales nuevos con `id`, hablante y tiempos (ya disponibles: `start`/`end` por segmento).
- **Cadencia:** al terminar un turno del cliente o cada ~20 s de habla nueva, lo que ocurra antes; nunca por palabra.
- **LLM (modelo barato):** recibe solo los pasos **no cubiertos** y los turnos nuevos; devuelve `[{step_id, quote, turn_id}]`.
- **Validación en servidor:** `step_id` pertenece a la versión; `quote` existe (normalizada) en el texto de ese `turn_id`; si no, se descarta. Lo cubierto no se desmarca en vivo (monótono); la evaluación final (F09/F11) puede corregir y conserva ambas.
- **Salida:** pasos cubiertos con evidencia y fase actual (la del último paso cubierto o la primera con requeridos pendientes).

### 4.2 Objeciones con respaldo — ampliación de `/copilot/suggest` (F12)

1. **Clasificar** (modelo barato, salida estricta): el último turno del cliente → `category | none` + cita. En duda → `none`.
2. **Recuperar:** entrada activa de esa categoría en la versión fijada; para `competitor`, además coincidencia de nombre/alias. Sin entrada → silencio + evento `gap`.
3. **Redactar:** una línea ≤ 90 caracteres a partir de `approved_answer` y lo que dijo el cliente; `follow_up_question` de la entrada. Validación determinista (longitud, idioma del turno, sin cifras/nombres ausentes de la entrada o del `product_context`). Si falla, se usa `approved_answer` recortada por frase o se calla.
4. **Resultado SSE:** campos actuales + `grounded`, `source_label` («Precio · Discovery v3»), `source_id`, `playbook_version`. Peticiones antiguas sin `capture_id` conservan su contrato (F12).
5. **Cliente:** muestra solo `grounded=true`; reglas de visibilidad ya implementadas (§1).

### 4.3 Modelo

`COPILOT_MODEL = deepseek/deepseek-v4.1-flash` (decisión de Dani, 2026-09-28) con `reasoning.enabled=false`: por defecto razona (~540 tokens ocultos en la prueba), lo que no cabe en ayuda en vivo. Prueba inicial (4 peticiones, prompt de meetings): objeción de precio detectada 3/3 con una línea válida, charla trivial correctamente en silencio; una de las tres líneas abría una negociación de precio poco recomendable, lo que justifica el dataset de §7.

### 4.4 Presupuesto de latencia

Pausa 1,5 s + clasificación + redacción. Se mide por evento en `copilot_events` antes de fijar objetivo; no se promete «tiempo real» sin esa medida.

## 5. Interfaz (desktop, columna derecha del meeting)

| Elemento | Dónde | Peso visual | Por qué |
|---|---|---|---|
| Fase actual | Cabecera del panel, una línea («Descubrimiento · 3/5») | Bajo | Orientación sin leer una lista |
| Preguntas de la fase | Lista corta bajo la fase; pendientes en gris, cubiertas con ✓ y la cita al pasar el ratón | Medio | Recordar qué falta preguntar sin clics |
| Tarjeta de objeción | Debajo; «Say this» + «Next question» + fuente | Alto, solo 4–10 s | Único momento que merece interrumpir |
| Anteriores | «Earlier», plegado | Mínimo | Consulta posterior |
| Pastilla nativa | Progreso compacto («3/7») + la tarjeta activa si hay | Bajo | Útil con la app minimizada; sin segunda ventana |

**Estados:**
- Sin playbook para la tipología: owner/admin ve «Define vuestro proceso para activar el coaching» → Settings › Playbooks; member ve «Tu administrador debe configurar el proceso». La grabación y las notas no se bloquean.
- Playbook sin nada cubierto todavía: pasos en gris, sin mensajes.
- Error del copiloto: una línea discreta; nunca toasts repetidos.
- Ayuda apagada: solo la fila del interruptor.

## 6. Integración entre superficies

- **Dashboard › Settings › Playbooks (F08):** creación, importación, publicación; panel de «huecos» (eventos `gap`) para completar entradas (F10).
- **Desktop:** consume checklist y sugerencias con la versión fijada. La beta queda disponible para todos: sin playbook da ayuda general rotulada como tal; con playbook publicado para la tipología usa sus respuestas aprobadas y muestra la fuente (decisión de Dani, 2026-09-28).
- **Memo tras el meeting:** muestra los pasos cubiertos (vivo) junto a la evaluación final (F09/F11) y las notas del comercial.
- **Extensión:** sin cambios (F12 no se amplía a cold calling).

## 7. Calidad — criterio de aceptación, no estilo

- **Dataset:** meetings reales autorizados y anonimizados con anotación de objeciones (categoría, turno) y pasos cubiertos.
- **Métricas:** precisión y recall de objeción (la precisión pesa más: una interrupción errónea cuesta más que una omisión), tasa de tarjetas con respaldo, longitud ≤ 90, idioma correcto, latencia p50/p95, precisión de pasos marcados (evidencia real).
- **Umbrales propuestos (a confirmar por Dani; se revisan con el primer dataset):**
  - Interrupciones erróneas: como máximo 1 de cada 10 tarjetas no corresponde a una objeción real (precisión ≥ 90 %).
  - Objeciones captadas: al menos 6 de cada 10 (recall ≥ 60 %); se prefiere callar a interrumpir mal.
  - Con playbook: ≥ 9 de cada 10 tarjetas de una categoría con entrada aprobada usan esa entrada.
  - Pasos marcados: ≥ 95 % correctos respecto a la anotación humana.
  - Formato: 100 % una línea ≤ 90 caracteres y en el idioma del turno (ya lo impone el servidor).
  - Latencia desde que el cliente termina de hablar: p50 ≤ 5 s, p95 ≤ 8 s. Referencia medida: el modelo solo tardó 2,1–3,9 s en 4 peticiones sin razonamiento, más la pausa de 1,5 s.
  - Dataset mínimo: 20–30 meetings reales autorizados y anonimizados, con objeciones y pasos anotados por una persona.
- **Sin AI slop:** frases prohibidas en prompt y en validador; revisión humana de una muestra por versión de prompt.

## 8. Casos límite

- Playbook actualizado durante el meeting → se mantiene la versión fijada al empezar.
- Canal desconocido o eco → el disparador exige turno del cliente ya filtrado por eco (`meeting-transcript.ts`).
- Respuesta tardía de otra captura/revisión → se descarta (F12).
- Dos objeciones en un turno → una tarjeta (la de mayor urgencia); la otra queda en `copilot_events`.
- Competidor no presente en el playbook → silencio + `gap`.
- Idioma mixto → el del último turno.
- Reunión larga → cadencia acotada; coste por meeting medido en `copilot_events`.
- Sin `product_context` ni playbook → silencio (con la beta apagada).

## 9. Orden de ejecución y archivos

1. **F08 playbooks** (su plan): migración 040 con el esquema de pasos/entradas de §3; `services/playbooks/`; Settings › Playbooks.
2. **Migración `copilot_events`** + servicio de registro.
3. **Checklist:** `backend/app/api/copilot.py` (`/checklist`), `backend/app/services/copilot/checklist.py`, pruebas de validación de citas; en desktop, `src/features/desktop/assist/checklist.ts` (fuente) y sección de fase/preguntas en `LiveAssistPanel.tsx`.
4. **Objeciones con respaldo:** `services/copilot/classify.py`, `services/copilot/grounded.py`, ampliación SSE con compatibilidad; en desktop, una fuente `grounded-objection` en `ASSIST_SOURCES` que sustituye a la beta cuando hay playbook.
5. **Pastilla nativa:** progreso compacto y tarjeta activa en `MeetingPill.swift` vía `shell:state`.
6. **Evaluación:** dataset, script de métricas y umbrales aprobados → activar por defecto.

### Ajustes tras prueba real (2026-09-29, decisión de Dani)

- **Visibilidad:** mínimo 8 s, se mantiene mientras el comercial responde, se retira 2,5 s después de que termine, máximo 25 s (sustituye 4/10 s de F12: la tarjeta desaparecía mientras se leía en voz alta). Espera de 60 s por categoría sin cambios.
- **Frase puente:** en cuanto el stream indica `is_objection=true` y el tipo, se muestra la etiqueta y una frase puente fija por tipo e idioma (`BRIDGES` en `src/lib/live-assist.ts`, editable); la respuesta validada la sustituye en el mismo sitio. Si el servidor acaba en silencio, el borrador se retira.
- **Tipo `question`:** pregunta directa sobre el producto solo si la respuesta está en PRODUCT / OFFER CONTEXT; si no, silencio. Etiqueta neutra para distinguirla de las objeciones.

## 10. Decisiones

**Tomadas (2026-09-28):**
- Modelo: DeepSeek V4.1 Flash sin razonamiento (§4.3).
- Registro `copilot_events`: solo durante la vida de ese meeting/memo (§3).
- Beta para todos; con playbook usa el playbook (§6).

**Pendientes:**
1. Confirmar o ajustar los umbrales propuestos (§7).
2. Qué rama es la base para unir el panel del meeting con el copiloto de `staging`.
