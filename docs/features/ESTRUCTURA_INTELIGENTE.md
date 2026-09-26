# Estructura inteligente — propuesta de arquitectura para B6, C1 y la capa de memoria
### Complementa `MASTER_PLAN.md`. No lo reemplaza ni lo edita.

*Basado en lectura directa del código, no en el plan — cada afirmación de "esto ya existe" cita archivo:línea. Fecha: 2026-09-21.*

---

## 0. Antes de la arquitectura: 4 cosas que hacer esta semana, no en Sprint 0

Ninguna depende de la propuesta de abajo. Son operativas y tienen fecha.

1. **Trabajo real sin commitear en `getvocify-desktop`.** `lib/permissions.js`, `lib/mic-devices.js`, `lib/memo-review.js`, `lib/extraction-omit.js`, todo `native/` (el tap Swift de ScreenCaptureKit), y cambios a `electron-main.mjs`/`preload.cjs`/`package.json` están modificados o sin trackear, solo en tu máquina. La versión en GitHub no tiene permisos, no sabe cargar el tap nativo — si tu cofundador hace `git pull` hoy, tiene una app peor que la que tú ves. Commit + push antes de leer el resto de este documento.
2. ~~**El gate de prefijo 400 no está implementado.**~~ **Hecho 2026-09-26** — `services/telephony/caller_id.py` rechaza verificar +34 6/7 y +34 400, y bloquea en llamada los móviles ya verificados desde el 17/10/2026. Regla e interpretaciones en `docs/telephony/DECISION.md` → "Action #2 as implemented".
3. **`backend/app/services/crm_updates.py:71`** tiene un TODO con fecha de corte 2026-09-15 — ya pasó. Borrar el código muerto que ese TODO describe.
4. **`billing/catalog.py:37` vende "Scoring you can stand on" en los planes Starter/Pro ($39/$59) hoy.** No existe backend de scoring (cero hits de MEDDIC/BANT/SPICED/scorecard en todo `backend/app`). "Coaching as it happens" sí es real (el objection-copilot en vivo). O se quita esa línea de la página de precios esta semana, o se prioriza C1 antes de lo que dice el plan — pero no debería quedar así ni una semana más.

---

## 1. El mapa real vs. el plan — qué ya existe, con archivo:línea

| Ítem de tu lista de 5 | ID en MASTER_PLAN | Estado real |
|---|---|---|
| 1. Captura + transcripción + CRM | A1/A2/B1 | **Hecho y maduro.** 3 superficies de captura (WhatsApp, extensión, desktop), extracción vía OpenRouter, sync a HubSpot/Salesforce/Pipedrive. Esto es todo el producto de hoy. |
| 2. Acciones proactivas | B6 "Organización del día" | **Cero código.** `grep -rn "proactive"` en todo `backend/app` → 1 hit irrelevante. Planificado Sprints 7-8. |
| 3. Desktop app | A4 | **Real y más avanzado de lo que el propio plan asume** — ver §0.1. `MASTER_PLAN.md:119` dice *"La carpeta `desktop/` ya existe"* refiriéndose al stub vacío dentro de este repo, no al repo hermano real. El plan no cuenta el trabajo ya hecho. |
| 4. Coaching + scorecards | C1/C2/D10 | **Existe algo relacionado pero distinto**: `services/copilot/suggest.py` da sugerencias en vivo durante la llamada (objection copilot, real, shipeado, consumido por `chrome-extension/lib/copilot-sse.js`). Scoring post-llamada contra playbook: cero código. Planificado Sprints 9-11, el último bloque antes del colchón. |
| 5. Memoria / contexto cruzado | — | **No tiene ID en el plan.** Ni siquiera está nombrado. Lo más cercano es F0.1 (el modelo `Interaction`) como sustrato futuro, pero ningún sprint lo construye. Es el único de tus 5 puntos sin hueco reservado. |

---

## 2. F0.1 "Interaction unificado" — es más barato de lo que el plan asume

`MASTER_PLAN.md:99` propone: `{id, type: call|meeting|visit|voice_note|email, source, audio_ref, transcript, participants, crm_links, extracted: {...}, score: {...}}`, con "migrar lo existente" como parte del trabajo de Sprint 0.

Comparado campo a campo contra la tabla `memos` que ya existe (`backend/app/models/memo.py`, `backend/migrations/`):

| Campo que pide F0.1 | Ya existe como | Falta |
|---|---|---|
| `id` | `memos.id` | — |
| `source` | `memos.source` (web/voice_memo/whatsapp/unipile/hubspot_call/vocify_call) | — |
| `type` (call\|meeting\|visit\|voice_note\|email) | **No existe** — hoy `source` mezcla canal y tipo | **Columna nueva** |
| `audio_ref` | `memos.recording_path` (migración 034) + `audioUrl` | — |
| `transcript` | `memos.transcript` | — |
| `participants` | No existe estructurado (solo `contactName` singular + `decisionMakers[]` en `extraction`) | Puede esperar a A3 (el bot de reuniones traerá lista real de asistentes vía calendario) |
| `crm_links` | Disperso: `matched_deal_id`, `hubspot_deal_id/contact_id/engagement_id` | Funciona así, no hace falta unificar todavía |
| `extracted` | `memos.extraction` JSONB (`MemoExtraction`, `models/memo.py:60`) | — |
| `score` | **No existe** | **Columna nueva** |

**Conclusión: F0.1 no es una migración de datos, es añadir 2 columnas a una tabla que ya hace el 80% del trabajo.** No hay "lo existente" que migrar — ya está en la forma correcta. Esto libera casi toda la semana de Sprint 0 que el plan reserva para F0.1, para gastarla en F0.3 (el golden dataset/eval harness), que es la pieza que de verdad no se puede acortar.

```sql
-- migración 037 (ilustrativa)
ALTER TABLE memos ADD COLUMN interaction_type text
  CHECK (interaction_type IN ('call','meeting','visit','voice_note','email'));
ALTER TABLE memos ADD COLUMN score jsonb;
-- backfill: source='whatsapp' → 'voice_note'; source IN ('vocify_call','hubspot_call') → 'call'
```

---

## 3. Los dos huecos reales: `action_signals` y `interaction_patterns`

Esta es la "estructura inteligente" que pediste — mínima, interconectada, y las dos tablas se alimentan de datos que **ya extraéis hoy** (`objections[]`, `painPoints[]`, `nextSteps[]` en `MemoExtraction`, `models/memo.py:78-82`). No es captura nueva, es una pasada más sobre lo que ya tenéis.

### 3.1 `action_signals` — la columna vertebral de B6 (y de C1, y de C2)

No existe hoy ninguna tabla de señales — `crm_updates` es un log de auditoría de escrituras al CRM, no un almacén de "por qué actuar". B6 necesita esto para no ser genérico (si no, es literalmente Salesloft Rhythm, que ya hace "detectar señal → acción priorizada con explicación" desde 2023).

```sql
CREATE TABLE action_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id),
  deal_id text,              -- CRM deal id, nullable si aún no hay match
  contact_id text,
  source_memo_id uuid REFERENCES memos(id),
  signal_type text NOT NULL, -- 'silence_2w' | 'requested_callback_date' | 'objection_unaddressed'
                              -- | 'champion_risk' | 'coaching_flag' (ver §3.3)
  detected_at timestamptz NOT NULL DEFAULT now(),
  due_at timestamptz,         -- para 'requested_callback_date': la fecha que el lead pidió
  payload jsonb NOT NULL,     -- el "por qué": quote de la transcripción, campo relevante
  status text NOT NULL DEFAULT 'pending', -- pending | actioned | dismissed | expired
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON action_signals (company_id, status, due_at);
```

**Generador v0 — reglas explícitas, no LLM nuevo.** El propio `MASTER_PLAN.md:135` ya pide esto ("reglas explicables, no ML opaco: follow-ups comprometidos > leads calientes > resto por cadencia") — coincide con lo que recomendé para el roadmap SDR. La primera versión es una función que corre después de cada `extraction` y lee lo que ya está ahí:

- `nextSteps[]` con fecha detectada → `signal_type='requested_callback_date'`, `due_at` parseado.
- `objections[]` no vacío + ningún `crm_update` posterior de tipo nota/tarea → `signal_type='objection_unaddressed'`.
- Deal con `matched_deal_id` y ningún memo nuevo en 14 días (query simple contra `memos.created_at` agrupado por deal) → `signal_type='silence_2w'`.

**Coste real: no es un feature de 2 semanas, es una función SQL/Python de un día sobre datos que ya existen**, más un endpoint de lista. La versión "Tu día" pulida con UI, ventanas horarias y teardown de Rhythm/Nooks (la que sí merece las 2 semanas completas que le da el plan) es la v1 que viene después — pero la v0 no tiene que esperar a Sprints 7-8.

### 3.2 `interaction_patterns` — la capa de memoria (el punto 5, sin ID hasta hoy)

Esto es deliberadamente estrecho — no es un sistema de memoria genérico ni un vector store. Es una tabla de hechos: objeción → qué se respondió → qué pasó con el deal. Alimenta tres cosas a la vez (B4/B5 briefs, C2 debrief, la biblioteca de respuestas ganadoras), que es exactamente el principio de "mínima información, todo interconectado" que pediste.

```sql
CREATE TABLE interaction_patterns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id),
  objection_category text NOT NULL,   -- taxonomía cerrada (8-12 valores), no texto libre
  source_memo_id uuid NOT NULL REFERENCES memos(id),
  rep_user_id uuid,
  response_summary text,              -- 1-2 frases: qué dijo el rep en respuesta
  deal_id text,
  outcome text,                       -- 'meeting_booked' | 'deal_won' | 'deal_lost' | 'no_response' | 'pending'
  outcome_recorded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON interaction_patterns (company_id, objection_category, outcome);
```

**Cómo se llena, sin trabajo nuevo de captura:** `objection_category` sale de clasificar `extraction.objections[]` contra una taxonomía cerrada (reutiliza el mismo patrón de `jev-1.13`, el clasificador rápido que ya existe en `services/llm/jev.py` para campos de CRM tipo dropdown — mismo tipo de problema, mismo pipeline, no es infraestructura nueva). `outcome` se actualiza cuando el `crm_update` correspondiente marca el deal como ganado/perdido (ya existe ese evento, solo falta el trigger que también escribe aquí).

**Por qué esta tabla y no la genérica que sugiere "sistema de memoria":** el research de competidores (que ya viste) confirmó que ninguna de las empresas analizadas — ni las que levantaron $50-75M — logró verificar un moat de datos cruzando clientes; lo único que funcionó fue memoria *dentro de cada cuenta*. `interaction_patterns` es exactamente eso: por `company_id`, nunca cruzando compañías. No construir la versión ambiciosa (patrones globales entre clientes) sin evidencia de que hace falta.

### 3.3 C1 (scoring) se conecta, no se construye aparte

El plan (`MASTER_PLAN.md:142`) dice: *"C1... es el gancho de compra"*. Vale la pena decirlo directo: la evidencia del research de competidores dice lo contrario — la queja más concreta que encontramos en todo el mercado fue sobre Attention, exactamente por tratar el score como el producto ("scoring identificado como el área más débil, los datos no se pueden exportar"). El feedback concreto y accionable es lo que genera prueba social; el número de score, en ningún caso analizado, aparece como razón espontánea de compra.

Esto no cambia si construir C1 — cambia **cómo se presenta**. Estructuralmente:
- El score vive en `memos.score` (la columna que ya propone F0.1, §2).
- Cuando un score señala un problema, genera una fila en `action_signals` con `signal_type='coaching_flag'` — así C2 (debrief al rep) y B6 (lista diaria) comparten la misma tubería en vez de ser dos UIs separadas.
- El cálculo reutiliza `services/llm/jev.py` (clasificación barata y calibrada) en vez de montar un motor de scoring nuevo — es el mismo tipo de tarea (clasificar contra criterios) que ya resuelve para campos de CRM.

### 3.4 El punto 6 de tu roadmap original (MCP conversacional) ya existe — extenderlo, no construirlo

`services/crm_copilot/` (`loop.py`, `tools.py`, `soul.md`) ya es un agente conversacional por WhatsApp con tool-loop real, no un concepto. "Qué pasó con los últimos 50 contactos, qué objeciones hubo" no es una feature nueva — son 2-3 tools nuevas (`query_action_signals`, `query_interaction_patterns`) registradas en el mismo loop que ya existe. Esto es, con diferencia, lo más barato de toda esta propuesta.

---

## 4. Secuencia recomendada — qué cambiar del plan y por qué

Los últimos 21 días de migraciones (025-036) fueron 100% telefonía/dialer y billing — cero en los puntos 2, 4 o 5. Eso no es negligencia, es el plan funcionando como está escrito: captura primero, inteligencia al final. Pero dado que F0.1 resulta ser 2 columnas (§2) y `action_signals` v0 resulta ser una función sobre datos que ya existen (§3.1), la razón original para posponer B6 a Sprints 7-8 — "consume todo lo anterior" — ya no aplica del todo: v0 no consume A3/A4/A9, consume lo que F0.2 ya produce hoy.

**Recomendación concreta: mete F0.7 (`interaction_patterns` + `action_signals`, schema + generador de reglas v0) dentro de Fase 0, en paralelo con F0.1-F0.6, no después.** Coste estimado 3-4 días, no las 2 semanas que el plan reserva para la versión pulida de B6. La versión pulida ("Tu día" como pantalla de inicio, ventanas horarias, teardown de Rhythm/Nooks) se queda donde está, en Sprints 7-8 — pero para entonces ya hay señal real acumulada desde Sprint 0 en vez de arrancar de cero.

No toco la posición de A3/A4/A9 (Sprints 1-3) ni de C1 completo (Sprints 9-11) — esas sí dependen de trabajo real que no existe todavía (Recall.ai, el bot de reuniones, el harness de evals). La única propuesta de reordenar es adelantar el cimiento de datos de B6/C2, no las features completas.

---

## 5. Desktop — qué significa "retoques" en concreto

Confirmado por lectura directa: el tap nativo de macOS (`native/macos-tap/main.swift`, ScreenCaptureKit) es ingeniería real, no un placeholder — es la misma técnica que usa Granola. No es un clon de Granola por construir; es cerrar 2 huecos reales, los dos con un patrón ya resuelto en otra parte del propio repo:

1. **Diarización real** — hoy es un split binario mic="Tú"/audio de sistema="Ellos" (`lib/listen-policy.js:32-54`), no distingue hablantes dentro de una reunión de grupo. La extensión de Chrome ya cita la diarización por canal de Speechmatics (`lib/stt-channels.js:3-4`) para su propio modo de escucha en vivo — el desktop ya manda los dos canales (mic/sistema) al mismo websocket de transcripción (`lib/channels.js:51-53`); falta activar diarización multi-hablante en la llamada a Speechmatics para el canal de sistema, no inventar nada nuevo.
2. **Persistencia de audio crudo** — hoy solo se sube la transcripción de texto (`renderer/app.js:538-541`), sin fallback si se cae el websocket a mitad de reunión. La extensión ya resuelve esto en su propio flujo de memo por mic (sube el blob grabado). Aplicar el mismo patrón al desktop.

No hay nada más "hecho a medias" a nivel arquitectónico — el resto (permisos, UI de review, overlay estilo Granola) ya está resuelto y probado (`lib/*.test.js`).

---

## 6. Siguiente paso

Esto está a propósito escrito como insumo para vuestro propio proceso de 6 etapas (`MASTER_PLAN.md:35`), no como reemplazo — si quieres, lo convierto en un `spec.md`/`design.md` real bajo un ID nuevo (propongo **F0.7** para el schema de `action_signals`/`interaction_patterns`) para que pase por teardown/spec/design como cualquier otra feature. Dímelo y lo dejo en `docs/features/F0.7/`.
