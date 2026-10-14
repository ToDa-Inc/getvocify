# Coaching v2 · coaching del comercial y conclusiones del Head of Sales (13 oct 2026)

Plan acordado con Toni el 13 oct 2026 tras la llamada con un Head of Sales. Sustituye las partes de
`docs/features/COACHING_SDR_AE_PLAN.md` que choquen con esto. El diagnóstico de datos del mismo día
está en `2026-10-13-coaching-mis-llamadas-y-diagnostico.md`.

## 1. Qué es cada cosa

Hay dos productos distintos y no se mezclan.

**Coaching: solo para el comercial (SDR y AE, en el dashboard y en la app de escritorio).**
- Cómo lo ha hecho en sus interacciones anteriores, separado por tipo de interacción.
- En qué pasos de su playbook no se ajusta.
- Cómo corregirlo en las próximas llamadas.
- Es feedback, no evaluación: nada de roleplay ni de ejercicios.
- Solo él contra su playbook: sin mediana del equipo, sin frases de compañeros y sin rankings.
- La misma estructura para SDR y AE; solo cambian los tipos de interacción.

**Conclusiones: solo para el Head of Sales.** Responden a tres preguntas:
1. ¿El equipo sigue el playbook? Por comercial, por paso y por tipo, comparando entre comerciales.
2. ¿El playbook funciona? Si lo siguen y no convierten, el problema es el guion; si no lo siguen, el
   comercial.
3. ¿Por qué perdemos? Causa principal de cada lost o no cualificado.

El comercial nunca ve conclusiones sobre el playbook ("el playbook no funciona").

**Pasos.** Cada empresa define los suyos en el onboarding (no hay pilares fijos para todas). Por
ahora la calibración con el cliente (qué es una buena llamada, qué se evalúa, qué respuesta a una
objeción es la correcta) es un servicio de onboarding, no una función del producto.

## 2. Coaching del comercial

Hecho el 13 oct, lo más sencillo posible: una sola pantalla plana, sin pestañas ni cajas, como Inicio
(`/dashboard/coach`, `GET /coaching/me/calls`). El botón **Playbook** junto al título abre el playbook
(`?tab=playbook`) y otro botón vuelve a Coaching.

1. **Coaching**, con un filtro por tipo de interacción (frío, inbound, discovery, demo…) cuando
   el comercial tiene más de uno. Diseño sobrio (guía: taste-skill `redesign` + `minimalist`): poco
   texto, color solo con significado (rojo sin hacer, ámbar a medias, verde hecho).
   - **En qué mejorar** (izquierda): los 1–2 pasos que más se le escapan en las últimas 4 semanas y la
     objeción que más deja sin resolver (objeciones, no obstáculos; hace falta que se repita: 2
     abiertas). Cada uno: etiqueta Paso/Objeción, título, "4/5 sin hacer", qué pasó, la frase de la
     llamada (en una objeción, también lo que respondió) y la próxima vez en verde (el consejo de la
     llamada, o la respuesta del playbook a esa objeción).
   - **Tus pasos** (derecha en escritorio): cada paso con barra, % (o "1 de 2" con menos de 3
     llamadas) y flecha frente a las 4 semanas anteriores.
   - **Tus llamadas** (debajo): todas las conversaciones del tipo en 4 semanas, una mini barra de
     pasos por llamada; las que tienen algo que mejorar se abren con el mismo detalle.
   - El paso de reunión (lo declara el comercial) no es conducta y no sale en "En qué mejorar".
2. **Playbook** (botón junto al título), solo de consulta, abierto en el tipo que se está viendo.

Se quitó del comercial: Resumen, Mi proceso, Ejemplos, el interruptor Llamadas/Reuniones, la
mediana del equipo, las frases y las "mejores llamadas" de compañeros y la conversión con o sin
proceso. Sigue pendiente: la nota 0–10 y la tarjeta "Prueba con…" en el detalle de cada llamada, y
la cualificación y las objeciones como apartados propios de "En qué mejorar".

## 3. Conclusiones del Head of Sales

Hecho el 14 oct en **Equipo** (`/dashboard/insights`, `GET /team/coaching`), con las mismas reglas de
diseño que Coaching: una pantalla plana, márgenes de Inicio, poco texto, color solo con significado.
Filtros: periodo, puesto (SDR/AE) y tipo de interacción.

- **¿Siguen el playbook?** El % del equipo (y el del periodo anterior) y un mapa de calor
  comercial × paso: verde ≥ 80 %, ámbar ≥ 50 %, rojo por debajo; con menos de 3 llamadas, la
  cuenta ("1/2") en gris. Mismo cálculo que el coaching del comercial.
- **¿Funciona el playbook?** El proceso completo y cada paso: % de reuniones con el paso y sin él, y
  un veredicto (marca diferencia / no cambia nada / va peor). Sin veredicto con menos de 5 llamadas
  a cada lado o menos de 3 reuniones; hasta entonces, una sola línea. Objetivo: la reunión que
  declara el comercial (en Vocify o en la etapa del CRM), también en AE por ahora; el avance del
  deal por etapa del CRM para AE queda pendiente.
- **¿Por qué perdemos?** Las llamadas marcadas no interesado / no cualificado en Vocify y las de
  deals perdidos en HubSpot (etapa `closedlost` del pipeline por defecto, solo lectura). La causa
  sale de la propia llamada, sin IA nueva: la objeción que quedó abierta, si no el obstáculo, si
  no el historial de ese contacto; "nunca se llegó a hablar" si no hubo conversación.

## 4. Historial cuando cambia el playbook

- Un paso cuyo criterio no cambia conserva su historial al republicar, aunque cambie su nombre o su
  identificador.
- Si cambia el criterio de un paso, su evolución empieza de cero. Las llamadas anteriores siguen en
  Mis llamadas con el veredicto que tuvieron, pero no cuentan en Qué mejorar ni en la evolución.
- Un paso nuevo empieza de cero; uno borrado sale de la evolución y queda en el historial.
- Las llamadas antiguas no se vuelven a leer con los pasos nuevos.

Esto sustituye al enfoque de la rama `fix/coaching-rescore-on-publish` (releer las llamadas de las
últimas 8 semanas al publicar), que no se fusiona.

## 5. Orden

### Fase 1 · Base (sin esto, cualquier número sale de datos malos)

1. **Identidad de un paso por su criterio** (§4). Todos los lectores de veredictos por paso usan la
   misma regla: un veredicto cuenta para un paso del playbook publicado si el criterio coincide (sin
   distinguir mayúsculas ni espacios); los veredictos antiguos sin criterio guardado caen al
   identificador.
2. **Resultado del comercial en producción:** aplicar `062_sdr_followup_cadence.sql` (`memos.rep_outcome`)
   y crear `brief_seen`. Revisar qué otras migraciones faltan. Necesita el visto bueno de Dani.
3. **Una sola definición de "% adherencia" y de "conversación"** para el comercial y para el Head
   of Sales (hecho el 13 oct, opción (a) de Toni):
   - % adherencia = pasos hechos ÷ (hechos + no hechos), de los veredictos por paso de la propia
     llamada. "Mejorable" cuenta como hecho; "No se llegó" y "Sin evidencia" no cuentan.
   - Solo pasos del playbook. La cualificación y las objeciones tienen sus propios números y no
     entran en el % (antes el Head of Sales las mezclaba y el comercial no).
   - Conversación = no es buzón ni sin respuesta, dura 30 s o más cuando se sabe, y alguien habló.
   - Con datos reales (30 días) el % del Head of Sales pasó de 54-55 % a 78-79 %: salen las
     llamadas que no eran conversación y la cualificación y las objeciones dejan de mezclarse.
4. **Pestaña Playbook del comercial:** que abra un tipo que su rol puede leer (hoy da 404).
5. **Una fila de puntuación actual por llamada:** los lectores eligen la misma (`revision_seq`).

### Fase 2 · Coaching del comercial (§2)

1. Filtro por tipo de interacción.
2. Qué mejorar con el trío "qué falló / lo que dijiste / cómo hacerlo". La frase de "cómo hacerlo"
   es una frase decible, no la guía entera del playbook.
3. Mis llamadas con el mismo trío por llamada.
4. Quitar lo que no es del comercial (§2).

### Fase 3 · ¿Por qué perdemos? (§3)

1. Guardar en Vocify cada lost o no cualificado (resultado de la llamada y etapa del CRM).
2. Extraer la causa principal de la última interacción, con historial como respaldo.
3. Agrupar las causas por tipo de interacción.

### Fase 4 · Conclusiones del Head of Sales (§3)

1. Adherencia por comercial, paso y tipo.
2. ¿Funciona el playbook?, paso a paso, también en AE con la etapa del CRM.
3. Las causas de pérdida, cruzadas con los pasos que no se siguieron.

## 6. Reglas que siguen valiendo

- Juzgar los pasos por intención, no por palabras exactas (memoria `coaching-judging-criteria`).
- Ningún porcentaje con menos de 3 llamadas; ningún veredicto sin resultados.
- La reunión agendada la declara el comercial o el CRM, nunca la IA.
- Nada se escribe en el CRM.
