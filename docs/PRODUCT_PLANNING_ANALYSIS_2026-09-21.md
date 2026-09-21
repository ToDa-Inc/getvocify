# Análisis Estructurado — Sesión de Product Planning Vocify (21 Sep)

> Documento derivado de `[product_planing.md](../product_planing.md)`, la transcripción cruda de la call entre Dani y su partner. Este documento **no añade información nueva**: reorganiza, interconecta y etiqueta (V1/V2, painkiller/nice-to-have, dentro/fuera de dominio) lo que ya se razonó y decidió en la conversación. Donde la transcripción quedó ambigua o sin cerrar, se marca explícitamente como tal en vez de asumir una conclusión.

---

## 1. Principios rectores (el "por qué" detrás de cada decisión)

Estos principios aparecen repetidos en distintos puntos de la call y funcionan como el filtro con el que se aceptó o descartó cada feature. Se listan aquí primero porque son la lógica de fondo que explica el resto del documento.

1. **"No nos compliquemos más de la cuenta"** — frase repetida varias veces (organización del día, playbooks, meeting booked, dashboard). Es el criterio de simplicidad por defecto: ante duda entre una solución simple y una compleja, se elige la simple y se deja la complejidad para V2/V3.
2. **Minimizar el "AI slop"** — las tareas, resúmenes y sugerencias generadas por IA deben leerse como frases cortas y directas ("2 líneas", "bullet points", "sin mucho AI slop"), nunca como párrafos genéricos de IA.
3. **Proactivo > reactivo, pero resuelto con un gesto, no con un formulario** — ejemplo ancla: en vez de que el comercial busque "a quién llamar", Vocify le presenta un botón con contexto ya resuelto ("Marina pidió que la llamaras en 2 semanas, han pasado 12 días, llamar ahora"). Este es el patrón de referencia para todas las "tareas inteligentes" (ver §3.3).
4. **Determinismo donde se pueda, IA acotada (constrained) donde no** — tensión que aparece varias veces (clasificación de objeciones, detección de meeting booked). La resolución práctica que se adopta es un híbrido: LLM + framework de clasificación tipo Jev.ai para forzar outputs cerrados (booleans/multiselect) en vez de dejar que el LLM razone libremente sobre datos operativos (ver §6.4 y §5).
5. **Dominio del producto = quitar carga administrativa y dar visibilidad de performance, no enseñar a vender ni sustituir el CRM.** El coaching estandariza la adherencia a un proceso que la empresa ya tiene, no enseña ventas desde cero (ver §4.1). El reporting de equipo existe para dar visibilidad, no para competir con los reportes nativos de HubSpot.
6. **ICP asumido: empresas que ya usan un CRM estructurado (HubSpot o Pipedrive) con 2-way email sync nativo.** Cualquier feature que solo tenga sentido para empresas sin CRM o con setups "artesanales" se descarta explícitamente por bajo ROI (ver §6.2 y §6.3).
7. **Construcción feature por feature, no las 20 a la vez.** Decisión explícita para la ejecución post-call: cada feature se construye, revisa y cierra antes de pasar a la siguiente, para evitar que "las primeras 2 salgan de puta madre y las últimas hechas con el culo" (ver §9).



- TODO ESTO TIENE QUE ESTAR INTERRELACIONADO Y TENER COHERENCIA CON CODIGO NUEVO, CODIGO EXISTENTE, PATTERNS YA UTILIZADOS Y NECESIDAD DE INTEGRACION NUEVA.

---



## 2. Pilar A — Reporting / captura de información

Definido como la base de datos de entrada: toda la información de interacciones comerciales que el sistema necesita capturar.

- **Fuentes de captura acordadas:**
  - Llamadas en frío (cold calling) — **ya se graba bien**, sin cambios.
  - Meetings online / warm calling — **ya se graba** con la app de escritorio (getvocify-desktop app). Revisar repo de vocify-desktop para ver exactamente el punto de imrpoval donde se neceste mejorar el styling
  - Visitas presenciales de comerciales de campo — captura vía **chat de WhatsApp** (grabación de audio).
- **Decisión:** no se añade ninguna fuente nueva de captura. El único cambio pendiente es **añadir la desktop app / extensión ("botless")** al flujo existente — considerado trabajo ya resuelto, "esto ya está bien incluso como lo tenemos".
- **Conclusión del pilar:** 100% de acuerdo, cerrado sin debate ("Estoy de acuerdo ahí, 100% de acuerdo").

Este pilar es la base física sobre la que corren todos los módulos de inteligencia (Ask Vocify, coaching, dashboard): sin esta captura no hay datos que orquestar ni que puntuar. Eso hace que el pilar principal de "CAPTURAR" la informacion cumpla su punto.

---



## 3. Pilar B — Quitar tareas administrativas al comercial

Framing inicial: *"¿Qué hacen los comerciales en el día a día que no es vender?"* — Se listó explícitamente:


| Tarea administrativa del comercial                            | Estado                                                            |
| ------------------------------------------------------------- | ----------------------------------------------------------------- |
| Actualizar el CRM                                             | Ya se hace                                                        |
| Enviar mails de follow-up                                     | NECESITAMOS IMPLEMENTARLO                                         |
| Prepararse para la llamada (resumen de contexto previo)       | NECESITAMOS IMPLEMENTARLO                                         |
| Prepararse para el meeting                                    | NECESITAMOS IMPLEMENTARLO                                         |
| Organizarse el día (a quién llamar / a quién hacer follow-up) | Ver lógica de priorización (§3.1)                                 |
| Revisar el mail (quién contestó, quién no)                    | Debate largo — ver §3.4, decisión final: NO construir capa propia |




### 3.1 Lógica de priorización de a quién llamar

Framing explícito (metáfora de las "manzanas bajas" / low hanging fruit):

1. **Tier 1 — "low hanging fruit":** leads con pain confirmado en llamadas recientes (p. ej. la semana pasada) que no llegaron a cuadrar demo, estaban liados, o no se pudo cerrar en su momento. Contactos ya "estucados" (calentados) que requieren poco esfuerzo ("no tienes que tener mucha fuerza para coger esas manzanas").
2. **Tier 2 — contactos no llamados.**
3. No se organiza por franja horaria estricta salvo que el lead haya pedido explícitamente una hora concreta; se prioriza por "lo más hot que puedas llamar".

Esta misma lógica de intelligence se aplica igual a nivel de **deals**: conversaciones de la semana pasada (ejemplo citado: "UE Solutions") se tratan con la misma regla de priorización.   
  
IMPORTANTE: SE PRECISA DE UN SITIO EN LA UI DASHBOARD DONDE ESTO PUEDA TENER SENTIDO PARA IMPLEMENTAR

### 3.2 El orquestador de inteligencia

Concepto técnico central identificado en la call: un **orquestador** — un LLM "más inteligente" por encima de las piezas individuales, capaz de:

- Orquestar tanto tareas creadas manualmente como tareas detectadas automáticamente.
- Analizar todas las fuentes conectadas (llamadas, CRM, calendario, mails) y decidir qué hace falta hacer.

**Referencia de inspiración citada:** el partner ya había construido algo similar con su propio setup de Claude, conectando Fathom + HubSpot + otras fuentes para que le dijera "no le has enviado el mail a este" / "tienes que volver a llamar a este". Vocify quiere ir un nivel más allá en inteligencia de orquestación, no solo replicar ese patrón.  Se puede utilizar un llm al estilo deepseek-v4.1-flash o gemini-3.8-flash para esta tarea

**Comparable de producto citado:** Sin Ask AI / "el Wizard" — un asistente que además de ejecutar, **notifica proactivamente** ("tienes tantos mensajes", "Google Calendar conectado pero no ha entrado ningún lead") - SIMILAR EN COMO TENEMOS SIGNALCORE-BACKEND.

**Consecuencia de diseño acordada:** cada día, como mínimo, debe aparecer un listado de tareas imprescindibles — mezclando tareas creadas manualmente **y** tareas detectadas automáticamente por el sistema (ver ejemplo en §3.3). Formato: "moderno", visual, no un listado de tareas clásico de CRM.

### 3.3 Tareas inteligentes vs. tareas genéricas

Distinción explícita y repetida como principio de diseño (ver también §1.3):

- **Tarea genérica (a evitar):** "Llamar a Marina" — sin contexto, indistinguible de cualquier tarea de cualquier CRM, "no enseña nada".
- **Tarea inteligente (objetivo):** contexto + gatillo temporal + acción de un solo gesto. Ejemplo textual de la call: *"Marina pidió que la llamaras en 2 semanas tras dudar por el precio, y ya han pasado 12 días → botón 'Llamar ahora' → te reproduce el voicemail/contexto y te redirige a HubSpot/CRM que ngas/llamas desde vocify ahi mismo" . igual añadir algun hook o algo.*

**Problema identificado que motiva esta feature:** hoy en HubSpot (o cualquier CRM) se crea la tarea "enviar mail de follow-up", pero **nunca se crea la tarea de segundo orden** ("si no me contesta en 10 días, volver a llamar"). Esa tarea de seguimiento condicional simplemente no existe hoy — es el hueco que Vocify llena - pero mas importante es el contexto de la tarea, el porque esta esa tarea y como se abre, hacer que las tareas esten prompteadas de mejor forma.

### 3.4 Debate: sincronización de email (decisión con razonamiento explícito)

Punto que el partner abrió como "el melón del mail" — propuesta inicial: que Vocify se conecte directamente a Gmail/inbox del comercial para detectar quién contestó, a quién hay que hacer follow-up, etc.

**Contraargumento de Dani (que termina ganando el debate):**

- Si el CRM (HubSpot o Pipedrive) ya tiene **2-way email sync** activado, los mails —tanto entrantes como salientes, vía extensión de Gmail/Outlook— **ya se guardan en el CRM** automáticamente, asociados al contacto.
- Confirmado explícitamente para ambos CRMs: HubSpot (usado antes por Dani) y Pipedrive (verificado: "You connect external inbox, Gmail or Outlook, to log inbound and outbound messages automatically on contact timelines").
- Por tanto, Vocify no necesita una integración propia: basta un **GET de la activity del contacto** en el CRM.
- Mismo patrón que ya se usa con grabadoras externas tipo AirCall: "si ya lo graban con AirCall, bien por ellos, nosotros la data la conseguimos de todas formas" — Vocify se apoya en lo que el CRM ya centraliza, no duplica infraestructura.

**Resolución final (explícita, con cálculo de costo/beneficio):**

- Conectar Gmail directamente vía API/MCP propio requiere **verificación pública de Google** (OAuth), que Dani estima como una inversión de desarrollo no trivial ("no es tan sencillo... lo más seguro hay una forma sencilla, pero estoy casi convencido [de que no]") - se puede anotar en el codigo como nice to have para mas adelante. LA SOLUCION ES QUE ESTO SE EVITE POR AHORA.
- Comparado contra el tamaño de ese sub-segmento de clientes (los que NO tienen CRM con sync nativo), la conclusión es: **"no es nuestro ICP al 100%"** — se decide **no construir la integración directa de Gmail**, y depender del 2-way sync nativo de HubSpot/Pipedrive como fuente de verdad para emails. Ver también §6.2 (Composio) y §6.3 (ICP) — es la misma lógica de costo/inversión aplicada tres veces en la call.  
  


---



## 4. Coaching



### 4.1 Filosofía central del coaching (framing explícito)

Citando directamente la lógica argumentada: el head of sales / director comercial normalmente **ya sabe vender** — tiene experiencia, conoce el producto, conoce el ICP. El coaching de Vocify **no enseña a vender desde cero**. Su función es:

1. **Estandarizar** el proceso de venta que la empresa ya tiene (vía cuestionario al head of sales / playbook existente).
2. **Medir cuánto se desvía cada comercial** de ese marco ya definido.
3. Señalar la desviación ("te estás saliendo del marco, aquí tienes que hacer esto") — **no** enseñar el "cómo" genérico de vender.
4. Si una empresa decide explícitamente que "cada uno venda como quiera", esa adherencia (o no-adherencia) también es medible como dato.

**Caso de uso ancla citado para justificar esto:** SDRs tienen mucha rotación (dato aportado: "no dura más de un año normalmente") y son mayoritariamente junior → el coaching diario de refuerzo (qué hiciste bien/mal en la apertura, en la cualificación) tiene especial valor ahí porque compensa la falta de experiencia y la alta rotación - EL DISPLAY SERÍA TANTO EN UN APARTADO PARA ELLO, COMO AFTER CALL O AFTER MEETING (HAY QUE VERLO Y SABERLO CON EXACTITUD)

### 4.2 Playbooks por tipología de interacción

Decisión de estructura: playbooks segmentados por tipo de interacción comercial, no un playbook único. Tipologías identificadas: cold calling, llamada de cualificación, discovery, cierre, y posiblemente visita presencial — "3, 4 tipos de interacciones comerciales principales".

Cada playbook incluye: objeciones esperadas y cómo gestionarlas, preguntas que se deben hacer, criterios de qué es una "buena propuesta de valor" para ese tipo de interacción.

### 4.3 Onboarding del playbook — decisión sobre el "self-serve" (con rechazo explícito de una alternativa)

**Decisión final adoptada (self-serve simple):** el director comercial, en su propio onboarding, puede aportar el playbook por **cualquiera de estas vías**, todas manuales/self-serve (no conducidas por IA):

- Escribirlo directamente en un panel de configuración (Settings).
- Subir un PDF.
- Grabarse un audio o hacer un meeting grabado explicando su proceso (referencia técnica: la misma capacidad de grabación con audio)

Este apartado en Settings debe ser **de configuración muy sencilla** para el sales manager - para la parte de admin. Donde los playbooks de referencia despues se utilicen como prompts para el LLM.

### 4.4 Scoring

**Framing del scoring (analogía explícita):** "un scoring es una forma simple de anotar un examen" — sirve como referencia relativa (esta llamada fue mejor/peor que la anterior), no como verdad absoluta. Ejemplos dados en la call: 9.5/10 vs. 7/10 en llamadas de la semana pasada.

**Objeción principal planteada (del partner) y respuesta:**

- Riesgo: el scoring puede fallar en distinguir una llamada "fácil" (lead ya convencido, agenda demo en 1.5 minutos) de una llamada realmente bien trabajada (hubo objeciones reales y se rebatieron bien). Ejemplo textual: el prospecto "buenorro" que agenda rápido no debería puntuar más alto que una llamada donde de verdad se batalló.
- **Criterio de "buena llamada" acordado explícitamente:** una llamada donde **hubo objeciones (no obstáculos)** y se rebatieron correctamente — se marca la distinción conceptual entre "obstáculo" y "objeción" como relevante para el criterio de scoring. SE PODRIA PERMITIR AL HEAD OF SALES DETERMINAR QUE ES UNA BUENA LLAMADA/VISITA/DEMO
- **Resolución de la discusión:** en vez de bloquear la feature por este edge case, se decide tratarlo como trabajo de prompting ("acabas de encontrar un edge case, vamos a hacer que el LLM encuentre diferentes edge cases para el mismo caso") — el scoring se construye igual, y los edge cases se van resolviendo vía prompt engineering, no se rediseña el approach. EL LLM NECESITA PROMPTEAR DE FORMA CORRECTA PARA QUE EL SCORING SEA REALMENTE EFICIENTE EN BASE A PARAMETROS NECESARIOS.
- Dani defiende explícitamente que la inversión de construir el scoring es "rapidísima, muy muy fácil" comparado con su valor de referencia.



### 4.5 Detección y clasificación de objeciones

- Se marca como **importante** y "metido con lo otro" (conectado a scoring y coaching).
- Se separa conceptualmente en dos usos distintos:
  1. **Clasificación estructurada** (para reporting/analítica): tipo de objeción (precio, tiempo, etc.), si es obstáculo real u objeción — tratado como **datos booleanos/multiselect**. Para esto se decide usar un **híbrido LLM + Jev.ai** (framework de clasificación con outputs forzados/acotados — ver §6.4) - ESTE PATTERN SE PUEDE UTILIZAR EN VARIOS SITIOS PARA CONSEGUIR ESTE RESULTADO DONDE SE PRECISE UN MODELO HIBRIDO DE LLM + CLASSIFIER (JEV ([https://openrouter.ai/typesafe/jev-1.13](https://openrouter.ai/typesafe/jev-1.13)))
  2. **Análisis para coaching** (leer entre líneas): aquí se necesita un LLM que entienda **contexto e ironía** — ejemplo citado: si un prospecto dice "qué barato" con tono irónico, el sistema no debe tomarlo literal. Se reconoce el riesgo (Andrés lo planteó en una reunión anterior) y se decide que el LLM de coaching debe estar optimizado para esta lectura contextual, distinto del clasificador determinista de (1).
- **Feature explícitamente descartada por poco fiable:** detección de **tono/emoción real** (p. ej. si el prospecto responde cortante o distante) a partir de la transcripción. Razón: las transcripciones no son 100% accurate, y detectar emociones reales desde texto se considera "un edge case complicado de resolver" sin garantía de que se pueda hacer bien hoy. **Se deja fuera de scope** — "no hay que ir más allá".
- **Solución adoptada en su lugar (ya resuelta y validada, sin complicarse más):** notas manuales en tiempo real durante la llamada (mismo patrón que Granola) — el comercial anota manualmente un matiz relevante (p. ej. "ha dicho que es barato irónicamente") y esa nota se asocia a la transcripción en ese instante exacto. Esto resuelve el caso concreto que Andrés había pedido sin necesitar sentiment analysis real. ES DECIR, QUE EL HUMANO PUEDE ANOTAR DURANTE LA INTERACCION (DEBERIA DE HABER UNA FORMA EN LA UI DE PODER FACILITAR ESO PARA HACERLO)



### 4.6 Brief post-interacción

- Contenido: qué se hizo bien, qué mejorar, con highlights de la llamada.
- **Timing: NO instantáneo / no forzado en tiempo real.** Corre como **background job**; el comercial lo revisa cuando quiere (después de la llamada, al final del día, etc.).
- **Razón explícita:** no interrumpir el ritmo de llamadas del comercial ("uno quiere estar ahí pam pam pam llamando") ni perder tiempo de la extracción/actualización de campos que ya corre en background.
- Comparable de producto citado: Granola, que graba y entrega el email de follow-up listo para enviar, con notas y campos actualizados automáticamente - o al menos la propuesta de ello.



### 4.7 Checklist en vivo durante el meeting (solo meetings, no cold calls)

- Formato acordado: checklist con auto-check (apertura, presentación/pitch, objection handling, cualificación) que se marca **automáticamente** cuando el sistema detecta que el comercial ya lo hizo — **no** un botón manual que el comercial tenga que apretar.
- **Razón explícita para descartar el check manual en cold calling:** las llamadas en frío son demasiado rápidas — "dudo mucho que en 3 minutos tengas energía mental para apretar un botón".
- **Alcance decidido:** esta feature es **solo para meetings** (vía desktop app / extensión), **no para SDRs en cold calling** en esta fase — motivo técnico: los SDRs graban solo con la extensión, y la extensión hoy no permite este nivel de feedback en vivo. **Explícitamente V2** para SDRs, guardando el mismo concepto/código para cuando se habilite.



### 4.8 Tarjeta de objection handling en tiempo real (real-time assist) - util para desktop APP 

- Concepto: durante el meeting, si el comercial quiere ayuda puntual (p. ej. objeción de presupuesto), puede pedir asistencia y aparece una "tarjetita" con una sugerencia de respuesta adaptada al coaching/playbook configurado — **no automática/forzada, es opcional** ("existencia de IA  real time... pero por eso, opcional").
- Mismo criterio de "sin AI slop": la sugerencia debe ser corta y directa, no un párrafo genérico de IA.
- **Alcance:** solo meetings en esta fase (mismo motivo técnico que §4.7 — límite de la extensión para cold calling). Para SDR/cold calling queda explícitamente en el roadmap para "un futuro no tan lejano" / V2, guardando el código ya pensado - y como se veria en la extensión



### 4.9 Roleplay con IA y coaching en vivo durante la llamada — diferidos

- **Roleplay con IA:** explícitamente descartado para esta fase ("no es mala idea, pero maybe not now"). V2/V3.
- **Coaching en vivo durante la llamada** (feedback en tiempo real mientras se habla, más allá de la tarjeta puntual de §4.8): ya está parcialmente construido en la app actual (la única que graba en vivo en el momento), pero se decide **dejarlo en beta/mínimo** por ahora y no invertir más ("ni tocarlo ahora"), reservando expansión para V2.



### 4.10 Reporting diario/semanal al rep (con evolución)

- **Prioridad: 100%, cerrado sin debate.**
- Formato: email al rep individual y al admin, con: qué hizo bien/mal, número de llamadas, número de cierres, objeción más común y cómo debió rebatirla, adherencia al proceso de venta (en cuántas se dejó la cualificación, en cuántas no se abrió bien, etc.).
- Incluye métricas de progreso en el tiempo (cómo ha ido mejorando) y **highlights** ("en este minuto lo hiciste así de bien") — con función explícita de motivar al comercial, no solo reportar - nice to have.
- Canal preferido: **email** — decisión explícita, con referencia de producto: Piper AI reporta así. Complementado con un icono de campana/notificación dentro del dashboard (referencia de producto propia: tool ya construida en SignalCore con el mismo patrón) - ahi se puede indicar cual es la actividad que se realizó, porqué, etc...
- Se identifica como relacionado con el módulo de **coaching diario** que el partner pedía para dar feedback — mismo mecanismo, doble propósito (reporting + coaching).

---



## 5. El debate central: detección de "Meeting Booked" (determinismo vs. IA)

Este fue el punto de mayor fricción y el más largo de la call — vale la pena documentarlo como caso de estudio de cómo se resuelven desacuerdos en el equipo.

**Postura inicial de Dani (en contra de que la IA marque el meeting booked):**

- Mover un deal a "meeting booked" es tradicionalmente una **acción determinista y manual** que hace el propio comercial en el CRM.
- Que Vocify tome esa responsabilidad de forma automática introduce riesgo: si la IA falla en detectar correctamente si hubo o no un meeting agendado, Vocify se hace responsable de un error en un dato que antes era 100% fiable por ser manual.
- Además, **detectar el "estado" de un deal es altamente personalizable por CRM/empresa** (cada uno define "meeting booked" distinto, usa Calendly, invite de calendario, line items, etc.) — construir detección genérica para esto implica muchos edge cases no mapeados.
- Preferencia explícita: enfocar a Vocify en **extraer inteligencia de la conversación**, no en ejecutar acciones directas/deterministas sobre el CRM.
- Referencia de dolor pasado citada: en BookedIn, Dani implementó algo similar (IA re-llamando automáticamente a la hora indicada) y "iba como el culo siempre".

**Postura del partner (a favor de que Vocify sí lo detecte y lo mueva):**

- La premisa de Vocify **es** quitarle esa carga manual al comercial — "toda la vida tú también estás tomando notas... pero para eso estamos haciendo Voiceify". No hacerlo contradice la propuesta de valor central.
- La detección **no es subjetiva**: si en la llamada se acuerda verbalmente "quedamos el martes a las 5 para el meeting", eso es, por definición, un meeting agendado — es un hecho verbal claro, no una inferencia ambigua.
- Ya existe una tarea equivalente y aceptada: el sistema ya detecta cuándo hay que enviar un mail de seguimiento a partir del contexto de la conversación — el mismo tipo de detección aplica aquí.
- El "meeting booked" es, además, un **KPI crítico** para el head of sales (cuántos meetings se está dejando cada comercial) — no reportarlo bien tiene coste real para el cliente.

**Resolución (Dani cede explícitamente, con "first principles"):**

- Se acuerda que la IA **sí debe** detectar cuándo hubo un meeting agendado verbalmente durante la llamada, como un booleano.
- Se distingue explícitamente **"agreement"/meeting booked** (compromiso verbal de reunión) de **"close"** (cuando el cliente paga) — Vocify puede detectar lo primero, no lo segundo (el close no es detectable por Vocify, requiere info de facturación externa).
- Requisito de calidad explícito: la **fecha y hora exactas** del meeting deben capturarse correctamente (tomando la hora que ambas partes confirman), porque se identificaron casos reales donde la transcripción capturó mal la fecha.
- **First principle articulado para cerrar el debate:** el propósito de fondo es (a) dar visibilidad de performance al equipo/head of sales, y (b) que Vocify —como parte de su responsabilidad central, no como extra— sea quien traslada correctamente esa información al CRM. "Somos los encargados de pasar toda la información al CRM."
- Nota de alcance que sobrevive del argumento de Dani: para el brief/reporting final, los datos priorizados son **meetings agendados, llamadas conectadas, objeciones más comunes y por qué las mejores llamadas fueron las mejores** — se mantiene disciplina de no intentar detectar *todos* los estados posibles de deal (eso sigue siendo demasiado personalizable por CRM), solo este conjunto acotado.  
  
PIENSA QUE TODO ESTE RAZONAMIENTO PARA SABER SI METER UN CLASSIFIER O NO SIGNIFICA QUE TIENE QUE SER HECHO BIEN Y ESTAR BIEN EMBEBIDO EN EL WORKFLOW DE LA MEJOR FORMA POSIBLE.

Este debate se conecta directamente con §6.4 (Jev.ai como framework de clasificación acotada) — la resolución técnica al problema de "cómo detectar esto sin que sea un riesgo" es la misma herramienta de clasificación con outputs forzados, no un LLM razonando libremente.

---



## 6. Arquitectura técnica



### 6.1 Ask Vocify / "el Wizard" 

- Es la interfaz conversacional central del producto — mismo concepto, tres superficies distintas que comparten la misma lógica de fondo ("yo lo pasaría por una misma ruta, un mismo funcionamiento"):
  1. Chat dentro del dashboard de Vocify.
  2. Conversación por WhatsApp (bidireccional: se le puede preguntar y responde)
  3. La feature ya existente de "grabar audio" en la landing/extensión — se señala que hoy es **solo de ida** (registra lo que pasó) y se plantea evolucionarla también hacia bidireccional, como WhatsApp.

- **Valor diferencial que se busca:** que el sistema pueda decir proactivamente a quién llamar hoy, por qué es prioritario, qué pasó en las últimas llamadas, qué objeción se repitió y por qué. ES UN LLM CONVERSACIONAL CAPAZ DE HACER TOOL CALLS, LLAMAR A MCP, TENER CONTEXTO DE CONTACTOS/DEALS, ETC... DE LO QUE SUCEDE EN HUBSPOT Y ES CAPAZ DE HACER ACCIONES EN BASE A LO QUE SE INDIQUE DE FORMA INTELIGENTE.  
  
estilo parecido al wizard de signalcore-backend (peudes revisar la repo)



### 6.2 Modelo LLM y conectividad (MCP vs API directa)

- Modelos candidatos para el motor conversacional: **Gemini 3.8 Flash** o **DeepSeek 4.1 Flash**  o Jev (donde se necesita classification) — elegidos por ser rápidos y baratos 
- **Decisión de conectividad importante:** el acceso a HubSpot debe ser vía **MCP de HubSpot**, no vía API directa — para que el LLM pueda hacer retrieve inteligente de deals, tasks, notas, activities, companies dentro del scope ya autorizado. REVISAR SI ESTO ES RELEVANTE O NO (IGUAL POR API/CLI YA ESTA BIEN)
- **RAG/sistema vectorial:** contemplado como posible mejora "en caso de que escale", pero **no se considera necesario ahora** — razón dada: las preguntas típicas de los usuarios no son tan abiertas/agregadas como para requerir retrieval a gran escala.



### 6.4 Jev.ai — framework de clasificación híbrida

- Framework LLM + reglas para forzar **outputs acotados** (boolean / multiselect) en vez de dejar que el modelo razone en abierto sobre un dato operativo.
- Analogía explícita usada en la call: como clasificar el color de mil imágenes dándole solo 3 opciones válidas (azul/rojo/verde) — el modelo solo puede responder dentro del set permitido.
- **Casos de uso identificados para Jev.ai dentro de Vocify:**
  - Clasificación de tipo de objeción (precio, tiempo, obstáculo vs. objeción real).
  - Detección booleana de "meeting booked" (ver §5) — este es el mecanismo técnico concreto que resuelve el debate de determinismo.
  - Identificación de qué CRM usa un lead/cliente (ejemplo dado en la propia call sobre uso interno: "¿qué CRM utiliza? HubSpot, Zoho... únicamente tiene estas opciones").
- **Beneficio explícito señalado:** abarata costos frente a dejar razonar libremente a un LLM grande para tareas que en realidad son de clasificación cerrada.



### 6.5 Infraestructura de datos y reporting

- Los datos para el dashboard de equipo (head of sales) se sirven desde **Supabase** propio — "fetch de nuestro propio [almacén] para poder desplegar esa data".
- Se reconoce que el scope actual de acceso a HubSpot cubre deals, objetos, line items, "algunas cosas más", y que **puede necesitar expandirse ligeramente** para cubrir todo lo que el Copilot/Ask Vocify necesita leer (p. ej. contexto de por qué un deal se cerró ganado o perdido).

---



## 7. Head of Sales / Dashboard de equipo



### 7.1 Filosofía de diseño del dashboard (principio explícito, aplica a todo el dashboard, no solo a esta sección)

> "Partiría de la premisa de lo más, lo menor que se pueda reducir en cuanto a tabs, botones y cosas que apretar, mejor. Y únicamente que tú quieras más cosas cuando las busques... como en settings. - QUE TENGAS LA MAYOR CANTIDAD DE  VALUE CON LA MENOR CUANTIDAD DE INFO DE LA FORMA MAS INTUITIVA Y SENCILLA"

Desarrollado más adelante como principio unificado:

- Máxima cantidad de valor/datos con la mínima cantidad de botones, palabras, imágenes y pantallas.
- La IA hace, el usuario aprieta poco y ve mucho.
- UI con **progressive disclosure**: lo importante siempre visible, el resto se expande bajo demanda ("¿quieres ver más? aprietas para expandir").
- Ordenar cada elemento de la UI por relevancia tanto para el comercial (usuario principal) como para el director de ventas.
- Se reconoce que la parte "difícil" no es la lógica de negocio (esa "la saca Claude en segundos"), sino lograr que el dashboard final **se vea bien y sea claro** — la dificultad percibida está en diseño visual, no en el algoritmo.



### 7.2 Features de equipo — incluidas (V1)


| Feature                                                                                    | Nota de alcance                                                                                          |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Dashboard de equipo: quién vende más/menos, por qué (actividad, calidad, resultado)        | V1, necesario                                                                                            |
| Panel de objeciones de equipo (cuáles se repiten, quién las supera, cuáles cuestan ventas) | Fácil y necesario; se conecta con la detección de objeciones de §4.5                                     |
| Detección de menciones de competidores y qué prometen                                      | Validado como caso real (ejemplo: detección recurrente de "Ringover" en llamadas) — dentro de dominio    |
| Reportes programados diarios/semanales al manager (email, Slack)                           | 100%; misma infraestructura que el reporting individual (§4.10), con analíticas a nivel equipo           |
| Manager Chat (Ask AI a nivel equipo)                                                       | Mismo motor que Ask Vocify (§6.1), con scope de datos ampliado a todo el equipo según permisos de cuenta |
| Win-loss insights (patrones de deals ganados vs. perdidos)                                 | Se identifica como parte del mismo "gran esquema" interconectado, no una feature aislada                 |
| Métrica de adherencia al método (playbook adherence)                                       | Ver §7.4 — marcada como especialmente importante                                                         |




### 7.3 Features de equipo — explícitamente descartadas o fuera de dominio

- **Notificaciones por WhatsApp para el equipo:** técnicamente no se puede sin el "plan 10" de Meta para envío. Calificado como **nice-to-have, no painkiller** — descartado para esta fase.
- **Análisis de competidores como categoría de mercado (más allá de detectar menciones en conversación) -** se diferencia de la detección de menciones dentro de una llamada (que sí está en dominio).



### 7.4 Métrica clave: adherencia al método (playbook adherence)

Marcada explícitamente como una de las conclusiones más fuertes de toda la sesión EN CUANTO A INFO PARA EL MANAGER:

- Definición: % del equipo que sigue el playbook definido por el manager, y su evolución en el tiempo.
- **Validación externa citada:** aparece mencionada en dos de los reviews más valorados de la categoría (Winn.ai) — referencia textual: *"Playbook adherence: del 40% pasó a más del 70%"*.
- Se conecta directamente con conversaciones previas del equipo (referencia a feedback ya recibido: *"los comerciales no se están adhiriendo muy bien a como yo estoy queriendo explicar y vender"*) - ESTO SE INTERCONECTA CON LOS PLAYBOOKS, OBJECTIONS E INTELLIGENCE.
- Framing de negocio: esta es la métrica que el head of sales reporta hacia arriba a su propio jefe — por tanto tiene valor no solo operativo sino también como argumento de venta/retención de Vocify.
- Se conecta con **frameworks configurables por el manager** (el manager define qué es una "buena llamada") — este framework configurable se deja como parte menor/opcional del dashboard ("si me lo metes ahí que no vale mucho, perfecto"), no como una feature de peso propio.



### 7.5 V2/V3 explícito para el dashboard

- **Dashboard 100% personalizado por el head of sales vía chat:** el manager pide en lenguaje natural ("quiero saber esto") y el sistema genera y **pinea** una tabla/widget al dashboard persistente. Explícitamente deseado por el partner ("me encantaría muchísimo") pero clasificado como V2/V3, no V1 — "de momento con el chat que hay, ya está bien".
- **Leaderboards del equipo:** calificado como necesario/innecesario dependiendo puramente de qué tan bien quede integrado visualmente — no es una decisión de producto firme, queda supeditado al diseño visual final del dashboard.  
  
  
ES DE MOMENTO ESTO PARA AÑADIR COMO NOTAS, NADA DE ROADMAP PARA AHORA.

---



## 8. Notificaciones y canales


| Canal                                       | Estado                                                                     | Nota                                                                                                         |
| ------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Email (individual y manager)                | **Prioridad 100%**, canal principal - implemenation con resend seguramente | Referencia de producto: Piper AI                                                                             |
| Slack / Teams (equipo)                      | NO HACER                                                                   | NO HACER                                                                                                     |
| Campanita/notificación dentro del dashboard | Se hace                                                                    | Referencia: tool ya construida en SignalCore con este patrón; se integra con el sistema de tareas proactivas |
| WhatsApp (equipo/notificaciones push)       | **No se puede hacer ahora**                                                | no hacer                                                                                                     |
| WhatsApp (conversacional, Ask Vocify)       | Sí se hace                                                                 | Esto es distinto de notificaciones push — es el chat bidireccional descrito en §6.1, ya viable               |


Nota de interconexión: el partner señala que el punto de "reporting + alertas" está relacionado con el **coaching**, porque el coaching también necesita repartir feedback — ambos flujos comparten el mismo mecanismo de entrega (email como canal principal, campana como canal secundario dentro del producto).

---



## 9. Roadmap resumido (V1 vs. V2/V3)



### V1 (esta fase, orden de ejecución: feature por feature, no en paralelo)

- Pilar A completo (captura), con desktop app añadida.
- Priorización de contactos a llamar (tiers) + orquestador de inteligencia.
- Tareas inteligentes proactivas (contexto + gesto único).
- Ask Vocify / Wizard: chat en dashboard, WhatsApp bidireccional, evolución de la feature de audio de la landing hacia bidireccional.
- Dependencia CRM (HubSpot/Pipedrive) para email vía 2-way sync nativo — sin integración propia de Gmail.
- Coaching: playbooks por tipología, onboarding self-serve (texto/PDF/audio, sin curso guiado por IA), scoring simple, clasificación de objeciones (híbrido LLM+Jev.ai) + notas manuales en tiempo real, brief post-interacción como background job configurable, checklist auto-check y tarjeta de objection handling en tiempo real **solo para meetings**.
- Reporting diario/semanal al rep (email + campana).
- Detección de "meeting booked" vía IA (boolean, con fecha/hora exacta), distinguido de "close".
- Dashboard de equipo (head of sales): performance, panel de objeciones, menciones de competidores, reportes programados, manager chat, win-loss insights, métrica de adherencia al playbook.
- Notificaciones Slack/Teams para equipo.



### V2 / V3 (explícitamente diferido)

- Checklist en vivo y tarjeta de objection handling en tiempo real para **SDRs / cold calling** (bloqueado hoy por límite técnico de la extensión).
- Roleplay con IA.
- Coaching en vivo durante la llamada, expansión más allá del beta actual.
- Tracking de skills en el tiempo / TTR de objeciones por rep (quedó sin definir del todo, "duda").
- Dashboard 100% personalizado por chat con widgets pineables.
- Leaderboards de equipo (condicionado a diseño visual).
- Notificaciones WhatsApp para equipo (bloqueado por Meta, no por decisión de producto).



### Descartado / fuera de dominio (no es roadmap, es decisión de no-hacer)

- Integración directa propia con Gmail (se usa el sync nativo del CRM en su lugar).
- Composio como base de integraciones masivas.
- Detección de tono/emoción real desde la transcripción.
- Análisis de mercado de competidores como categoría (más allá de detectar menciones puntuales en conversación).
- Curso guiado por IA para construir el playbook en onboarding.
- "Scorecards comparativas entre reps" tal como se propuso originalmente (nunca quedó claro qué era).

---



## 10. Naming

- Nombre de trabajo para el asistente conversacional: **"Ask AI"** (provisional, sin resolver del todo — se barajaron "Wizard", nombres humanos tipo los bots internos existentes: "Hugo" para debugging, "Marco" para marketing). Decisión explícita: quedarse con "Ask AI" por ahora y revisar naming más adelante con más originalidad — no es una decisión de producto, es un pendiente menor. EL CONCEPTO ES VIBE-SELLING.

---



## 11. Próximos pasos acordados al cierre de la call



1. Instrucción explícita al LLM para ese plan: **no tratar esto como "meter 20 features a la vez"** — cada feature debe planificarse y ejecutarse individualmente, en profundidad, antes de pasar a la siguiente (ver también §1.7). ESTO DEBE SEGUIR UN PROCESO ACOTADO, CON UN PLANNING DIRECTO, TENIENDO EN CUENTA LO QUE EXISTE, COMO SE INTERLAZA TODO. 

