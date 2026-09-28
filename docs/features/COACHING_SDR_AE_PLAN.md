# Plan · Coaching y feedback para SDR y AE

> Fecha: 2026-09-28 (v2, reescrita tras la aclaración de alcance del mismo día).
> Plan hermano: [`HEAD_OF_SALES_DASHBOARD_PLAN.md`](./HEAD_OF_SALES_DASHBOARD_PLAN.md) (vive en `getvocify`).
> Contexto de producto: `docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md` §4 (Coaching) y §7.4 (adherencia), en `getvocify`.
> Evidencia de mercado: [`analisis-competidores/`](../analisis-competidores/informe-ejecutivo.md) (teardown del 21 sep: Sybill, Winn, Siro, Attention), [`competidores.md`](../competidores.md) (Piper).
> Este documento es el **plan**. Cada fase tendrá después su `spec.md`, según `_TEMPLATE/` de `getvocify`.
> Se implementa en el repo **`getvocify`**. Este workspace solo guarda el plan y la evidencia.

Etiquetas del workspace: **Hecho** (visto o confirmado) · **Pendiente** · **Apuesta** (decisión de diseño sin validar con clientes) · **Consejo** (MdV, consultor).

---

## 0. En una frase

El comercial hace su trabajo como siempre: llamadas, demos. Vocify escucha cada conversación y la compara con **el proceso de venta que ha definido el Head of Sales de su empresa**. Después le da soporte **en paralelo** por dos vías:

1. **Pestaña "Coaching"** en su dashboard: entra cuando quiere y ve cómo sigue el proceso, paso a paso, con métricas, feedback y ejemplos.
2. **Mensaje diario y semanal**, en la bandeja de la app y por email: le dice cómo lo ha hecho y qué corregir.

**El objetivo no es "vender mejor" en abstracto.** Es que el comercial pase de **vender como quiere** a **vender siguiendo el proceso de su empresa**. Hay que detectar tres cosas en cada paso:
- el paso que **se salta** (se olvida de cualificar);
- el paso que **hace flojo** (propuesta de valor débil);
- el paso que **hace fuera de sitio** (intenta cerrar antes de cualificar).

Después se le ayuda a corregirlo, **una cosa cada vez**.

**Lo que NO es:** no hay pop-ups durante la llamada, ni guion en pantalla, ni interrupciones. El comercial no tiene que hacer nada distinto para recibir coaching.

---

## 1. Contexto mínimo

- **Filosofía (§4.1 de la planificación):** no enseñamos a vender. Estandarizamos el proceso que la empresa ya tiene, medimos cuánto se desvía cada comercial y señalamos el momento exacto. Como mucho **1 foco por persona y semana**.
- **El proceso lo define el Head of Sales** (plan hermano §4). Hay uno para SDR y otro para AE, con **un playbook por tipo de interacción**: llamada en frío, demo, discovery, etc. Cada playbook tiene pasos, objeciones con su respuesta, criterio de "buena llamada" y competidores. Tiene versiones.
- **El proceso no es fijo, ni de Vocify: es de cada cliente.** Puede llegar de tres formas (§9):
  - la empresa ya lo tiene y lo importamos;
  - parte de una metodología conocida (BANT, MEDDICC, SPICED…) y la adapta;
  - no tiene ninguno y se lo creamos con un **cuestionario**.

  La pestaña, los mensajes y el motor **no saben qué metodología hay debajo**: solo leen los pasos que definió ese cliente.
- **Hay dos causas de que algo no funcione:**
  - el comercial **no sigue** el proceso → **coaching** (este plan);
  - el comercial **sí lo sigue** y aun así no convierte → no es culpa suya. Es **feedback al Head of Sales** sobre el proceso (plan hermano §5, y §10.1 aquí).
- **SDR y AE son distintos:**
  - el SDR hace muchas llamadas cortas y sabe el resultado en el momento (¿demo agendada?);
  - el AE hace pocas reuniones largas dentro de un deal que dura semanas.

  El motor es común; la pestaña y los mensajes se adaptan a cada rol (§5.3, §6.4).

---

## 2. Principios

1. **Un foco, no diez.** Cada semana se trabaja **un paso** del proceso. El mensaje diario lo refuerza. No se le lanzan 9 correcciones a la vez.
2. **Siempre con evidencia**: el minuto exacto de **su** llamada, qué dijo y cómo lo pide el proceso. Si hay, un ejemplo real de un compañero que lo hizo bien.
3. **Se compara consigo mismo y con su puesto**: primero con su propia semana anterior, después con la mediana de su mismo puesto y antigüedad. Nunca un SDR contra un AE. **Sin rankings.**
4. **El proceso es del cliente.** Nunca se puntúa contra un "buen vendedor" genérico. Es lo que le funcionó a Winn en Deel: "convirtió nuestro framework de un deck de training en algo que los reps usan y siguen".
5. **Primero el feedback, el número después.** Lo primero que ve el comercial es una frase: "ayer te saltaste la cualificación en 6 de 11 llamadas; en el 02:40 de la llamada con Acme era el momento". No un "7/10". La queja más concreta del research es contra el scoring de Attention: "the weakest area", además de "no se puede exportar".
6. **Hacer que seguir el proceso compense, con sus propios datos.** El argumento más fuerte para que un comercial cambie es ver que **él mismo** convierte más cuando sigue el proceso: "cuando haces los 5 pasos agendas 3 de cada 10; cuando te saltas la cualificación, 1 de cada 10". Este es el motor del cambio de hábito (§4.4).
7. **Solo lo que se dijo, nunca cómo se dijo.** Se evalúa el contenido verbal, no el tono, la emoción ni la "energía" (ver §3.3). El EU AI Act, art. 5.1.f, prohíbe el reconocimiento de emociones para evaluar a empleados.
8. **Cada veredicto lleva cita verificable.** Si no hay evidencia, el paso queda en "sin evidencia", nunca en "no hecho".
9. **Adopción antes que catálogo.** Sin leaderboards, gamificación ni 100 agentes: en la competencia son "features fantasma". Lo que importa es que el comercial abra el mensaje y la pestaña. Por eso son cortos y concretos.
10. **Aprendizaje por cuenta.** Los ejemplos y los datos de una empresa no salen de esa empresa. Entre clientes solo se comparten plantillas.

---

## 3. El corazón: cómo se evalúa cada paso del proceso

Todo lo que ve el comercial sale de aquí. Para cada llamada o demo, y para **cada paso** del proceso de su empresa, Vocify decide una de estas cosas:

| Estado | Significado | Ejemplo |
|---|---|---|
| ✅ **Bien hecho** | Lo hizo y cumple los criterios de calidad del paso | Propuesta de valor ligada al sector del prospecto, con un dato concreto |
| 🟡 **Hecho, pero flojo** | Lo hizo, pero falla al menos un criterio de calidad, **y se dice cuál** | "Propuesta de valor genérica: solo adjetivos, ningún dato ni caso" |
| ❌ **No hecho** | La llamada llegó a ese punto y el paso no aparece | Pidió la demo sin haber cualificado |
| ↕️ **Fuera de orden** | Lo hizo, pero en un momento que el proceso no pide (solo si el Head of Sales marca el orden como importante) | Intentó cerrar la demo antes de crear valor |
| ⚪ **No se llegó** | La llamada terminó antes por decisión del prospecto ("no me interesa", cuelga). **No penaliza** | Colgó en el gancho: los pasos 3–5 no cuentan |
| ❔ **Sin evidencia** | El motor no está seguro. **No penaliza** y no se enseña como error | Audio malo en ese tramo |

La diferencia entre **"no hecho"** y **"no se llegó"** es crítica para que el comercial confíe: no se le puede culpar de no cualificar en una llamada donde le colgaron a los 20 segundos.

### 3.1 Cómo define el Head of Sales un paso (para que se pueda evaluar)

Cada paso del proceso tiene esta ficha. La rellena el Head of Sales, con ayuda de Vocify: se propone automáticamente desde la plantilla o el cuestionario.

| Campo | Para qué sirve |
|---|---|
| **Nombre y objetivo** | En el lenguaje del equipo. "Gancho de conexión: que el prospecto sepa quién soy y por qué le llamo *a él*" |
| **Se considera hecho si…** | La condición mínima. Es la que separa ❌ de lo demás |
| **Se considera bien hecho si…** | 2–4 criterios de calidad, observables en lo que se dice. Separa ✅ de 🟡 |
| **Errores típicos** | Lo que hace flojo el paso. El motor lo usa para explicar el 🟡 |
| **Ejemplos buenos / malos** | Frases o clips reales del equipo |
| **Orden y tiempo orientativo** | "Después del gancho, antes del cierre", "menos de 45 s" |
| **Obligatorio / opcional y peso** | Si saltarse este paso es grave o no |

### 3.2 Ejemplo resuelto · Proceso SDR (llamada en frío)

Es el proceso que describiste, tal como quedaría definido en Vocify. Las frases son de ejemplo: cada empresa pone las suyas.

| # | Paso | Hecho si… | Bien hecho si… | Flojo típico |
|---|---|---|---|---|
| 1 | **Apertura** | Saluda y hace una pregunta de cortesía en los primeros ~10 s ("Buenos días, ¿qué tal? ¿Cómo vas?") | Usa el nombre del prospecto · no pide perdón ("perdona que te moleste") · deja responder antes de seguir | Entra directo al pitch sin saludar · "¿tienes un minuto?" seguido de monólogo |
| 2 | **Gancho de conexión** | Dice quién es + un motivo concreto para llamar a *esa* persona | El motivo es específico del prospecto (conectamos en LinkedIn, también estáis en Madrid, un cliente de su sector…) · incluye nombre y cargo ("soy Toni, director de expansión de Vocify") · menos de 20 s | Motivo genérico ("llamo a empresas como la tuya") · no dice su cargo o su empresa |
| 3 | **Propuesta de valor** | Explica qué hace la empresa y por qué le puede importar | Se conecta con un problema o situación del prospecto · incluye al menos una prueba concreta (dato, cliente, resultado) · menos de ~45 s · termina con una pregunta | Solo adjetivos ("somos los mejores, crecemos muchísimo") · monólogo de más de 60 s · no habla del prospecto |
| 4 | **Cierre a demo** | Propone una reunión o demo | Propone **fecha y hora concretas** (idealmente 2 opciones) · confirma quién asistirá y a qué email va la invitación | "¿Te mando info y hablamos?" · "¿Cuándo te va bien?" sin fecha · no confirma el email |
| 5 | **Cualificación** | Hace al menos 1 de las preguntas de cualificación del playbook | Cubre los criterios que define la empresa (p. ej. tamaño del equipo comercial, CRM que usan, quién decide, momento) · **se cuentan uno a uno**: "3 de 4" | Cualifica solo con "¿os interesaría?" · se olvida de quién decide |

Con esto, **una llamada queda así** (lo que ve el comercial, §5.2):

```
Llamada con Laura Pérez (Acme) · 4:12 · Demo agendada ✔
① Apertura ✅   ② Gancho ✅   ③ Propuesta 🟡   ④ Cierre ✅   ⑤ Cualificación ❌
                               00:48 "Somos una empresa que crece muchísimo…"
                               → Flojo: ninguna prueba concreta ni conexión con su caso.
                                                                   ⑤ Cerraste la demo sin preguntar quién decide ni qué CRM usan (03:20)
```

Y el resumen de la llamada para el comercial es **una sola línea**: "Agendaste, pero sin cualificar: el AE llegará a ciegas. Pregunta CRM y decisor antes de proponer fecha".

### 3.3 Nota sobre la "energía" en la apertura

El ejemplo dice "abre la llamada **con energía**". El tono y la energía de la voz **no se evalúan**, por tres motivos:
- es inferir estados emocionales de un empleado para evaluarle (EU AI Act);
- no es fiable;
- genera desconfianza.

Lo que sí se evalúa es lo observable que suele ir con la energía: la fórmula de saludo, la pregunta abierta, que no pida perdón, que deje hablar y el ritmo (el tiempo hasta la primera pregunta). Si el Head of Sales quiere juzgar la energía, lo hace él escuchando. La pestaña del manager le pone esas llamadas a mano (plan hermano).

### 3.4 Ejemplo resuelto · Proceso AE (demo)

Es un ejemplo de lo que traería la plantilla de demo; cada empresa lo adapta.

| # | Paso | Bien hecho si… | Flojo típico |
|---|---|---|---|
| 1 | **Agenda y objetivo** | Dice qué se va a ver, cuánto dura y qué se decide al final · pregunta si falta alguien | Empieza a compartir pantalla sin encuadre |
| 2 | **Recap del dolor** | Recuerda con palabras del cliente lo que se habló en el discovery y **lo confirma** ("¿sigue siendo así?") | Recap genérico o ninguno · no confirma |
| 3 | **Demo dirigida al dolor** | Enseña solo las 2–3 partes ligadas a los dolores confirmados · pregunta "¿esto cómo lo hacéis hoy?" | Tour completo del producto · monólogo de más de 5 min sin preguntar |
| 4 | **Objeciones y preguntas** | Las objeciones se responden según el playbook · se comprueba que quedó resuelta | Se esquiva · se responde con descuento de entrada |
| 5 | **Próximos pasos** | Siguiente paso con **fecha, responsable y quién más participa** (decisor) | "Te mando la propuesta y me dices" |

En el AE, además, se mira **el deal entero**: qué criterios de cualificación del playbook (decisor, presupuesto, proceso de compra, plazo…) ya se conocen después de todas las reuniones (§5.3).

---

## 4. Qué se le corrige al comercial, y en qué orden

### 4.1 Prioridad de las correcciones

Cada semana, para cada comercial y cada paso, se mira qué pasa **de forma repetida**, no en una llamada suelta. Orden de prioridad:

1. **Pasos obligatorios que se salta** (❌ repetido). Ejemplo: "no cualificas en el 55 % de tus llamadas".
2. **Pasos que hace flojo** (🟡 repetido), **con el criterio concreto** que falla. Ejemplo: "tu propuesta de valor no lleva ninguna prueba concreta en 8 de 10 llamadas".
3. **Orden y tiempos**, si el Head of Sales los marcó como importantes. Ejemplo: "intentas cerrar antes de crear valor".
4. **Objeciones mal gestionadas** frente a la respuesta del playbook.

Dentro del mismo nivel gana el paso con:
- más distancia frente a su propia media anterior y frente a la mediana de su puesto;
- más peso en el proceso;
- más relación con el resultado **en esa empresa**: "cuando se hace este paso, se agendan más demos";
- más oportunidades de practicarlo: sale en muchas llamadas.

### 4.2 El foco de la semana

- **Un solo paso**, y a ser posible **un solo criterio** de ese paso. Por ejemplo: "Esta semana: en la cualificación, pregunta siempre quién decide".
- Se elige el lunes y dura hasta que lo corrija o como mucho 3 semanas; después rota para no atascarse.
- Hacen falta ≥3 llamadas con evidencia para elegirlo. **Si no hay nada claro, no hay foco**, y se le dice ("vas bien, sigue así").
- A un SDR recién incorporado no se le pone foco en un paso opcional mientras falle en uno obligatorio.

### 4.3 Qué pasa con el resto de errores

No se esconden: aparecen en la pestaña, en el detalle de cada llamada y en la vista "Mi proceso". Pero **los mensajes solo hablan del foco**, y como mucho de una cosa más.

### 4.4 Cómo se consigue que cambie de hábito (el porqué del diseño)

| Palanca | Cómo aparece |
|---|---|
| **Ver el hueco con sus propios datos** | "Cualificas en 4 de cada 10 llamadas; el equipo SDR, en 8 de cada 10" |
| **Ver que el proceso le funciona a él** | "Tus llamadas con los 5 pasos: 30 % de demos. Sin cualificación: 11 %". Solo con muestra suficiente; si no, se usa el dato del equipo |
| **Saber exactamente qué decir** | La frase o pregunta recomendada del playbook, y un clip de un compañero que lo hizo bien |
| **Ver progreso diario** | "Hoy has cualificado en 7 de 9 (ayer 4 de 11)" |
| **Reconocimiento cuando lo consigue** | "Foco conseguido: 3 días seguidos cualificando en más del 80 %. Siguiente foco el lunes". Sin rankings ni puntos |
| **Que su manager lo vea** | La adherencia por paso llega al dashboard del Head of Sales (plan hermano). El comercial sabe que el proceso importa |

---

## 5. Superficie 1 · Pestaña "Coaching" en el dashboard del comercial

Una sola pestaña, con **4 vistas** (5 en AE). Se abre en "Resumen".

### 5.1 Vista "Resumen" (la que se abre por defecto)

De arriba abajo:

1. **Mi foco de la semana.** Qué paso y qué criterio · por qué, con sus datos · progreso de esta semana día a día (L M X J V) · botón "ver cómo hacerlo" (frase del playbook + clip de referencia).
2. **Mi proceso, últimos 7 días.** Barra con los pasos del proceso de su empresa. Cada paso muestra el % bien hecho, con color, y la flecha frente a la semana anterior:
   ```
   Apertura 92% ↑   Gancho 78% →   Propuesta 41% ↓   Cierre 70% ↑   Cualificación 38% ↓
   ```
   Al pulsar un paso se va a su detalle (§5.3, vista "Mi proceso").
3. **Mis números de la semana** (4 cifras, según el rol; ver §7).
4. **Seguir el proceso te funciona.** Una frase comparando su conversión con el proceso completo frente al incompleto (§4.4). Solo aparece cuando hay datos suficientes.
5. **Último mensaje** (diario o semanal), con enlace a la bandeja.

### 5.2 Vista "Mis llamadas" (SDR) / "Mis reuniones" (AE)

- Lista cronológica de conversaciones. Por cada una:
  - la **tira de pasos** (✅🟡❌↕️⚪) de §3.2;
  - el resultado (demo agendada, siguiente paso…);
  - la duración;
  - la línea de resumen.
- **Filtros útiles para corregir el hábito**: "llamadas donde me salté la cualificación", "propuestas flojas", "con objeción de precio", "demos agendadas".
- **Detalle de una llamada:**
  - reproductor y transcripción;
  - una **línea de tiempo con los pasos marcados en su minuto**;
  - para cada paso: el veredicto, la cita, el porqué ("flojo: sin prueba concreta") y **cómo lo pide el proceso**;
  - una **reescritura sugerida** con el contexto de esa llamada ("aquí podrías haber dicho: 'Trabajamos con X, que como vosotros…'"), marcada como sugerencia;
  - objeciones detectadas y cómo se respondieron;
  - botón **"no estoy de acuerdo"** (disputa, §10.4).

### 5.3 Vista "Mi proceso" (métricas paso a paso)

- **Tabla paso × semana** (últimas 6–8 semanas) con el % bien hecho. Se ve en qué paso ha mejorado y en cuál no.
- Por cada paso:
  - % hecho y % bien hecho;
  - **el criterio que más falla** ("en cualificación, la pregunta que más te saltas es *quién decide*: 70 %");
  - tiempo medio en el paso;
  - la **mediana de su puesto** como referencia (una línea, sin nombres).
- **Objeciones:** las que más le salen, % respondidas según el playbook y % en las que la llamada siguió adelante.
- **Solo AE — Mis deals:**
  - para cada deal abierto, los criterios de cualificación del playbook (decisor, presupuesto, proceso de compra, plazo…) con su estado: sabido / parcial / desconocido, y la cita de la reunión donde salió;
  - alertas sencillas: "3 reuniones y sin decisor identificado", "siguiente paso sin fecha";
  - **qué te falta preguntar en la próxima reunión** con ese deal.

### 5.4 Vista "Ejemplos"

- Por cada paso del proceso y cada objeción: la **frase o respuesta recomendada** del playbook y los **mejores momentos reales del equipo**.
- Solo se usan clips bien hechos y con buen resultado; el Head of Sales puede fijar o vetar clips.
- Es lo que usa un comercial nuevo para aprender "cómo lo dice el mejor". En Siro/Bath Fitter esto redujo el onboarding un 50 %.
- Aquí también se ve el **historial de focos**: qué se trabajó cada semana y si se consiguió.

### 5.5 Qué NO hay en la pestaña

- No hay ranking entre compañeros.
- No hay nota global "7/10" como protagonista. La adherencia existe, pero se muestra como "pasos bien hechos: 3 de 5".
- No hay métricas de tono o emoción.
- No hay ajustes del proceso: eso es del Head of Sales.

---

## 6. Superficie 2 · Mensaje diario y semanal (bandeja en la app + email)

### 6.1 Canal y horario

- **Bandeja "Coaching" dentro de la app**, con aviso de no leído, y **el mismo mensaje por email**. Cada comercial puede desactivar el email, no la bandeja.
- **Diario**: por defecto **a primera hora del día siguiente** (8:30, hora local), antes de empezar a llamar. Así "lo que corregir" se aplica ese mismo día. El Head of Sales puede cambiarlo a final del día. **Decisión abierta** (§14).
- **Semanal**: el **lunes a primera hora**. Sustituye al diario de ese día.
- **Si no hubo llamadas, no hay mensaje.** Con muy pocas conversaciones (p. ej. un SDR con menos de 3), el diario se acumula al día siguiente.
- **Opcional, más adelante:** por WhatsApp, que ya es canal de Vocify.

### 6.2 Mensaje diario · SDR

**Asunto:** "Ayer: 14 conversaciones, 3 demos · Hoy: pregunta quién decide"

1. **Tus números de ayer**: conversaciones · demos agendadas · llamadas con el proceso completo (p. ej. 5 de 14).
2. **Tu proceso ayer**: la tira de pasos con el % de cada uno.
3. **✔ Lo mejor de ayer**: un momento concreto bien hecho, con enlace al minuto. Ejemplo: "Tu gancho con Laura (00:22) es de manual: motivo concreto y cargo en 12 segundos".
4. **↗ Lo que corregir hoy**: **siempre ligado al foco**, salvo que haya algo obligatorio más grave. Incluye:
   - el dato ("6 de 11 sin preguntar quién decide");
   - un momento suyo con minuto ("con Acme, en el 03:20, propusiste fecha sin saber quién decide");
   - cómo hacerlo, con la frase del playbook.
5. **Tu foco esta semana**: progreso del lunes a hoy.
6. Botón **"Ver en Coaching"**.

Como máximo son 1 cosa buena y 1 cosa a corregir. Se lee en menos de 1 minuto.

### 6.3 Mensaje semanal · SDR

**Asunto:** "Tu semana: cualificación 38 % → 71 % · Nuevo foco: propuesta de valor"

1. **Resultado del foco de la semana pasada**: conseguido o no, con la evolución día a día.
2. **Tu semana en números** frente a la anterior: conversaciones, demos, % proceso completo y **% bien hecho por paso**.
3. **Seguir el proceso te funciona**: su conversión con el proceso completo frente al incompleto (cuando hay muestra).
4. **Nuevo foco** para esta semana, con su porqué, un momento suyo y un ejemplo del equipo.
5. **2 llamadas para escuchar** (5 minutos): una suya, para ver el error, y una de referencia del equipo.

### 6.4 Diferencias en el AE

- **Diario solo los días con reuniones.** Por cada reunión de ayer (suelen ser pocas):
  - la tira de pasos del tipo de reunión (discovery, demo, negociación…);
  - lo mejor y lo que corregir;
  - el siguiente paso que quedó (¿con fecha?).
- Además, **"Para hoy"**: las reuniones del día con lo que falta saber de cada deal. Ejemplo: "Demo con Acme a las 12:00: aún no sabes quién firma ni el presupuesto; pregúntalo antes de enseñar precios". Es coaching **antes** del error, pero en el mensaje, no durante la llamada.
- **Semanal**:
  - foco;
  - adherencia por paso en las reuniones de la semana;
  - **estado de cualificación de sus deals abiertos** (qué deals tienen huecos);
  - deals sin siguiente paso con fecha.
- Como el AE tiene pocas reuniones, la comparación es sobre todo **consigo mismo** y contra el objetivo del Head of Sales. La mediana del puesto solo se usa si hay volumen.

### 6.5 Tono de los mensajes

- En segunda persona, concreto, sin halagos vacíos ni reproches.
- Siempre: **dato → momento suyo → cómo hacerlo**.
- Nunca palabras como "mal", "fallo" o "suspenso". Se usa "te saltaste", "más flojo", "prueba a".
- El mensaje lo **genera el LLM a partir de datos ya calculados**, con una plantilla fija. El LLM redacta, no decide: los números, el foco y los clips los elige el motor.

---

## 7. Métricas: qué se calcula, qué ve el comercial

| Métrica | SDR | AE | Dónde la ve el comercial |
|---|---|---|---|
| **% bien hecho por paso** (y % hecho) | ✔ | ✔ | Resumen, Mi proceso, mensajes |
| **Criterio que más falla por paso** | ✔ | ✔ | Mi proceso, mensajes (si es el foco) |
| **Llamadas/reuniones con proceso completo** | ✔ | ✔ | Resumen, mensajes |
| **Pasos bien hechos por llamada** (3 de 5) | ✔ | ✔ | Mis llamadas |
| **Progreso del foco** (día a día) | ✔ | ✔ | Resumen, mensajes |
| **Conversión con proceso completo vs. incompleto** | ✔ | ✔ (avance de etapa) | Resumen, semanal |
| **Conversaciones** (se excluyen buzón, no contesta y menos de 30 s) | ✔ | — | Resumen, mensajes |
| **Demos agendadas / % sobre conversaciones** | ✔ | — | Resumen, mensajes |
| **Demos celebradas** (no-show del AE) | ✔ | — | Semanal |
| **Calidad de handoff** (según el AE, ¿cumplía el criterio de paso a AE?) | ✔ | da el feedback | Mi proceso, semanal |
| **Reuniones por tipo** | — | ✔ | Resumen |
| **Siguiente paso con fecha y responsable** | — | ✔ | Resumen, mensajes |
| **Cualificación del deal** (criterios conocidos) | — | ✔ | Mis deals, "Para hoy", semanal |
| **Avance de etapa de los deals** | — | ✔ | Semanal |
| **Objeciones: % respondidas según el playbook** | ✔ | ✔ | Mi proceso |
| **Tiempo por paso / % que habla el comercial / monólogo más largo** | ✔ | ✔ | Detalle de llamada (quién habla y cuánto es contenido, no emoción) |

**Referencias de comparación**, siempre en este orden:
1. él mismo la semana anterior;
2. la mediana de su puesto y tramo de antigüedad (0–3, 3–6 y más de 6 meses) si hay al menos 3 personas y 30 llamadas en 4 semanas;
3. si no, el objetivo que fija el Head of Sales.

**Muestras mínimas:** no se afirma "te funciona el proceso" con menos de ~30 conversaciones SDR o ~8 reuniones AE en la ventana. Por debajo se dice "tendencia" o no se muestra.

---

## 8. Motor de análisis (común)

```
Llamada/reunión grabada (dialer, extensión, Companion) → transcripción + quién habla (comercial / prospecto)
  → 0. ¿Es conversación? (buzón, no contesta, menos de 30 s → cuenta como actividad, no se evalúa)
  → 1. Tipo de interacción (llamada en frío, demo, discovery… según el playbook del cliente)
  → 2. Localizar cada paso en la transcripción (minuto de inicio y fin)
  → 3. Veredicto por paso: ✅ / 🟡 (+ criterio que falla) / ❌ / ↕️ / ⚪ / ❔, con cita literal
  → 4. Objeciones: categoría del playbook, respuesta del comercial, ¿alineada?, ¿siguió la llamada?
  → 5. Criterios de cualificación conocidos (y, en el AE, se acumulan al deal)
  → 6. Verificar citas: el texto existe en la transcripción; si no, se descarta
  → 7. Resultado: SDR = demo agendada (calendario/HubSpot) · AE = siguiente paso con fecha, cambio de etapa (llega después)
  → 8. Guardar → alimenta la pestaña, los mensajes y el dashboard del Head of Sales
```

- Es **asíncrono** y va aparte de la aprobación del CRM, así que no frena el flujo actual de memos. Se enchufa detrás del pipeline de transcripción que ya existe (**Hecho** en `getvocify`: Deepgram/Speechmatics → OpenRouter).
- **LLM por OpenRouter**, con salida JSON validada con Pydantic. En cada análisis se guardan `model`, `prompt_version` y `playbook_version_id` para poder re-evaluar y comparar.
- Las llamadas SDR son cortas, así que el coste es bajo. Las reuniones AE se evalúan por tramos. **El coste por llamada se mide en F1** antes de cerrar el precio.
- Se reutiliza el glosario (nombres de producto y competidores, spanglish).
- **Prerrequisitos que hoy no están (Pendiente):**
  - organización, equipo, rol y fecha de alta: hoy todo es por usuario;
  - diarización comercial / prospecto;
  - leer el resultado en HubSpot (reunión creada, etapa del deal);
  - llamada registrada como **actividad de llamada** en HubSpot (ya pendiente en MdV).

---

## 9. De dónde sale el proceso: playbook adaptable a cada cliente

La pestaña y los mensajes funcionan igual para cualquier empresa porque todos leen el mismo formato (`PlaybookSpec`, versionado):

```
Playbook (1 por organización) → versiones (borrador → sombra → publicada → archivada)
  └── por rol (SDR, AE) → tipos de interacción (llamada en frío, discovery, demo, negociación…)
        ├── pasos[]: nombre, objetivo, "hecho si", "bien hecho si" (2–4 criterios), errores típicos,
        │           ejemplos, orden, tiempo orientativo, obligatorio/peso
        ├── criterios de cualificación (BANT, MEDDICC, SPICED… o los propios)
        ├── objeciones[]: cómo suena, respuesta recomendada, ejemplos
        ├── competidores[] · qué es "buena llamada" · cuándo descalificar es lo correcto
        └── criterio de handoff SDR → AE
```

- **Entre 5 y 9 pasos por tipo de interacción.** Con más, el comercial no los interioriza y la evaluación pierde precisión.
- **Versiones inmutables.** Cada evaluación sabe contra qué versión se hizo, y el Head of Sales puede cambiar el proceso sin romper el histórico.

### 9.1 Tres formas de crearlo

| Camino | Para quién | Cómo |
|---|---|---|
| **A · Importar** | Ya tiene playbook (PDF, deck, guion, Notion) | La IA propone los pasos con su ficha (§3.1) y cita de dónde sale cada uno · marca los huecos ("no dice qué hacer si dicen 'ya tenemos proveedor'") · los huecos se completan con las preguntas del cuestionario que falten |
| **B · Plantilla** | Usa o quiere una metodología conocida | Plantillas en español: **llamada en frío SDR** (la de §3.2), **BANT**, **SPICED**, **MEDDICC**, **SPIN**, **Challenger**, **demo AE** (la de §3.4) · hay que ajustarla: objeciones, competidores, frases propias. Sin ajustar no se publica |
| **C · Cuestionario** | No tiene nada escrito | Ver §9.2 |

### 9.2 Cuestionario para crear el proceso desde cero

Son 20–30 minutos, en bloques y guardando el progreso. Se puede responder escribiendo o **por voz**: el Head of Sales cuenta cómo vende y la IA rellena las respuestas.

| Bloque | Preguntas (resumen) | Genera |
|---|---|---|
| 1. Qué vendéis | Producto, ticket, recurrente o no, duración del ciclo | Metodología base recomendada (§9.3), tipos de interacción |
| 2. A quién | Cargo que decide y cargo que usa; ¿una persona o un comité? | Criterios de cualificación |
| 3. Cómo llegan los leads | Outbound, inbound; ¿hay SDR separado del AE? | Roles y procesos |
| 4. Etapas | Etapas del pipeline y **qué tiene que ser verdad para pasar a la siguiente** | Handoff SDR → AE, "buena llamada" |
| 5. La mejor llamada | "¿Qué hace tu mejor comercial en los primeros 2 minutos? ¿Cómo engancha, cómo presenta, cómo cierra?" | Pasos y "bien hecho si" |
| 6. La peor llamada | "¿Qué hace un comercial nuevo que te desespera?" | Errores típicos, pasos obligatorios |
| 7. Objeciones | Las 5 más frecuentes y cómo responde el mejor | Objeciones |
| 8. Competencia | Con quién os comparan y qué decís | Competidores (+ glosario) |
| 9. Descalificación | Cuándo hay que cortar y no insistir | Qué no penaliza |
| 10. Referentes | ¿Quién es hoy tu mejor SDR y tu mejor AE? | Llamadas semilla para calibrar y para "Ejemplos" |

**Salida:**
1. El proceso v0, marcado como **provisional**, con la metodología recomendada explicada.
2. Una página de resumen para compartir con el equipo. Muchas pymes no tienen ni eso por escrito, y **ya es valor antes de evaluar nada** (**Apuesta**: ningún competidor documenta este camino).

### 9.3 Metodología recomendada (reglas legibles, no un modelo)

- Hay SDR outbound → **llamada en frío + BANT ligero**.
- Ciclo <30 días y un decisor → AE con **BANT**.
- Ciclo de 30–90 días y 2–3 personas deciden → **SPICED**.
- Ciclo >90 días, compras/legal, >3 personas deciden → **MEDDICC**.
- Problema que el cliente no reconoce → se añaden pasos **SPIN / Challenger** al discovery.

El Head of Sales siempre decide; la regla es solo el punto de partida.

### 9.4 Calibración antes de enseñarle nada al comercial

1. **Modo sombra**: unas 2 semanas, o ≥50 llamadas SDR / ≥10 reuniones AE. Se evalúa todo, pero **solo lo ve el Head of Sales**. Ni pestaña ni mensajes para el comercial.
2. **Llamadas de control**: el Head of Sales (o Vocify con él) marca 15–20 llamadas a mano. Un paso solo se enseña al comercial cuando Vocify coincide **≥85 %** con esas marcas. Los que no llegan se reescriben o siguen en sombra.
3. **Propuestas a partir de los mejores**: "tus demos agendadas casi siempre incluyen X, que no está en el proceso: ¿lo añadimos?". Son propuestas al Head of Sales, nunca cambios automáticos.
4. **Antes de publicar una versión nueva**, se re-evalúa una muestra con las dos versiones y se enseña qué cambiaría.

---

## 10. Cerrar el bucle con el Head of Sales

### 10.1 ¿Es culpa del comercial o del proceso?

Por paso, con una ventana de 4 semanas y muestra mínima:

| | **Convierte** | **No convierte** |
|---|---|---|
| **Sigue el paso** | ✅ Nada que hacer; sus momentos pasan a "Ejemplos" | 🔁 **Señal de proceso al Head of Sales**: "el paso se hace bien y no convierte". **No se le corrige al comercial** |
| **No sigue el paso** | 🔍 **Posible hueco del proceso**: gana sin seguirlo → propuesta al Head of Sales | 🎯 **Coaching**: candidato a foco |

Si la mayoría del equipo falla en el mismo paso, no son N focos individuales: es formación o un paso mal definido, y va al Head of Sales.

### 10.2 Comentario del manager → regla del proceso

Un comentario del manager en un momento de una llamada ("aquí había que preguntar por el ERP") puede proponerse como regla. Si el Head of Sales la acepta, entra en la siguiente versión del proceso y **aparece en "Ejemplos" y en los mensajes de todo el equipo**.

### 10.3 Objeción → respuesta → resultado

Cada objeción queda enlazada con la respuesta y con lo que pasó después. Con volumen, se puede proponer al Head of Sales qué respuesta funciona mejor ("para 'ya tenemos proveedor', la respuesta B consigue demo el doble de veces"). Así se sabe **qué funcionó**, no solo qué se dijo.

### 10.4 Disputas

- El comercial puede pulsar "no estoy de acuerdo" en cualquier veredicto, con un motivo de una línea.
- Las disputas aceptadas corrigen las llamadas de control.
- Si más del 15 % de los veredictos de un paso se disputan, ese paso vuelve a modo sombra.

---

## 11. Modelo de datos y API (orientativo, Supabase con RLS por organización)

Hay que verificarlo contra el esquema real de `getvocify` en la spec de F0.

| Tabla | Campos clave |
|---|---|
| `organizations`, `org_members` | `role` (sdr/ae/manager/head_of_sales/admin), `team_id`, `started_at` — **prerrequisito** |
| `playbooks`, `playbook_versions` | `status` (draft/shadow/published/archived), `spec` JSONB, `source` (import/template/questionnaire), `published_at` |
| `playbook_sources` | Archivo, texto, voz o respuestas del cuestionario del que salió cada versión |
| `interactions` (o columnas en `memos`) | `org_id`, `user_id`, `role`, `interaction_type`, `is_conversation`, `duration`, `hubspot_deal_id` |
| `call_analyses` | `interaction_id`, `playbook_version_id`, `steps_done_well`, `steps_applicable`, `model`, `prompt_version`, `cost_cents` |
| `step_results` | `analysis_id`, `step_id`, `status` (well/weak/missing/out_of_order/not_reached/no_evidence), `failed_criteria[]`, `quote`, `t_start_ms`, `t_end_ms`, `confidence`, `suggested_rewrite`, `disputed` |
| `objection_events` | `category_id`, citas del prospecto y del comercial, `t_ms`, `aligned`, `continued` |
| `interaction_outcomes` | `type` (meeting_booked/meeting_held/stage_advanced/next_step_dated/won/lost), `source`, `at` — llegan más tarde |
| `deal_qualification` | `hubspot_deal_id`, `field_id`, `state`, evidencia |
| `coaching_focuses` | `user_id`, `week`, `step_id`, `criterion_id`, `baseline`, `target`, `daily_progress` JSONB, `status` |
| `coaching_messages` | `user_id`, `kind` (daily/weekly), `period`, `payload` JSONB (datos ya calculados), `body_md`, `sent_email_at`, `read_at`, `opened_cta_at` |
| `coaching_prefs` | `user_id`, `email_enabled`, `daily_time`, `timezone` |
| `reference_moments` | `step_result_id` u `objection_event_id`, `pinned`, `vetoed` |
| `playbook_proposals` | Origen (comentario del manager, patrón de resultados, disputa), `status` |

**Endpoints (FastAPI, `/api/v1`):**
- `coaching/me/summary`, `coaching/me/interactions`, `coaching/interactions/{id}`, `coaching/me/process` (paso × semana), `coaching/me/deals` (AE), `coaching/examples`, `coaching/me/messages` (+ `PATCH` para marcar como leído), `coaching/results/{id}/dispute`, `coaching/export` (CSV para el manager).
- `playbooks`: `import`, `from-template`, `questionnaire`, `versions/{v}/shadow|publish`, `versions/{v}/diff`.
- **Jobs programados:** el mensaje diario (por zona horaria del usuario) y el semanal (lunes). Selección del foco el lunes antes del semanal. Envío de email con el proveedor que ya use `getvocify` (**verificar**).

**Frontend** (según `RULES.md`: features aisladas, archivos pequeños):
- `src/features/coaching/`: `summary/`, `interactions/`, `process/`, `deals/`, `examples/`, `inbox/`;
- `src/features/playbook/`: editor, importador, cuestionario, plantillas;
- la ruta `dashboard/coaching` solo compone.

---

## 12. Fases, con condición para avanzar

| Fase | Qué se construye | Con quién | Condición para avanzar |
|---|---|---|---|
| **F0 · Cimientos** | Organización, roles y fecha de alta · diarización · filtro de conversación · resultado desde HubSpot · llamada como actividad en HubSpot | MdV | Rol, diarización y resultado fiables en ≥90 % de las llamadas de MdV |
| **F1 · Proceso + motor en sombra** | Formato de playbook y versiones · los 3 caminos (importar, plantilla, cuestionario) · evaluación por paso (§3) · verificación de citas · llamadas de control · vista solo para el Head of Sales · exportación CSV | MdV + 1 empresa sin playbook (probar el cuestionario) | ≥85 % de coincidencia en ≥4 pasos · el Head of Sales dice "esto es como vendemos" · coste por llamada medido |
| **F2 · Coaching SDR: pestaña + mensajes** | Pestaña (Resumen, Mis llamadas, Mi proceso, Ejemplos) · mensaje diario y semanal (bandeja + email) · foco semanal · disputas | SDR de MdV | ≥60 % de los SDR abren el mensaje diario 3+ días a la semana durante 4 semanas · el paso foco mejora en ≥50 % de los focos · disputas <15 % |
| **F3 · Coaching AE** | Proceso de demo/discovery · vista "Mis deals" · "Para hoy" en el diario · feedback de handoff al SDR | Primer cliente con AE separado | Los AE abren el diario los días con reunión ≥60 % · el Head of Sales valida las alertas de deal |
| **F4 · Bucle con el Head of Sales** | Culpa del comercial vs. del proceso (§10.1) · propuestas al proceso · objeción → respuesta → resultado | Cuentas con ≥8 semanas de datos | ≥1 cambio de proceso aceptado por cuenta · primer caso con nombre, cargo y cifra |
| **F5 · Solo si hay evidencia** | Mensajes por WhatsApp · roleplay de objeciones · ayuda durante la llamada | — | La ayuda durante la llamada queda fuera del alcance actual ("en paralelo"). Además es una trampa de tiempo según `capa-de-decision.md` |

**SDR va antes que AE**: el resultado es inmediato, hay más volumen y MdV está ahí.

**Encaje con la estrategia:** `foco-comercial.md` (**Consejo**) pide "no construir más", y `capa-de-decision.md` dice que se puntúe contra el playbook "solo si lo piden ≥3 clientes de pago". F0 es lo que MdV ya necesita, y F1 corre en sombra. Se avanza **por evidencia**, no por calendario.

---

## 13. Cómo sabremos que funciona

| Qué mide | Métricas |
|---|---|
| **Adopción** (lo primero) | % de mensajes diarios abiertos · % que hacen clic en "Ver en Coaching" · visitas semanales a la pestaña |
| **Cambio de hábito** (lo que se vende) | % bien hecho del paso foco, antes y después · % de llamadas con el proceso completo, por semana · focos conseguidos |
| **Negocio** (con muestra suficiente) | Demos agendadas por conversación (SDR) · siguiente paso con fecha y avance de etapa (AE) · semanas hasta que un nuevo llega a la mediana del puesto |
| **Manager** | Horas de escucha por semana antes y después (referencia de Siro: −90 %) |
| **Confianza en el motor** | Coincidencia con las llamadas de control · % de disputas |

Ninguna cifra se publica sin medirla en el propio cliente, y las cifras no se reutilizan entre casos.

---

## 14. Decisiones abiertas

1. **¿Mensaje diario a primera hora del día siguiente o al acabar el día?** Propuesta: por la mañana, porque se aplica ese mismo día. Configurable por empresa.
2. **¿El comercial ve la mediana de su puesto o solo su evolución?** Propuesta: sí, como una línea de referencia sin nombres; el Head of Sales puede desactivarla.
3. **¿MdV tiene un proceso escrito?** Decide si el primer camino es importar o el cuestionario. **Pendiente**: preguntarlo a Gonzalo.
4. **¿Cómo se reparten SDR y AE en MdV?** **Pendiente.**
5. **¿`interactions` es una tabla nueva o columnas en `memos`?** Se decide en la spec de F0.
6. **Proveedor de email** para los mensajes. Verificar qué hay en `getvocify`.

---

## Anexo · Qué tomamos de cada competidor

| De | Tomamos | Evitamos |
|---|---|---|
| **Winn** | El playbook del cliente como checklist que se sigue de verdad (Deel: +31 % de adherencia a MEDDICC) · plantillas de metodología | Coaching en vivo como apuesta principal; les falta el análisis post-llamada, que es nuestro hueco |
| **Siro** | Feedback con minuto exacto · ejemplos de compañeros por objeción (−50 % de onboarding) · −90 % de tiempo de revisión del manager | Leaderboard · un "playbook builder" que nadie usa |
| **Attention** | Enlazar cada observación a su minuto | Scoring solo en pantalla y no exportable · un "tiempo real" que en realidad no lo es |
| **Sybill** | Extraer la metodología (MEDDPICC, BANT…) hacia campos del CRM | IA emocional (AI Act) · clips para el manager sin una acción concreta |
| **Piper** | Tipos de reunión (discovery, demo, cierre) | Escribir en el CRM sin aprobación |

**Lo que no documenta ninguno** y es nuestra apuesta:
- evaluación **paso a paso contra el proceso propio del cliente**, distinguiendo "flojo" de "no hecho" de "no se llegó";
- **mensaje diario y semanal con un único foco**;
- proceso creado por **cuestionario** para quien no tiene uno;
- coaching distinto para **SDR y AE**;
- separar **fallo del comercial** de **fallo del proceso**.
