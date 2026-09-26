# Vocify · Plan maestro de implementación — Nueva identidad y 20 features

**Fecha:** 19 sep 2026 · **Fuente de requisitos:** `vocify-nueva-identidad-features.pdf` (identidad de marca + 4 pilares + 13 gaps fase 1)
**Equipo:** 2 founders + Cursor · **Principio rector:** cada feature pasa por el proceso completo de 6 etapas. Ninguna se shipea "a medias". Calidad > velocidad aparente.

---

## 0. La tesis del plan

Las 20 features NO son 20 proyectos independientes. Comparten un sustrato:

```
CAPTURA (Pilar A)          →  PIPELINE COMÚN                    →  CONSUMIDORES (Pilares B/C/D)
─────────────────             ────────────────                     ──────────────────────────
cold call (dialer)     ──┐                                      ┌─ CRM autofill (B1) ✅
meeting online (A3)    ──┤    Interaction (objeto único)        ├─ Follow-up email (B3)
botless desktop (A4)   ──┼──→ transcripción                 ──→ ├─ Briefs (B4/B5)
voz WhatsApp (A2) ✅   ──┤    extracción estructurada (LLM)     ├─ Tasks/compromisos (B7/B8)
ingesta dialers (A9)   ──┘    scoring (C1)                      ├─ Daily plan (B6)
                              eventos de analytics              ├─ Debrief rep (C2)
                                                                ├─ Objeciones/competidores (C3/D3/D4)
                                                                └─ Dashboard + reportes (D1/D2/D5/D11)
```

**Implicación:** el 70% de la calidad de TODAS las features B/C/D depende de la calidad de la extracción del pipeline común. Por eso la Fase 0 (fundamentos) no es burocracia: es donde se gana o se pierde el nivel "cirujano".

**Cómo lo han construido los que admiramos** *(hallazgos del benchmark; verificar en cada teardown)*:
- Los productos de meeting-recording (categoría de Sybill/Attention/tl;dv) mayoritariamente NO construyen su propio bot de Zoom/Meet/Teams: usan infra tipo **Recall.ai** (API de bots + Desktop Recording SDK para botless). Evaluar comprar vs. construir en A3/A4 — puede convertir meses en semanas. *(A verificar en teardown: pricing de Recall.ai vs. volumen esperado.)*
- Sybill mide su follow-up email con **"75% no-edit rate"**: la métrica de calidad es parte del producto. Cada feature nuestra define su métrica equivalente ANTES de construirse.
- Siro es **offline-first** en móvil y Attention es **botless-first**: las decisiones de captura son decisiones de adopción, no técnicas.
- Ya tenemos Speechmatics en el backend (tests presentes) — el pipeline de STT existe; el gap es la extracción estructurada evaluable y el modelo `Interaction` unificado.

---

## 1. El proceso por feature: las 6 etapas (no negociables)

Cada feature, da igual su tamaño, pasa por las 6. Es lo que garantiza el mismo cariño a la 1 que a la 20.

### Etapa 1 · Teardown (0,5–1 día)
Analizar cómo lo hacen los 2–3 mejores en esa feature concreta:
- Sacar trial/demo del competidor cuando sea posible (Sybill Free, Fathom free, tl;dv free) y usarlo de verdad con una llamada nuestra.
- Capturar: su UX exacta (screenshots), qué campos extraen, cómo presentan el output, qué hacen con los edge cases, tiempos de entrega del resultado.
- Buscar sus engineering blogs, changelogs, docs de API: pistas de arquitectura y proveedores.
- **Output:** `docs/features/<ID>/teardown.md` — con la decisión "qué copiamos, qué mejoramos, qué ignoramos".

### Etapa 2 · Spec (0,5 día)
PRD corto (1–2 páginas máx) usando `docs/features/_TEMPLATE/spec.md`:
- Job-to-be-done en 1 frase + a qué audiencia sirve (rep vs. head of sales — el messaging es doble).
- **Métrica de calidad medible** (ej.: B3 → % de emails enviados sin editar; C1 → % de acuerdo entre score IA y score del manager en 20 llamadas de validación).
- Edge cases enumerados (llamada sin respuesta, audio malo, meeting en inglés, contacto no existe en CRM…).
- Qué NO hace la v1 (el recorte explícito es lo que permite el cariño en lo que sí hace).

### Etapa 3 · Design doc (0,5 día)
- Arquitectura: qué toca del pipeline común, modelos de datos, endpoints, prompts (versionados en repo).
- Revisión: el otro founder lee y firma. Para features grandes, usar Cursor en plan mode contra el spec y discutir el plan generado.
- **Output:** `docs/features/<ID>/design.md`.

### Etapa 4 · Build con Cursor (1–5 días según feature)
- Rama `feat/<ID>-nombre-corto`. Una feature = una rama = un PR (o serie de PRs pequeños).
- Arrancar cada sesión de Cursor dando contexto: `@docs/features/<ID>/spec.md @docs/features/<ID>/design.md` + rules del dominio.
- **Lógica determinista → TDD** (test primero, Cursor implementa hasta verde).
- **Lógica IA → eval harness**: cada prompt tiene su set de casos en `backend/evals/<ID>/` con inputs reales (golden dataset) y outputs esperados/criterios. Cambio de prompt sin correr evals = PR rechazado.
- Self-review con checklist antes de merge (lint, types, tests, evals, migración reversible, feature flag).

### Etapa 5 · QA de cirujano (1–2 días)
- **Verificación Reticle (frontend):** todo cambio con superficie de UI se verifica con un flow de Reticle antes de darse por hecho (`reticle_act_and_wait` con veredicto real, no `no-fault`). Los flows guardados de cada feature llevan `intent` y quedan como regresión permanente: la feature #1 sigue verificándose cuando construimos la #13.
- **Dogfooding**: los 2 founders usan la feature con SUS llamadas reales durante ≥2 días.
- **Design partners**: 2–3 clientes beta asignados a cada feature (rotar entre los 16) la prueban con flag activado. Feedback estructurado, no "¿qué te parece?".
- La métrica de calidad del spec debe alcanzar su umbral ANTES de GA. Si no llega, se itera (prompts → evals → repeat), no se shipea.

### Etapa 6 · Ship + medir (continuo)
- Feature flag → rollout a los 16 betas → medir la métrica de éxito 2 semanas.
- Los 4 KPIs de negocio (fill rate CRM, horas admin ahorradas, adherencia al método, time-to-value) se actualizan automáticamente; son la materia prima de los futuros testimonios.
- Retro de 15 min: ¿qué aprendimos? → actualizar rules de Cursor y este plan.

**Límite de WIP: máximo 2 features simultáneas en etapa 4** (una por founder). Todo lo demás espera en cola. Es la protección real del "mismo cariño para cada una".

---

## 2. Setup de Cursor (hacer una vez, Sprint 0)

1. **Rules por dominio** en `.cursor/rules/` (añadir a las existentes):
   - `pipeline.mdc` — el modelo `Interaction`, convenciones del pipeline, dónde viven los prompts, cómo correr evals.
   - `feature-process.mdc` — resumen de las 6 etapas; obliga a Cursor a pedir el spec si no se lo dan.
   - `frontend.mdc` / `backend.mdc` — convenciones ya conocidas del repo (shadcn, React Query, FastAPI, migraciones).
2. **Command** `.cursor/commands/new-feature.md`: scaffolding de `docs/features/<ID>/` desde la plantilla.
3. **Specs como contexto de primera clase**: Cursor siempre trabaja CONTRA un spec del repo, nunca contra una descripción oral. El spec es el contrato.
4. **CI**: lint + typecheck + tests + evals en cada PR. Un eval que baja del umbral rompe el build igual que un test.
5. **Prompts versionados en el repo** (`backend/app/prompts/` o equivalente), nunca hardcodeados inline: son código de primera clase, con review y evals.

---

## 3. Fase 0 · Fundamentos (Sprint 0, ~1 semana, ambos founders)

Sin esto, cada feature reinventa la rueda y la calidad diverge.

| # | Entregable | Detalle |
|---|-----------|---------|
| F0.1 | **Modelo `Interaction` unificado** | Tabla + API: `{id, type: call\|meeting\|visit\|voice_note\|email, source, audio_ref, transcript, participants, crm_links, extracted: {...}, score: {...}}`. Migrar lo existente (cold calls, WhatsApp voice) al modelo. |
| F0.2 | **Pipeline de extracción v1** | Etapas: STT (Speechmatics, ya existe) → extracción estructurada (JSON schema por tipo de interacción) → router de acciones. Idempotente, reintentable, con cola. |
| F0.3 | **Golden dataset + eval harness** | 50–100 interacciones reales anonimizadas de los betas (con permiso/DPA), con extracciones esperadas anotadas a mano por los founders. Runner de evals (puede ser pytest + LLM-as-judge para campos abiertos). ESTE es el activo que hace posible el trabajo de cirujano en IA. |
| F0.4 | **Instrumentación de los 4 KPIs** | % campos CRM rellenos, horas admin ahorradas (calculadas por actividad), time-to-value, y hueco preparado para adherencia (llega con C1). Dashboard interno simple. |
| F0.5 | **Feature flags** | Por cliente/usuario. Simple (tabla + check), no hace falta LaunchDarkly. Por empresa: hecho (ver abajo). Por usuario: pendiente. |
| F0.6 | **Decisión build vs. buy para A3/A4** | Spike de 1 día con Recall.ai (bot API + Desktop SDK): coste por hora de grabación vs. volumen de los 16 betas. Decisión documentada en `docs/features/A3/design.md`. |

### Activar un flag para un cliente

El valor global sale de `backend/app/config.py` (env). Una fila en `company_feature_flags` lo sobrescribe para esa empresa; sin fila, manda el global. El backend lo lee con `app.services.feature_flags.is_enabled(supabase, company_id, "FLAG")`. Solo service role (SQL editor de Supabase); no hay UI ni escritura desde cliente. El cambio tarda hasta 1 minuto en aplicarse (caché por proceso).

```sql
SELECT id, name FROM companies WHERE name ILIKE '%acme%';

INSERT INTO company_feature_flags (company_id, flag, enabled)
VALUES ('<company_id>', 'INTELLIGENCE_EXTRACT_ENABLED', true)
ON CONFLICT (company_id, flag) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now();

-- volver al valor global
DELETE FROM company_feature_flags WHERE company_id = '<company_id>' AND flag = 'INTELLIGENCE_EXTRACT_ENABLED';
```

Hoy por empresa: `REPORTING_DAILY_EMAIL_ENABLED` (email del informe diario; apagado, el informe se genera y sale en la campana, pero no se envía), `INTELLIGENCE_EXTRACT_ENABLED`, `ASK_VOCIFY_DATA_TOOLS_ENABLED` y `ASK_CALL_ACTIONS_ENABLED` (botón Llamar en «¿a quién llamo hoy?» de Ask; necesita también `ASK_VOCIFY_DATA_TOOLS_ENABLED`, ver F07.06). `TEAM_ADHERENCE_TREND_ENABLED`: evolución semanal de adherencia por comercial en Equipo, solo owner/admin; apagado, `GET /team/adherence/trend` da 404 y la tarjeta de Adherencia no cambia (addendum de `16-f15-equipo.md`). `REPORTING_WEEKLY_ENABLED`: informe semanal personal (viernes 18:00 local, email «Tu semana en Vocify»), F13.04. `REPORTING_TEAM_ENABLED`: informe semanal de equipo por email solo para owner/admin, F15.05. `NOTIFICATIONS_ACTIVITY_ENABLED`: la campana lista también lo que Vocify hizo solo en el CRM, F13.04. `HOY_NO_REPLY_ENABLED`: aviso de Hoy «no te ha respondido» (F05.05; en HubSpot necesita el permiso `sales-email-read`). `DEAL_STAGE_CONFIRM_ENABLED`: el comercial confirma la etapa del deal en la revisión de la nota y aceptar una reunión no la mueve (addendum de `12-f14-meeting-booked.md`). `REP_WORKSPACE_ENABLED`: `/dashboard` pasa a ser la casa del comercial, con un menú más corto y, para los miembros, sin Copiloto (beta) ni la tarjeta de planes (F16); apagado, la home y el menú son los de siempre. `COMMITMENT_TASKS_ENABLED`: las tareas del CRM salen de los compromisos de C04, con el texto y la fecha que enseña Hoy, y cada compromiso sale una vez en Hoy (addenda E2 de `07-f05-hoy.md` y `08-f06-acciones-y-cola.md`; necesita `INTELLIGENCE_EXTRACT_ENABLED`; en Salesforce no cambia nada). `FOLLOWUP_ENABLED`: borrador de follow-up tras cada conversación; el global sigue encendido, así que la fila sirve para apagarlo en una empresa (no se genera ninguno, ni al terminar ni al abrir la nota). Con `INTELLIGENCE_EXTRACT_ENABLED` encendido, el borrador espera a C04 hasta 30 s para usar compromisos y reunión (addendum E6 de `02-f02-followup.md`). Un flag nuevo solo necesita que su punto de uso llame a `is_enabled` con el `company_id`.

`HOY_NO_REPLY_ENABLED` (F05.05, tarjeta «no te ha respondido» en Hoy): lee los emails del comercial en HubSpot. HubSpot exige el scope `sales-email-read`, que todavía no está en `HUBSPOT_OAUTH_SCOPES`. Sin ese scope, `coverage.crm_emails` sale `forbidden` y Hoy muestra «Información incompleta». En Pipedrive siempre sale `unavailable`. Enciéndelo solo en portales HubSpot que hayan concedido el scope.

---

## 4. Secuencia de implementación (respeta dependencias técnicas Y narrativa de marca)

Estimaciones para 2 founders con Cursor y el proceso completo de 6 etapas. *(Estimación, no compromiso.)*

### Sprint 0 (sem 1) — Fundamentos
F0.1–F0.6. Sin features nuevas visibles. Es la semana que compra la calidad de las 12 siguientes.

### Sprints 1–3 (sem 2–4) — Bloque 1: «capturamos el 100%»
| Feature | Notas de construcción |
|---|---|
| **A3 · Meeting bot** (Zoom/Meet/Teams) | Si el spike F0.6 valida Recall.ai: integración de bot + calendario (Google/Microsoft OAuth) + auto-join. El output cae al pipeline como `Interaction(type=meeting)`. |
| **A4 · Botless desktop app** | Con Recall.ai Desktop SDK o captura nativa macOS/Windows. Empezar por macOS (vuestros betas). La carpeta `desktop/` ya existe. |
| **A9 · Ingesta de otros dialers** | Empezar por los 2 que usen vuestros betas (¿Ringover/Aircall?): webhook/API pull de grabaciones → pipeline. Reduce fricción de onboarding → mejora time-to-value «mismo día». |
| A7 · Multiidioma | Barato: Speechmatics ya soporta idiomas; propagar language-detect por el pipeline. Colar en cualquier hueco. |

**Hito de marca:** al cerrar A3+A4 se desbloquea el claim «captura el 100% de las interacciones» en web y pitch (el PDF lo condiciona explícitamente).

### Sprints 4–6 (sem 5–7) — Bloque 2: «el comercial solo vende»
| Feature | Notas de construcción |
|---|---|
| **B3 · Follow-up emails** | Motor: extracted → draft en la voz del rep (few-shot con sus emails reales, como Sybill). Métrica: % no-edit. Envío vía Gmail/Outlook OAuth o copy-paste v1. |
| **B4+B5 · Pre-call y pre-meeting briefs** | UN solo motor de briefs con 2 templates. Fuentes: historial de Interactions + CRM + enriquecimiento (ya tenéis Prospeo). Entrega: notificación 15 min antes (meeting) / en el dialer (cold call). |
| **B7+B8 · Tasks y follow-ups comprometidos** | Extracción de compromisos con fecha («te llamo el jueves») ya sale del pipeline; aquí se materializa en tareas + auto-agenda. Base imprescindible para B6. |
| **B2 · Matching robusto** | Subir de Parcial a Tenemos: fuzzy matching contacto/deal + UI de confirmación cuando la confianza es baja. |

### Sprints 7–8 (sem 8–9) — B6 · Organización del día (la joya)
Se construye AL FINAL del bloque 2 porque consume todo lo anterior (tasks, follow-ups, briefs, prioridad).
- Motor de priorización v1 con reglas explicables (no ML opaco): follow-ups comprometidos > leads calientes (recencia+señales) > resto por cadencia. Respeta ventanas horarias dichas por el lead (extraídas en pipeline).
- UI: "Tu día" como pantalla de inicio del rep. Cada item con su brief a un clic.
- Es el mayor diferencial potencial (nadie lo hace bien para SMB): merece sus 2 semanas completas y teardown de Salesloft Rhythm + Nooks.

### Sprints 9–11 (sem 10–12) — Bloque 3: coaching
| Feature | Notas de construcción |
|---|---|
| **C1+D10 · Scoring configurable** (primero, es el gancho de compra) | Framework como dato, no como código: el manager define criterios (o elige plantilla MEDDIC/BANT/SPICED) → el pipeline puntúa cada Interaction contra ellos. Validación: ≥80% acuerdo IA-vs-manager en 20 llamadas antes de GA. |
| **D11 · Adherencia al método** | Agregación del scoring. Casi gratis tras C1. |
| **C2 · Debrief al rep** | Mismo output del scoring, presentado al rep con clips y 1–2 mejoras concretas (no 10). |
| **C3+D3+D4 · Objeciones y competidores** | Entidades ya extraídas en pipeline desde F0.2; aquí se agregan y visualizan. |
| **D1+D2+D5 · Dashboard head of sales + reportes programados** | Consume todo lo anterior. Reportes por email/Slack con cron. |
| C8 · Reporting al rep | Variante del D5 con scope personal. |

### Colchón (sem 13–14)
Deuda de calidad detectada en QA, iteración de prompts contra evals, pulido de las métricas que no alcanzaron umbral. **Este colchón es sagrado: es la diferencia entre "hecho" y "bien hecho".**

**Total fase 1: ~14 semanas** para los 13 gaps con proceso completo. Si "lo antes posible" necesita ser más corto, se recorta ALCANCE de v1 en el spec de cada feature (etapa 2), nunca las etapas del proceso.

---

## 5. Reglas del juego (resumen para la nevera)

1. Ninguna feature entra a build sin teardown + spec + design firmado.
2. Máximo 2 features en construcción a la vez.
3. Todo prompt vive en el repo y tiene evals. Cambiar prompt = correr evals.
4. La métrica de calidad del spec decide el GA, no la sensación de "ya funciona".
5. Feature flag siempre; los 16 betas son el campo de pruebas estructurado (design partners rotativos).
6. Los 4 KPIs de negocio se miden desde el Sprint 0 — son los futuros testimonios.
7. Retro de 15 min por feature → se actualizan las rules de Cursor. El proceso mejora con cada feature.

## 6. Punto abierto único

**Build vs. buy en A3/A4 (Recall.ai u otro proveedor de infra de grabación).** Afecta coste variable por minuto grabado y dependencia de un tercero, pero cambia el bloque 1 de ~6 semanas a ~2–3. El spike F0.6 (1 día) trae los números; la decisión es vuestra.
