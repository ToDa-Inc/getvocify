# Plan · Coaching en los dashboards de SDR y AE

> Fecha: 2026-09-28. Plan hermano: [`HEAD_OF_SALES_DASHBOARD_PLAN.md`](./HEAD_OF_SALES_DASHBOARD_PLAN.md).
> Contexto de producto: `docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md` §4 (Coaching) y §7.4 (adherencia). Este documento es el **plan**; cada fase tendrá después su `spec.md` según `_TEMPLATE/`.

---

## 0. Contexto mínimo (para trabajar este plan sin leer el otro)

- **Filosofía (§4.1 de la planificación):** no enseñamos a vender. **Estandarizamos el proceso que la empresa ya tiene, medimos cuánto se desvía cada comercial y señalamos el momento exacto** de la llamada. Como mucho **1 foco por persona y semana**.
- **El proceso de venta lo define el Head of Sales** en su dashboard (plan hermano §4). Incluye un proceso para SDR y otro para AE, con etapas, criterios de handoff SDR → AE y **un playbook por tipo de interacción**: pasos (obligatorios u opcionales), objeciones con su respuesta recomendada, criterio de "buena llamada" y competidores. Los playbooks tienen versiones. **El coaching puntúa contra ese playbook.**
- **Hay dos causas de que algo no funcione:**
  - el comercial **no sigue** el playbook → esto lo resuelve el **coaching** (este plan);
  - el comercial **sí lo sigue** y aun así falla → es **feedback al Head of Sales** sobre el playbook (plan hermano §5).

  El coaching solo señala al comercial cuando su adherencia es baja. Si la adherencia es alta y el resultado es malo, **no se culpa a la persona**: la señal se envía a la Salud del proceso.
- **SDR y AE tienen coaching distinto**, porque su trabajo es distinto:
  - el SDR hace **muchas llamadas cortas** para generar reuniones;
  - el AE tiene **pocas reuniones largas** que forman parte de un deal que dura semanas.

  Hay un motor de puntuación común (§2) y dos experiencias diferentes (§3 y §4).

---

## 1. Principios

1. **Un foco, no diez.** Cada semana se trabaja una sola cosa, con evidencia.
2. **Siempre con evidencia**: el minuto exacto de su propia llamada y un ejemplo de referencia del equipo.
3. **Se compara con su puesto y su antigüedad**: la mediana de su mismo puesto, nunca un SDR contra un AE, y teniendo en cuenta la fecha de alta.
4. **Motiva, no vigila.** Lo que hizo bien va primero. No hay ranking con nombres salvo que el Head of Sales lo active en Ajustes → Coaching.
5. **No interrumpe** (§4.6). El debrief corre en segundo plano y el comercial lo lee cuando quiere.
6. **Honestidad:** sin muestra suficiente no hay diagnóstico ("con 6 llamadas conectadas todavía no se puede sacar una conclusión").

---

## 2. Motor común: puntuación de cada interacción

Es un background job que se ejecuta después de la extracción del memo. Es una clasificación **acotada** (booleanos y multiselect, patrón Jev.ai de §6.4), no un LLM razonando en abierto.

Para cada interacción:
1. **Tipo de interacción** (cold call, cualificación, discovery, demo, propuesta, cierre) → decide qué playbook y qué versión se aplican.
2. **Pasos del playbook:** hecho o no hecho, con la marca de tiempo de la evidencia.
3. **Objeciones:** tipo (taxonomía cerrada), si es *objeción* u *obstáculo* (§4.4–4.5) y si se superó.
4. **Dificultad** (baja / media / alta): para que una llamada fácil no puntúe más que una batallada (§4.4).
5. **Adherencia** = pasos obligatorios cumplidos ÷ pasos obligatorios.
   **Score** = adherencia + gestión de objeciones, ajustado por dificultad.
6. **Momentos destacados:** el mejor momento y el momento a mejorar, con su marca de tiempo.

**Criterio de salida (MASTER_PLAN C1):** ≥ 80 % de acuerdo entre la IA y el manager en 20 interacciones de cada tipo antes de activarlo. Dataset de evaluación en `backend/evals/coaching/`.

**Datos que ya existen:**
- las transcripciones;
- en `MemoExtraction`: objeciones, competidores, pains, siguientes pasos y decisores en texto libre;
- `call_disposition`, `screening_outcome` y `recording_duration`;
- el resultado de la llamada converted / on hold / lost con motivo (migración 021).

---

## 3. Coaching del SDR

### 3.1 Qué es distinto

- **Volumen alto** (50–100 llamadas al día) y **llamadas cortas**. Un debrief por llamada sería ruido. Aquí el coaching se basa en **patrones agregados**, y el debrief individual queda solo para algunas llamadas elegidas.
- **Perfil junior y con mucha rotación** (§4.1). Necesita un refuerzo **diario**, corto y muy concreto.
- **Su resultado es la reunión**, y la calidad de esa reunión la confirma el AE. Por eso el handoff forma parte de su coaching.

### 3.2 Qué se mide

| Métrica | Para qué sirve en el coaching |
|---|---|
| Llamadas y % de conexión | Volumen, listas y horario (no es un problema de técnica) |
| Conversaciones útiles (≥ umbral) | Apertura: ¿consigue que no le cuelguen? |
| Conversión conversación → reunión | Pitch y objeciones |
| Reuniones con fecha y hora cerradas | Cierre de la cita |
| Realizadas / no-show | Confirmación y cualificación |
| **Calidad del handoff**: reuniones que el AE consigue avanzar | Cualificación según los criterios de handoff |
| Adherencia por paso: apertura · motivo de la llamada · cualificación · pitch · objeciones · cierre de la cita | Qué paso del playbook se salta |
| Objeciones: frecuencia y % superadas | Con qué objeción pierde más |

### 3.3 Diagnóstico y foco (reglas)

| Síntoma frente a la mediana SDR | Adherencia en ese paso | Foco |
|---|---|---|
| Pocas llamadas | — | Disciplina: bloques de llamada |
| Conexión baja con volumen normal | — | Listas u horario (con las mejores franjas del equipo) |
| Conecta pero corta rápido | Baja en *apertura* | Los primeros 30 segundos |
| Conversa pero agenda poco | Baja en *pitch* u *objeciones* | La objeción que más pierde, con la respuesta del playbook y un clip del equipo |
| Agenda sin fecha y hora o con muchos no-show | Baja en *cierre de la cita* | Cerrar día y hora y confirmar |
| Reuniones que el AE no avanza | Baja en *cualificación* | Criterios de handoff |
| Cualquiera de los anteriores | **Alta** | No es foco del comercial → la señal va a la Salud del proceso |

### 3.4 Experiencia en el dashboard SDR

- **Resumen diario** (al final del día, o al empezar el siguiente): 3 números de hoy (conectadas, conversaciones útiles, reuniones), **una cosa bien hecha** con su clip y **una a mejorar** con su clip.
- **Mi foco de la semana:** una frase, la respuesta o el paso del playbook que corresponde, 2 clips propios y 1 clip de referencia.
- **Mi embudo:** llamadas → conectadas → conversaciones útiles → reuniones → realizadas, frente a la mediana anónima de los SDR.
- **Mi adherencia por paso**, con la evolución de 4–8 semanas.
- **Mis objeciones:** las 3 que más recibo, mi % de éxito y la respuesta del playbook.
- **Llamadas para revisar:** solo las destacadas (mejor, peor, conectadas con objeciones), cada una con su debrief corto. No las 80 del día.
- **Mi playbook** en modo lectura: el guion de cold call y de cualificación.

---

## 4. Coaching del AE

### 4.1 Qué es distinto

- **Pocas interacciones, largas y de mucho valor.** Aquí sí tiene sentido un **debrief completo de cada reunión**.
- **El coaching va a nivel de deal, no solo de llamada**: lo que importa es si, a lo largo de las reuniones de un deal, se ha completado el discovery, se ha encontrado al decisor y siempre hay un siguiente paso.
- **Mira hacia delante:** antes de la siguiente reunión de un deal, el AE ve qué le faltó en la anterior.

### 4.2 Qué se mide

| Métrica | Para qué sirve en el coaching |
|---|---|
| **Discovery completo por deal**: pain, decisor, presupuesto, timing, criterios de decisión (según la plantilla elegida, p. ej. SPICED o MEDDIC) | Qué campos le suelen faltar |
| **Siguiente paso fechado** al final de cada reunión | Control del proceso |
| Avance de etapa por reunión | Si sus reuniones mueven el deal |
| Win rate por etapa y ciclo medio | Dónde se atascan sus deals |
| **Multi-threading**: nº de interlocutores por deal | Riesgo de deal con un solo contacto |
| Objeciones y competidores: % superadas | Cierre y posicionamiento |
| Adherencia por playbook: discovery · demo · propuesta · cierre | Qué tipo de reunión hace peor |
| Talk ratio y preguntas abiertas (V2, necesita diarización fiable) | Escucha |

### 4.3 Diagnóstico y foco (reglas)

| Síntoma frente a la mediana AE | Adherencia en ese paso | Foco |
|---|---|---|
| Reuniones que no avanzan el deal | Baja en *discovery* | Los campos del discovery que le faltan |
| Deals sin siguiente paso | Baja en *cierre de reunión* | Cerrar cada reunión con un siguiente paso fechado |
| Ciclo largo o deals con un solo contacto | — | Multi-threading y acceso al decisor |
| Pierde en la etapa final | Baja en *objeciones* o *cierre* | La objeción final más frecuente |
| Pierde contra un competidor concreto | Baja en *competidores* | El posicionamiento del playbook frente a ese competidor |
| Cualquiera de los anteriores | **Alta** | No es foco del comercial → la señal va a la Salud del proceso |

### 4.4 Experiencia en el dashboard AE

- **Debrief de cada reunión:** lo que hizo bien, una cosa a mejorar con el minuto exacto, la checklist del playbook de ese tipo de reunión y las objeciones con su resultado.
- **Mis deals:** para cada deal activo, el **estado del discovery** (✅ pain · ✅ presupuesto · ❌ decisor · ❌ timing) y el siguiente paso acordado.
- **Preparación de la siguiente reunión:** "en la última reunión con X faltó el presupuesto y salió la objeción Y; el playbook recomienda…". Se muestra antes de la reunión si está en el calendario.
- **Mi foco de la semana:** una frase, con clips propios y uno de referencia.
- **Mi adherencia** por tipo de reunión y **mi win rate por etapa**, frente a la mediana anónima de los AE.
- **Mi playbook** en modo lectura.

---

## 5. Común a los dos puestos

- **Resumen semanal por email** (lunes, vía Resend, §4.10): qué hizo bien, sus números frente a la semana anterior, si ha mejorado el foco de la semana pasada, el nuevo foco y un momento destacado.
- **Evolución:** cada foco se mide la semana siguiente (¿ha subido la adherencia en ese paso? ¿ha mejorado la conversión?). Así el coaching demuestra si funciona.
- **Clips de referencia del equipo:** se muestran con el nombre de quien lo hizo solo si el Head of Sales lo permite en Ajustes → Coaching.
- **Hacia el Head of Sales:** `coaching_focus` y la adherencia alimentan su tabla Equipo, la ficha de cada persona (para el 1:1) y la Salud del proceso (plan hermano §9).

---

## 6. Datos

**Tablas que son de este plan:**
- `interaction_scores`: una por memo, con score, adherencia, dificultad, tipo de interacción, `playbook_version_id` y momentos destacados.
- `interaction_steps`: paso, hecho o no, marca de tiempo.
- `interaction_objections`: tipo, objeción u obstáculo, superada, marca de tiempo.
- `coaching_focus`: persona, semana, puesto, foco, evidencia y resultado de la semana siguiente.
- `deal_discovery_status`: solo para AE, estado de cada campo del discovery por deal.

**Lo que consume del plan del Head of Sales:** `sales_role` y fecha de alta, procesos y playbooks con sus versiones, Ajustes → Coaching, capa de métricas y medianas por puesto, y las reuniones y deals de HubSpot (para el handoff y el avance de etapa).

---

## 7. Fases

| Fase | Entregable | Contenido | Depende de |
|---|---|---|---|
| **C0 · Prerrequisitos** | — | `sales_role`, playbooks con versiones y capa de métricas | Plan hermano H0–H1 |
| **C1 · Motor de puntuación** | Cada memo tiene su score y sus pasos | Clasificación acotada, taxonomía de objeciones, dificultad, evals ≥ 80 % de acuerdo | C0 |
| **C2 · Coaching SDR** | Sección de coaching en el dashboard SDR | Resumen diario, foco semanal, embudo, adherencia, objeciones, llamadas destacadas | C1 |
| **C3 · Coaching AE** | Sección de coaching en el dashboard AE | Debrief por reunión, estado del discovery por deal, preparación de la siguiente reunión, foco semanal | C1 y deals de HubSpot (H2) |
| **C4 · Resumen semanal + evolución** | Email semanal al comercial y medición del foco | Resend, `coaching_focus` con resultado; salidas hacia el Head of Sales | C2 / C3 |
| **V2** | — | Biblioteca de mejores momentos, talk ratio, coaching en vivo más allá de la tarjeta de objeciones (§4.8–4.9), roleplay | C4 |

Primero SDR y después AE: el SDR tiene más volumen, así que las evaluaciones se validan antes, y es el caso ancla de la planificación (junior y con mucha rotación).

---

## 8. Decisiones abiertas

1. **Visibilidad entre compañeros:** ¿solo la mediana anónima (por defecto) o también un ranking con nombres?
2. **Resumen del SDR:** ¿al final del día o a primera hora del día siguiente?
3. **Llamadas destacadas del SDR:** ¿cuántas al día (3?) y con qué criterio?
4. **Plantilla de discovery del AE por defecto:** ¿SPICED o MEDDIC?
5. **¿Ve el Head of Sales el debrief completo** de cada interacción, o solo los agregados y los clips?
