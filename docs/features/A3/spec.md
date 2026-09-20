# Spec · A3 — Grabación de meetings online (Zoom/Meet/Teams)

> BORRADOR pre-rellenado — los founders validan job, métrica y recortes antes del design.

## 1. Job to be done
"Cuando un AE tiene una demo o reunión online, quiere que la conversación quede grabada, transcrita y en el CRM sin hacer absolutamente nada, para dedicar su atención al cliente y no a tomar notas."

## 2. Audiencia y mensaje
- [x] Rep («solo vendes») — es quien vive el meeting
- [x] Head of sales — desbloquea el claim «capturamos el 100%» y el coaching sobre demos
- Frase de marketing: «Tus demos y reuniones, grabadas y en el CRM solas. Tú, a vender.»

## 3. Métrica de calidad (PROPUESTA — validar umbral)
| Métrica | Umbral para GA | Cómo se mide |
|---|---|---|
| % de meetings del calendario capturados con éxito (bot entró + audio útil) | ≥ 95% | eventos pipeline: `meeting_detected` vs `interaction_ready` |
| Time-to-transcript tras acabar el meeting | ≤ 5 min | timestamp diff |
| Meetings con speaker attribution correcta | ≥ 90% (validación manual founders, 20 meetings) | QA etapa 5 |

## 4. Comportamiento
### Flujo principal
1. Rep conecta Google Calendar (OAuth) una vez, en onboarding.
2. Vocify detecta meetings con link de Zoom/Meet/Teams y auto-agenda el bot (Recall.ai).
3. Bot entra al meeting (con nombre "Vocify Notetaker" + aviso de grabación configurable).
4. Al acabar: webhook → pipeline → `Interaction(type=meeting)` → STT Speechmatics → extracción → CRM autofill existente (B1).
5. Rep recibe notificación: resumen + link. No hizo nada en todo el flujo.

### Edge cases
| Caso | Comportamiento esperado |
|---|---|
| Meeting sin link de video (presencial/phone) | No se agenda bot; no es error |
| Rep quiere excluir un meeting (personal, interno) | Toggle por meeting en UI + reglas (ej.: solo meetings con externos) |
| Bot rechazado en la sala de espera | Notificar al rep en el momento; marcar `capture_failed` |
| Meeting empieza tarde / se alarga | Bot espera N min; graba hasta el final real |
| Audio inservible | `Interaction` con flag `low_quality`; no se generan acciones downstream con confianza baja |
| 2 meetings solapados del mismo rep | Ambos se graban (bots independientes) |
| Asistente pide no ser grabado | Rep puede parar la grabación desde la UI en vivo |

## 5. Qué NO hace la v1
- NI resúmenes en tiempo real NI coaching en vivo (fase 3).
- Sin Outlook Calendar (salvo que un beta lo necesite — confirmar).
- Sin video en el player v1: audio + transcript. El video se guarda para fase 2.
- Sin Webex/GoTo (Recall los soporta; activarlos cuando un cliente los pida).

## 6. Dependencias
- F0.6 decidido: Recall.ai (PAYG). F0.1 (`Interaction`) y F0.2 (pipeline) deben existir.
- Terceros: Recall.ai (bot + calendar API), Google OAuth, Speechmatics (existente).

## 7. Evals
- No aplica LLM nuevo (usa la extracción común del pipeline). Los evals de extracción sobre meetings se añaden al dataset común: mínimo 10 meetings reales en `backend/evals/pipeline/`.
