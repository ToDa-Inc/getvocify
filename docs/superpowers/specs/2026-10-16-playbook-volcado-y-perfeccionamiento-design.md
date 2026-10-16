# Playbook de ventas: volcado asistido y perfeccionamiento con el uso

Fecha: 2026-10-16
Estado: implementado en `main` (commits de Toni, 16 oct 2026), apagado por flags y sin push. Falta activarlo: ver sección 13.
Plan de implementación: `docs/superpowers/plans/2026-10-16-playbook-volcado-y-perfeccionamiento.md`.

## 1. Objetivo

Que un Head of Sales o CEO llegue a Vocify, vuelque todo lo que sabe sobre cómo vende y sobre su producto, y
Vocify lo convierta en un playbook de ventas lo más detallado y preciso posible. Después, el playbook se
perfecciona con la práctica real. La meta de fondo es que lo que sabe el jefe llegue a otra persona en el
momento y la forma correctos. La entrega al comercial (la ayuda en directo) ya existe; este spec cubre solo el
lado del admin: cómo entra la información y cómo se mejoran las respuestas.

Criterio de éxito acordado:

- En la prueba inicial, el jefe aprueba sin cambios al menos el 80% de las respuestas de Vocify.
- En llamadas reales se mide la cobertura (cuántas objeciones y preguntas tienen respuesta aprobada) y el
  success rate de cada respuesta (sección 8.2).

## 2. Alcance

Dentro:

1. Volcar con ayuda: varios documentos, voz o texto; resumen de lo entendido; detección de huecos; preguntas de
   una en una; llamadas modelo.
2. La prueba: 10–12 casos en los que el jefe ve cómo respondería Vocify y lo corrige.
3. Perfeccionar con el uso: cola de casos reales, resumen semanal para el Head of Sales, cobertura y success
   rate.

Fuera, por decisión de Toni (no se hace en este trabajo):

- Cualquier cambio en la ayuda en directo: `turn.py`, `suggest.py`, `prompts.py`, `grounding.py`, los prompts
  `copilot_*` y el panel de la app de escritorio. Se llaman tal como son.
- Cualquier cambio en cómo funciona el coaching. Lo está haciendo Dani; ver sección 9.
- Casos de prueba con respuestas incorrectas o preguntas que el material no contesta.
- Botones o marcas del comercial sobre las tarjetas.
- "Ver ficha", el guardado de "te lo confirmo", el aviso al comercial cuando el jefe contesta y las preguntas
  probables en el brief previo.
- Leer una web por enlace, búsqueda por significado (embeddings) y analítica por comercial.
- Aprender la voz del jefe de forma automática de sus llamadas. Lo que sí entra son llamadas modelo que el jefe
  elige a propósito (sección 6.5).

## 3. Decisiones tomadas

| Decisión | Detalle |
|---|---|
| Sin motor nuevo | Todo lo que el jefe vuelca se guarda en el formato de playbook que la ayuda en directo ya lee. |
| Variantes de una objeción | Ramas dentro de la misma respuesta ("si es X…, si es Y…"), que el prompt en directo ya interpreta. |
| Preguntas técnicas del producto | Entradas propias del equipo (`custom`): pregunta y respuesta. |
| Cadencia de la revisión | Cola siempre disponible en Playbook y resumen semanal dentro del informe del Head of Sales. |
| Activar con menos del 80% | Permitido, con aviso. El 80% es una guía. |
| Quién lo dijo | La revisión no muestra quién lo dijo. Eso ya está en Equipo. |
| Tope por respuesta | Sube de 600 a 1.200 caracteres (editor y validación del servidor; no cambia el motor en directo). |
| Coaching | Fuera de este trabajo. Se coordina con Dani (sección 9). |
| Medida en llamadas reales | Success rate por respuesta, calculado sin intervención del comercial (sección 8.2). |
| Umbral de viabilidad del success rate | Acuerdo de al menos el 80% con las etiquetas de Toni y no más del 30% de "no se sabe" (sección 8.5). |
| Dónde se guarda una pregunta técnica nueva | En el tipo de llamada donde apareció. Sirve en todos por `with_company_answers`. |
| Veredictos del success rate | El jefe puede corregirlos desde el caso (sección 8.2). |

Glosario para no confundir dos números:

- **Aprobadas en la prueba**: de los casos de la prueba, los que el jefe aprueba sin cambiar. Solo existe en la
  fase 2.
- **Success rate**: en llamadas reales, de las veces que el comercial dijo la respuesta sugerida, cuántas
  resolvieron la objeción o la duda. Solo existe en la fase 3.

## 4. Recorrido del jefe

1. Primer día. Sube documentos, dicta o escribe. Vocify dice lo que ha entendido, pregunta lo que falta de una
   en una y acepta llamadas modelo. Después pasa la prueba y activa.
2. Cada semana. Recibe en el informe del Head of Sales las respuestas que peor funcionan, con los casos reales,
   y las corrige desde la cola. Las mejoras se publican juntas.

## 5. Qué se guarda y dónde

No hay almacén nuevo de conocimiento. Se usa lo que ya hay:

| Qué | Dónde | Límites actuales |
|---|---|---|
| Pasos del proceso | `steps` del playbook: `label`, `criterion`, `example` | `example` hasta 300 caracteres, 15 pasos |
| Respuesta a una objeción fija (precio, timing…) | `entries`, una por categoría | Respuesta hasta 1.200 caracteres, `trigger` hasta 200 |
| Variantes de esa objeción | Ramas dentro de la respuesta | Dentro de los 1.200 caracteres |
| Objeciones y preguntas técnicas propias | `entries` con categoría `custom`: `label` (60), `trigger` (200), respuesta | Hasta 200 por empresa |
| Datos de empresa | "Vuestra empresa" (`company_sales_knowledge`) | Sin cambios |

Hechos del código que condicionan el diseño:

- A la tarjeta en directo solo llegan de "Vuestra empresa" la frase de valor, 5 diferenciales, 3 casos y los
  competidores nombrados en la llamada, con tope de 2.400 caracteres (`format_company_knowledge`). El precio no
  llega: para que llegue tiene que ser una pregunta propia ("¿cuánto cuesta?"). El asistente lo hará así.
- Las respuestas de los demás tipos de llamada también se añaden a la tarjeta (`with_company_answers`), así que
  una pregunta técnica guardada en un tipo de llamada sirve en todos.
- El jefe es owner o admin y puede publicar. Lo que dicta él mismo cuenta como aprobado. Lo que Vocify extrae de
  un documento queda como propuesta con su frase de origen hasta que el jefe lo apruebe.
- Todo entra como borrador del playbook y se publica con el flujo existente. Las mejoras de la fase 3 se
  acumulan en el borrador y se publican por lotes, para no crear una versión por cambio.

Tablas nuevas (tres; nombres provisionales; el SQL de activación lo ejecuta el fundador en Supabase):

- `playbook_assistant_sessions`: estado del asistente de huecos para poder retomarlo.
- `playbook_review_moments`: la cola de casos, copiados del registro para que no se pierdan a los 90 días.
- `playbook_suggestion_outcomes`: veredicto de cada sugerencia (usada, resuelta) para el success rate.

## 6. Fase 1: volcar con ayuda

### 6.1 Entrada

El **guion de ventas** es el documento principal que se pide (todo equipo tiene uno): de él salen los pasos, sus ejemplos
reales y las respuestas a objeciones. Las llamadas modelo son un complemento, no un requisito.

La caja actual ([PlaybookStart.tsx](../../../src/features/playbooks/components/PlaybookStart.tsx)) acepta un solo
archivo. Pasa a aceptar varios, cada uno leído con el mismo `read_source` (texto, PDF, audio). Se añade el tipo
"llamada modelo" (6.5).

### 6.2 Resumen de lo entendido

Tras leer, una línea: "He entendido 3 tipos de llamada, 5 objeciones con respuesta, 14 preguntas del producto
y 2 casos de cliente". Cada dato extraído guarda la frase del documento de la que sale (`source_ref`). Se amplía
el procesado actual (`split_source` en `structure.py`, prompts `playbook_split_v2.md`) para que también extraiga
preguntas técnicas como entradas propias y ramas de objeciones.

### 6.3 Detección de huecos

Sin formulario fijo. Tres fuentes:

1. Temas típicos que casi siempre preguntan los clientes y el material no responde: precio y planes,
   integraciones, seguridad y datos, plazos de implantación, soporte, límites, contrato y renovación, quién
   decide, comparación con los competidores principales.
2. Objeciones y preguntas reales de las llamadas del equipo que no tienen respuesta aprobada. Se leen del
   registro de ayuda en directo (`live_assist_events`) y de las objeciones extraídas de las llamadas
   (`team_insights/objections.py`).
3. Contradicciones entre documentos: dos valores distintos para el mismo dato, como dos precios para el mismo
   plan.

### 6.4 Preguntas de una en una

Se ordenan por frecuencia real. El jefe contesta con voz, texto o un documento adjunto, o dice "lo respondo
luego". Tras cada respuesta, una línea con lo guardado y la opción de deshacer. Cada ronda son unas 10
preguntas. La sesión se guarda y se retoma donde se dejó. Una empresa sin llamadas empieza por la fuente 1.

### 6.5 Llamadas modelo

El jefe aporta transcripciones de llamadas donde se hizo bien en general, o donde se respondió bien una objeción
concreta, para que Vocify aprenda cómo se hace y en qué momento se aplica.

- **La llamada no se guarda.** Vocify la lee, propone y la descarta: no hay tabla de llamadas modelo y solo queda en el
  playbook lo que el jefe acepta (un ejemplo de paso, una rama de una respuesta). Por eso funciona aunque las tablas
  nuevas no estén activadas.
- Se aportan pegando o subiendo la transcripción, o eligiendo una llamada que Vocify ya tiene.
- El jefe indica si toda la llamada es un buen ejemplo o solo un momento, y opcionalmente por qué (voz o texto).
- Vocify propone, sin activar nada:
  - por cada paso bien hecho, un ejemplo real para el campo `example` del paso;
  - por cada objeción bien respondida, la respuesta y en qué momento funcionó (lo que el cliente había dicho
    antes), como rama de la respuesta.
- Cada propuesta se muestra con el trozo de la llamada y quién habla. El jefe confirma o edita. Esto es
  obligatorio porque las transcripciones pueden venir con los hablantes cambiados (en las pruebas del
  2026-09-30, 5 de 13 transcripciones eran malas).
- Si dos llamadas modelo se contradicen, se avisa.

## 7. Fase 2: la prueba

### 7.1 Casos

10–12 casos. Reales (objeciones y preguntas de llamadas del equipo) y sacados de los documentos del jefe. Si la
empresa no tiene llamadas, se usan solo los sacados de sus documentos y las objeciones típicas. Sin respuestas
incorrectas a propósito y sin preguntas que el material no contesta.

### 7.2 Cómo responde Vocify en la prueba

Con la ayuda en directo tal como es, pero alimentada con el borrador del jefe, sin publicar nada:

1. `read_turn(conversation, latest, custom)` de `turn.py`, con las entradas propias del borrador.
2. `stream_objection_suggestion(...)` de `suggest.py`, que ya recibe el playbook como parámetro
   (`grounding.playbook_snapshot`), junto con `company_knowledge` y `product_context`.
3. `finalize_suggest_result` de `grounding.py`.

Se verificó que estas funciones aceptan el playbook como argumento, así que no hay que tocarlas. El riesgo es que
nuestro orquestador se separe del endpoint real (`api/copilot.py`). Se cubre con un test que compara la salida de
los dos para el mismo playbook publicado, y con el simulador existente
([run.py](../../../backend/evals/copilot/run.py)).

### 7.3 Pantalla

Frase del cliente y, debajo, la tarjeta exacta que vería el comercial. Cuatro botones:

- **Vale**: la respuesta queda reforzada.
- **Yo diría…**: escribe o dicta su versión. Se guarda en el borrador, se relanza el caso y se prueba una frase
  parecida del cliente para ver si hace falta una rama.
- **No lo sé / sin respuesta**: el caso no tiene respuesta aprobada; el jefe la escribe.
- **Nunca digas esto**: se guarda dentro de la respuesta como "No digas: …".

### 7.4 Resultado

"9 de 12 aprobadas sin cambiar (75%)", con los temas flojos. Con menos de 3 casos se muestra el recuento, no el
porcentaje. Si queda por debajo del 80%, Vocify propone una ronda corta sobre esos temas. Activar publica el
borrador con el flujo existente. Por debajo del 80% se permite, con aviso.

## 8. Fase 3: perfeccionar con el uso

### 8.1 Cobertura

De las objeciones y preguntas detectadas en llamadas reales en las últimas 4 semanas, qué parte tenía respuesta
aprobada. Sale de `live_assist_events` (`is_objection`, `source_id`). Con menos de 3 casos, recuento.

### 8.2 Success rate

Se calcula sin intervención del comercial, comparando lo que Vocify sugirió con lo que pasó en la llamada.

Entrada: cada sugerencia registrada en `live_assist_events` (kind `suggest`, `is_objection`, `say_this`,
`source_id`, `latest_turn`, `capture_id`). El `capture_id` es el id de la llamada (memo), que tiene la
transcripción completa.

Dos veredictos por sugerencia, ambos por intención y no por palabras exactas:

1. **¿Se usó?** Localizar el turno del cliente en la transcripción y leer qué dijo el comercial a continuación.
   Resultado: usada, adaptada, no usada o no se sabe.
2. **¿Resolvió?** Solo si se usó o se adaptó. Leer lo que dijo el cliente después. Resultado: resuelta (acepta,
   contesta lo que se le preguntó, pasa al siguiente tema), no resuelta (repite la objeción, la endurece o corta)
   o no se sabe.

Fórmulas, por respuesta (no por comercial):

- **Success rate** = resueltas / (usadas + adaptadas con veredicto claro).
- **Tasa de uso** = (usadas + adaptadas) / sugerencias con veredicto claro.
- Los "no se sabe" se cuentan aparte y nunca suman como éxito.
- El porcentaje solo se muestra con al menos 3 casos con veredicto; por debajo, el recuento ("2 de 2").
- Se presenta como estimación, con los casos a un clic para que el jefe vea de dónde sale.
- El jefe puede corregir un veredicto desde el caso ("este sí se resolvió"). La corrección se guarda y cuenta
  en el success rate.

Una respuesta entra en la cola cuando acumula al menos 3 casos en los últimos 30 días en que no se usó o se usó
y no resolvió.

Limitaciones conocidas:

- `live_assist_events` guarda 90 días y recorta la frase del cliente a 300 caracteres. Los casos que entran en la
  cola se copian a `playbook_review_moments`.
- No hay tiempos por palabra en llamadas de dialer o HubSpot (informe del 2026-09-30), así que el turno del
  cliente se localiza por texto.
- Saber quién es el comercial y quién el cliente en la transcripción guardada depende de las etiquetas de
  hablante. En el informe del 2026-09-30 esa asignación fallaba a veces. Hay que comprobar su estado actual.

### 8.3 Cola y resumen semanal

Cola en Playbook, siempre disponible. Cada semana, un bloque "Respuestas a mejorar" (las 5 de más valor) en el
informe semanal del Head of Sales (`services/reporting/`; el punto exacto de enganche se confirma en el plan).
Cada caso muestra la frase del cliente, lo
sugerido, lo que dijo el comercial y qué pasó después, sin nombres.

### 8.4 Acciones del jefe sobre un caso

- **Mantener**: la respuesta está bien; el caso fue ruido.
- **Yo diría…**: su versión.
- **Añadir una rama** a la respuesta, con el "cómo se nota" redactado por Vocify desde el caso.
- **Crear una objeción nueva.**

Vocify propone cuál de las cuatro. Las mejoras se acumulan en el borrador y se publican por lotes. Las
propuestas automáticas de partir una objeción en subgrupos exigen al menos 3 casos parecidos.

### 8.5 Comprobación previa de viabilidad

El success rate es lo que más riesgo técnico tiene. La primera tarea de la fase 3 es una prueba corta sobre
llamadas reales: localizar la sugerencia en la transcripción y emitir los dos veredictos. Se compara con las
etiquetas manuales de Toni sobre al menos 20 sugerencias. Umbral acordado para seguir: acuerdo de al menos
el 80% y no más del 30% de "no se sabe". Si no se cumple, se detiene y se replantea antes de construir el resto
de la fase 3.

## 9. Coordinación con coaching (Dani)

Contrato que nos comprometemos a mantener: el playbook publicado sigue siendo `{steps, entries, qualification}`.
Solo añadimos contenido (respuestas con ramas, muchas entradas propias, ejemplos de pasos) y campos opcionales.
Mensaje para Dani en el apéndice A.

## 10. Riesgos

| Riesgo | Cómo se cubre |
|---|---|
| Dato mal extraído de un documento | Frase de origen en cada dato y aprobación del jefe. |
| Saturar al jefe | Rondas de unas 10 preguntas, cola con tope, resumen semanal de 5. |
| Success rate poco fiable | Comprobación de viabilidad (8.5), estimación con casos visibles, mínimo de 3 casos. |
| Hablantes cambiados en transcripciones | El jefe confirma quién habla en las llamadas modelo; el success rate usa solo llamadas con asignación fiable. |
| Ramas que no caben en 1.200 caracteres | La propuesta se descarta con aviso y se ofrece crearla como objeción propia. |
| Choque con el trabajo de coaching | Contrato y mensaje de la sección 9. |

## 11. Verificación y despliegue

- Tests unitarios de los servicios nuevos y casos nuevos en el simulador de llamadas, con el proveedor que usa el
  resto de llamadas por-llamada (DeepSeek en Together). No se usa Gemini en pruebas.
- Nunca se escribe en HubSpot: las pruebas y reprocesados solo leen.
- Las pantallas nuevas se verifican en el navegador con Reticle antes de darlas por hechas.
- Es un cambio grande: la norma del repo lo lleva a la rama `staging`; Toni pidió meterlo directamente en `main`
  (todo apagado por flags). Las tablas nuevas llevan un SQL de activación para que lo ejecute el fundador; el agente
  no tiene acceso para crear tablas.
- Varias sesiones comparten la carpeta: cada commit lleva solo los archivos propios.

## 12. Preguntas abiertas

No quedan preguntas abiertas. El tope por respuesta se decidió en 1.200 caracteres.

## Apéndice A: mensaje para Dani

> Dani, estamos montando el proceso por el que un Head of Sales vuelca su conocimiento y perfecciona las
> respuestas del playbook (spec: `docs/superpowers/specs/2026-10-16-playbook-volcado-y-perfeccionamiento-design.md`).
> No tocamos ni la ayuda en directo ni el coaching. Para que no te limites a las reglas de hoy y le saques
> partido a lo que generamos, esto es lo que conviene contemplar:
>
> 1. Respuestas más ricas: `guidance` era una respuesta de hasta 600 caracteres por categoría fija; hemos subido
>    el tope a 1.200. Con nuestro proceso llevará ramas ("si es X…, si es Y…"). Conviene juzgar por
>    intención y por rama, no contra un texto único. `build_phrases` (briefs.py) cita la respuesta entera.
> 2. Muchas preguntas técnicas del producto entrarán como entradas `custom` (hasta 200). No son objeciones: no
>    deberían contar como "objeción no manejada".
> 3. Los pasos tendrán `example` con ejemplos reales sacados de llamadas buenas. Sirven para juzgar intención.
> 4. Las llamadas modelo NO se guardan: se leen una vez, Vocify propone qué conservar (un ejemplo real para un
>    paso, una rama de una respuesta) y solo lo que el jefe acepta entra en el playbook como `example` o rama.
>    No hay tabla de llamadas modelo.
> 5. Medimos por respuesta si el comercial dijo lo sugerido y si resolvió la objeción o la duda (success rate).
>    Tu "¿el playbook funciona?" compara lo mismo. Mejor una sola función y una sola tabla de veredictos para los
>    dos. Dinos qué criterio de "resuelta" usas.
> 6. Las mejoras del jefe se publicarán por lotes (al acabar la prueba y cada semana), así que habrá más
>    versiones publicadas que hoy. Las llamadas siguen fijadas a su versión; compara siempre contra la fijada.
> 7. No cambiaremos la forma del playbook publicado `{steps, entries, qualification}`, solo añadiremos contenido
>    y campos opcionales. Avísanos si cambias cómo lees `entries` o los ids `objection:custom:<slug>`.
> 8. Nuestro success rate depende de saber quién habla en la transcripción guardada. Si cambias esa asignación,
>    avísanos.
> 9. Archivos: nosotros en `services/playbooks/`, `api/playbook_*` y `features/playbooks/`; tú en
>    `services/coaching/`. Migraciones: ya hay dos `080_*` y una `081_demo_profiles`; la nuestra es la `082`
>    (`082_playbook_assistant`). Si añades otra `082`, renumera la tuya o la nuestra: solo hay que decirlo.
> 10. El informe semanal del Head of Sales gana un bloque opcional `playbook_improvement` (solo con los dos flags
>     y solo si hay respuestas que fallan): `team_snapshot(..., playbook_improvement=None)` y una sección en los dos
>     renderers del email. No cambia su contrato. La página del informe en la app aún no lo pinta.

## 13. Estado de la implementación (16 oct 2026)

Hecho, en `main`, con tests (backend `tests/playbooks` y `tests/reporting`, front `src/lib/*.test.ts`):

- Fase 1: preguntas guiadas («Lo que falta»), varios documentos a la vez con fusión en servidor, resumen de lo
  entendido, llamada modelo sin guardar, tope de respuesta en 1.200 caracteres.
- Fase 2: «La prueba» (10–12 casos, corrección, rama, «nunca digas esto», frase parecida) con el mismo motor de
  la ayuda en directo llamado con el borrador; activación con aviso por debajo del 80%.
- Fase 3: cobertura, success rate, cola de respuestas que fallan (≥3 casos en 30 días), acciones sobre cada caso,
  publicar por lotes, corrección de veredictos por el jefe y bloque en el informe semanal.
- Los veredictos NO se calculan al cerrar una llamada: se calculan después, por lotes de 40 (botón «Actualizar» o
  `backend/scripts/refresh_playbook_outcomes.py`), solo sobre llamadas con más de 6 horas y con su lectura posterior.
- No se tocó la ayuda en directo, ni coaching, ni el escritorio (comprobado con `git diff`).

Decisiones de implementación que se apartan del texto de arriba:

- Migración `082` (no `081`): la `081` pasó a ser `081_demo_profiles`.
- Una respuesta pertenece a un tipo de llamada: «Precio» de Descubrimiento y de Cierre se cuentan aparte.
- La barra de publicación nombra los tipos con cambios pendientes en lugar de «Publicar mejoras (3)».
- Sin el flag del success rate «Mejoras con el uso» muestra solo la cobertura; la cola, el botón Actualizar y la
  publicación desde la cola necesitan `PLAYBOOK_SUCCESS_RATE_ENABLED`.

Pendiente de Toni / el fundador (ver `docs/superpowers/plans/2026-10-16-activacion-playbook-asistente.sql`):

1. Ejecutar el SQL de las 3 tablas (082) y acordar el número con Dani.
2. Encender `PLAYBOOK_ASSISTANT_ENABLED` para una empresa de prueba y probarlo de punta a punta.
3. La hoja de viabilidad del success rate (`backend/evals/outcomes/README.md`) con llamadas reales: no se ha
   generado (necesita datos de producción y 20 etiquetas a mano). Hasta que dé «SIGUE», el flag se queda apagado.
   Además, una sugerencia solo se liga a su llamada si el evento de ayuda en directo trae `capture_id`: hasta el commit
   `a0ce79dd` de Dani (16 oct) ninguno de los 2.804 eventos lo traía, así que no hay nada que juzgar de antes de esa fecha
   y la hoja saldrá vacía hasta que salga la app de escritorio que envía `call_id`. Se acepta el id de la memo y el
   `client_capture_id` que la app dio a la grabación. La cobertura no depende de esto y ya funciona.
4. Las pantallas se vieron en la página de previsualización de desarrollo (claro, oscuro y móvil), no contra la
   página real del Playbook ni con Reticle (sin sesión de prueba).
