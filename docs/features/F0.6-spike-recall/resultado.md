# F0.6 · Spike: build vs. buy para A3 (meeting bot) y A4 (botless desktop)

**Fecha:** 19 sep 2026 · **Fuente:** [recall.ai/pricing](https://www.recall.ai/pricing) y [recall.ai/product/desktop-recording-sdk](https://www.recall.ai/product/desktop-recording-sdk), verificadas hoy por fetch directo.

## Qué ofrece Recall.ai (datos duros)

| Concepto | Dato |
|---|---|
| Precio Pay-As-You-Go | **$0,50/hora de grabación** (mismo precio bot API y Desktop SDK), prorrateado |
| Primeras horas | 5 h gratis al registrarse |
| Transcripción integrada (opcional) | $0,15/h — pero **ya tenemos Speechmatics**, no la necesitamos |
| Storage | 7 días gratis por grabación; después $0,05/h/30 días — nos la llevamos a nuestro storage y no pagamos esto |
| Plataformas bot (A3) | Zoom, Google Meet, Microsoft Teams, Webex, GoTo Meeting, Slack Huddles |
| Botless (A4) | Desktop Recording SDK, macOS + Windows: detección automática de meeting, speaker names, join/leave events, "10 líneas de código, integración en 1 día" (claim del vendor) |
| Extra relevante | **Mobile Recording SDK** (llamadas y reuniones en persona) — cubriría A5 en fase 2 con el mismo proveedor. Marcado "SOON" en su web |
| Calendar API | Google + Microsoft Calendar para auto-join |
| Data residency | **US, EU o JP → elegir EU (GDPR)** |
| Billing | Por duración del meeting, da igual el nº de participantes |

## Coste estimado para nuestro caso *(estimación propia, no dato)*

Supuesto: 16 clientes beta × ~3 reps activos × ~5 h de meetings grabados/rep/mes ≈ **240 h/mes**.

- 240 h × $0,50 = **~$120/mes (~110 €/mes)** en PAYG.
- Escalado x4 (64 clientes): ~$480/mes.
- Por rep: 5 h/mes × $0,50 = **$2,50/rep/mes ≈ 6% del precio de 39 €**. Margen intacto.

## Build (alternativa)

- Bot propio por plataforma: Zoom SDK + Meet (sin API oficial de bots → headless browser frágil) + Teams. Estimación realista: 4–8 semanas por plataforma con mantenimiento perpetuo (cada update de Zoom/Meet rompe bots caseros).
- Botless nativo macOS (ScreenCaptureKit/audio taps): la propia comparativa de Recall admite que el audio en tiempo real es viable en nativo, pero sin speaker names, sin metadata de participantes y con ~98% de fiabilidad; los edge cases (virtual audio devices, versiones de OS) son el coste oculto.

## Recomendación

**Buy (Recall.ai) para A3+A4.** Razones:
1. ~110 €/mes hoy vs. 6–12 semanas de build + mantenimiento perpetuo de bots.
2. Un solo proveedor cubre A3 (bot) + A4 (botless) + futuro A5 (mobile SDK) — misma integración, mismo webhook al pipeline.
3. EU data residency → coherente con el claim GDPR del pitch.
4. El diferencial de Vocify NO está en la infra de grabación: está en el pipeline de extracción, el daily plan y el scoring. Cada semana en infra de bots es una semana robada al diferencial.
5. Reversible: la salida de Recall es audio+metadata → nuestro pipeline `Interaction` no sabe ni le importa de dónde viene el audio. Si algún día conviene internalizar, se cambia la fuente sin tocar el resto.

**Riesgos aceptados:** dependencia de un tercero (mitigada por la reversibilidad); coste variable que crece con el uso (bueno: crece solo si los clientes usan el producto).

## Próximo paso ejecutable

1. Crear cuenta en recall.ai (PAYG, 5 h gratis) — **requiere founder: email + tarjeta**.
2. En Cursor: implementar el spike técnico — bot que se une a un Meet de prueba, webhook recibe la grabación, cae al pipeline como `Interaction(type=meeting)` y sale una transcripción Speechmatics. Criterio de éxito: transcript correcto de un meeting real de 10 min entre los 2 founders.
3. Si el spike pasa → A3 sale de spike y entra al proceso normal de 6 etapas (el teardown y spec ya están scaffolded en `docs/features/A3/`).
