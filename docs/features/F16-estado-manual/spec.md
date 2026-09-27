# Spec · F16 — El comercial decide el estado; la cola obedece al CRM

> Pieza 1 de 6 del bloque «procesos SDR / AE / General». Las otras (roles, traspaso SDR → AE, Hoy por rol, playbook por proceso, vista Head of Sales) tienen su propio spec.

## 1. Job to be done
Cuando termina una llamada, el comercial quiere marcar él mismo el resultado con los estados que su empresa ya tiene en el CRM, y que la cola de rellamar saque a un contacto solo cuando ese estado lo dice, para no perder ni volver a llamar a nadie por una suposición de la IA.

## 2. Audiencia y mensaje
- [x] Ambos. Rep: «tú decides qué pasó en la llamada». Head of sales: «tu pipeline, tus estados, tus reglas».
- Mensaje: «Vocify sugiere; tu equipo decide y tu CRM manda».

## 3. Métrica de calidad (decide el GA)
| Métrica | Umbral para GA | Cómo se mide |
|---|---|---|
| Contactos que salen de la cola sin estado confirmado en el CRM | 0 | Log `queue_exit` con `reason` y estado; ninguno con `reason` inferido |
| Contacto con estado de salida recién aprobado que sigue en la cola | 0 en la siguiente carga de la cola | Test de integración + dogfooding 2 días |

## 4. Comportamiento

### Configuración (owner/admin, pantalla de CRM existente)
1. **Dónde marca el comercial el resultado:** «Etapa del deal» o «Estado del lead» (`hs_lead_status`, solo HubSpot). Pipedrive siempre usa la etapa del deal.
2. **Sale de la cola · reunión agendada:** selección múltiple de estados de la empresa. (La pieza 3 usará este grupo para pasar el contacto al AE.)
3. **Sale de la cola · fin:** selección múltiple (perdido, descalificado…). En Pipedrive incluye además «Ganado» y «Perdido» del estado del deal.
4. Los estados no marcados dejan al contacto en la cola. Sin nada marcado, nadie sale por estado.
5. La etapa de «reunión agendada» de F14 que ya exista se copia al grupo «reunión agendada».

### Revisión tras la llamada (web, extensión, desktop)
1. Modo **etapa del deal**: igual que F14 con `DEAL_STAGE_CONFIRM_ENABLED`. Fila de etapa con las etapas del pipeline del deal, sugerencia preseleccionada, se escribe al aprobar.
2. Modo **estado del lead**: siempre aparece la fila «Estado del lead», primera, con las opciones del portal. Preselección: el primer estado de «reunión agendada» si el memo tiene una reunión acordada no omitida; si no, el estado que sugiere la extracción; si no, el estado actual del contacto.
3. Solo una aprobación revisada escribe el estado. Las aprobaciones sin revisión (autoaprobación, WhatsApp) nunca lo escriben.

### Cola de rellamar (`/contact-priorities`) y Hoy (`/today`)
1. La cola lee del CRM el estado de cada contacto: `hs_lead_status` en modo lead; en modo deal, la etapa del deal asociado modificado más recientemente (Pipedrive: `status:won` / `status:lost` si el deal está ganado o perdido).
2. Un contacto cuyo estado está en «reunión agendada» o «fin» no aparece en la cola ni en Hoy.
3. Al aprobar una revisión con estado confirmado, ese estado se aplica a la cola en el momento; la siguiente lectura del CRM lo sustituye por lo que diga el CRM.
4. Con el flag encendido, `meeting_agreed` y `deal_closed` inferidos por la IA ya no sacan a nadie de la cola ni de Hoy.

### Edge cases
| # | Caso | Comportamiento esperado |
|---|---|---|
| E1 | Flag `CRM_STATE_EXIT_ENABLED` apagado | Todo igual que hoy (incluida la exclusión por `meeting_agreed`) |
| E2 | Flag encendido, admin sin estados marcados | Nadie sale por estado; `meeting_agreed` tampoco saca a nadie |
| E3 | IA detecta reunión, el comercial elige otro estado o quita la fila | El contacto sigue en la cola |
| E4 | Comercial confirma un estado de «reunión agendada» | Fuera de la cola y de Hoy en la siguiente carga |
| E5 | Comercial confirma un estado de «fin» | Fuera de la cola y de Hoy |
| E6 | Estado cambiado directamente en el CRM | Se refleja en la siguiente lectura (≤ 30 min) |
| E7 | Deal reabierto en el CRM (vuelve a un estado no marcado) | El contacto vuelve a la cola en la siguiente lectura |
| E8 | Contacto con varios deals (modo deal) | Decide el modificado más recientemente; empate → id mayor |
| E9 | Contacto sin deal (modo deal) | Sin estado → sigue en la cola. Revisión: comportamiento F14 |
| E10 | Portal sin opciones de `hs_lead_status` | «Estado del lead» deshabilitado en la configuración; si ya estaba, no hay fila y nadie sale |
| E11 | Falla la lectura de estados del CRM | Se conserva el último estado conocido; la cola avisa «puede estar incompleta» |
| E12 | Aprobación sin revisión (autoaprobación, WhatsApp) | No escribe estado, no saca a nadie |
| E13 | La escritura en el CRM falla al aprobar | No se aplica el estado a la cola |
| E14 | Pipedrive, deal ganado o perdido | Estado `status:won` / `status:lost`, seleccionables en «fin» |
| E15 | Modo lead pedido para Pipedrive | Se guarda como `deal_stage` |
| E16 | El admin cambia el modo o los estados | Aplica en la siguiente lectura de la cola (≤ 30 min) |
| E17 | Estado configurado que ya no existe en el CRM | Nunca coincide; al guardar la configuración se descartan ids que el CRM ya no ofrece |
| E18 | Tarjeta de Hoy de un memo con `deal_closed` inferido | Se muestra (con el flag encendido) salvo que el estado del CRM sea de salida |

## 5. Qué NO hace la v1
- Roles SDR / AE / General / Head of Sales, traspaso al AE, Hoy por rol, playbook por proceso, onboarding.
- Estado del lead en Pipedrive (objeto Leads) y Salesforce.
- Tocar la bajada de prioridad por reunión futura detectada (`scheduled_at`).
- Reprocesar señales de Hoy ya guardadas.

## 6. Dependencias
- F14 y `DEAL_STAGE_CONFIRM_ENABLED` (fila de etapa confirmada). F04 (cola, caché `contact_priority_context`). F05 (Hoy).
- APIs: HubSpot contacts search, deals search, associations v4 batch; Pipedrive deals v2.
- Sin prompts nuevos ni cambios de extracción.

## 7. Evals
No aplica: no hay prompts nuevos. La sugerencia de estado del lead reutiliza la extracción existente (Jev `lead_status`).
