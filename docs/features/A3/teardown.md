# Teardown · A3 — Grabación de meetings online (Zoom/Meet/Teams)

> Objetivo: robar con criterio. Probar los productos de verdad antes de diseñar el nuestro.

## Competidores analizados
| Competidor | Cómo lo probamos | URL |
|---|---|---|
| Sybill (plan Free: grabaciones ilimitadas) | Trial real con un meeting nuestro | https://www.sybill.ai/pricing |
| Fathom (free forever, bot y bot-free) | Trial real con un meeting nuestro | https://fathom.video/ |
| Modjo (europea, la más comparable) | Demo/vídeos/docs | https://www.modjo.ai/en |

## Qué sabemos ya del benchmark (19/09/2026)
- **Sybill:** graba Zoom/Meet/Teams/Webex; "Invisible Recorder" (sin bot visible); summaries en <5 min; 100+ idiomas. El plan Free incluye grabaciones+transcripciones ilimitadas → su coste marginal de grabación es ~0, coherente con usar infra tipo Recall.
- **Fathom:** "bot o no bot, tú eliges"; claim de 38 min ahorrados/meeting; resultado instantáneo al acabar la llamada.
- **Attention:** botless-first como argumento de VENTA ("buyers talk differently when a recorder joins") — el botless no es solo técnica, es messaging.
- **Infra:** decisión tomada en F0.6 → **Recall.ai** ($0,50/h, bot + desktop SDK, EU residency). Ver `docs/features/F0.6-spike-recall/resultado.md`.

## Por cada competidor (COMPLETAR al probarlos)
### Sybill
- UX exacta (screenshots en ./assets/): ¿cómo conecta el calendario? ¿auto-join por defecto? ¿aviso de grabación a los asistentes?
- Cuándo entrega el resultado (latencia percibida):
- Edge cases: meeting que empieza tarde / rep que no invita al bot / meeting recurrente / 2 meetings solapados:

### Fathom
- UX exacta del onboarding (es el gold standard de time-to-value de la categoría):
- Cómo maneja el consentimiento de grabación (aviso en el meeting):

## Síntesis (COMPLETAR)
| Decisión | Qué |
|---|---|
| Copiamos | |
| Mejoramos (y por qué podemos) | Idioma/UX 100% en español; el meeting cae al MISMO timeline que las llamadas y visitas (nadie más tiene los 3 canales) |
| Ignoramos | |

## Implicaciones para el spec
- Auto-join desde calendario (Google primero; nuestros betas → confirmar si alguno vive en Outlook)
- Consentimiento: aviso configurable al entrar el bot (GDPR, two-party) — reutilizar patrón A8
