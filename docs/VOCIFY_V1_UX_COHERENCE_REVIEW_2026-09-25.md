# Vocify V1 — revisión de UX, coherencia y resultado de producto

Fecha: 25 de septiembre de 2026. Rama revisada: `feat/vocify-v1`, worktree `/Users/danizal/getvocify/.worktrees/vocify-v1`. Último commit contrastado para esta revisión: `653f0c9`. La rama recibió correcciones durante la auditoría; se distinguen abajo de los problemas todavía presentes. Los cambios locales de desktop de otra tarea quedan fuera de este corte.

Esta es una revisión, no una implementación. No se han cambiado código de producto, datos del CRM, procesos publicados ni configuración de cuentas.

## Qué tiene que conseguir el producto

La referencia es `PRODUCT_PLANNING_ANALYSIS_2026-09-21.md`, los contratos y planes V1, y las decisiones vigentes de `00-decisiones.md`.

Para el comercial, el resultado esperado es: saber a quién contactar y por qué ahora → recuperar el contexto → conversar → revisar únicamente lo necesario → dejar CRM y seguimiento preparados → continuar trabajando.

Para el manager: definir su propio método → aplicarlo a las interacciones correctas → identificar incumplimientos concretos con evidencia → comprobar evolución del equipo. La captura es la entrada de ambos recorridos.

La implementación presenta muchas piezas de esos recorridos, pero varias conexiones necesarias todavía faltan. El principal riesgo es que la interfaz dé apariencia de capacidad terminada donde el usuario sigue teniendo que reconstruir contexto o donde no existe un productor de los datos que la pantalla espera.

## Evidencia y límites

- Observación real de Inicio, cola de llamadas, detalle de dos interacciones, Equipo, Preguntar y Proceso, mediante navegador, árbol accesible, capturas y consola.
- Inspección de los componentes montados y de sus rutas reales de API, adaptadores, persistencia y productores de inteligencia. La existencia de un componente o test aislado no se trata como prueba del recorrido.
- Reproducciones locales, sin red ni escritura en base de datos: pérdida de fechas y orden en Hoy; errores de lectura convertidos en cero actividad; extracción sin observaciones de playbook; checklist sin captura y con uno/dos playbooks.
- Las primeras observaciones del navegador corresponden a la rama antes de varios commits correctivos. Posteriormente `localhost:8080` y el backend de `8888` pasaron a ejecutarse desde el checkout principal. Se verificó mediante los directorios de trabajo de los procesos. Se dejó de atribuir ese navegador a V1.
- No hay veredicto Reticle: sus herramientas MCP no estaban disponibles en esta sesión. No se ha verificado una grabación nativa, un envío real, una escritura CRM ni una migración aplicada. Las reproducciones de funciones son evidencia de lógica, no una validación nativa.

## Hallazgos pendientes, por impacto

### UX-01 · P1 · «Hoy» no conserva quién debe hacer la tarea ni cuándo corresponde

**F05/F06. Objetivo:** preparar el día del comercial con compromisos propios y vencimientos reales.

La consulta de tareas HubSpot solicita asunto, estado y clave de deduplicación, pero no responsable ni vencimiento; filtra únicamente tareas no completadas. Pipedrive sigue el mismo patrón de actividades abiertas. El adaptador descarta esas dimensiones y la composición añade las tareas en el orden recibido, después de las señales. No hay selección por comercial ni orden temporal en ese camino.

En el navegador aparecieron asuntos como «el martes que viene» y una tarea de febrero bajo «Hoy», sin fecha absoluta, contacto enlazado ni explicación de atraso. Un título con una fecha antigua puede ser una tarea legítimamente atrasada: el problema demostrado es que el sistema no usa su vencimiento ni permite distinguirlo.

**Evidencia:** [scheduler.py](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/hoy/scheduler.py:86), [adaptación](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/hoy/scheduler.py:42), [lectura por conexión de empresa](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/api/today.py:224).

Reproducción local: una tarea de 2030 seguida de una vencida conservó ese orden, perdió ambas fechas y produjo `pulse=2`. Ese pulso cuenta tareas; el plan lo define como actividad real.

**Cierre exigible:** dos comerciales y tareas vencidas, actuales y futuras; cada uno ve su trabajo, con fecha comprensible, orden correcto y procedencia. El pulso usa actividad o cambia explícitamente de significado.

### UX-02 · P1 · El botón «Empezar a llamar» lleva a un estado sin llamada ni acceso al CRM

**F06. Objetivo:** ejecutar la recomendación con un gesto y conservar el ritmo de llamadas.

Comprobado en pantalla: al pulsarlo desaparece el listado y quedan nombre, motivo, «Saltar» y «Salir». El enlace de CRM que sí existía en la tarjeta desaparece. No hay acción de llamada, resultado de llamada ni transición hacia revisión en ese componente. Además, la tarjeta normal ofrece «Descartar», pero no aplazar ni resolver.

**Evidencia:** [TodayPanel.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/today/components/TodayPanel.tsx:87), [TodayItemList.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/today/components/TodayItemList.tsx:56).

**Cierre exigible:** recomendación → llamada real o fallback explícito al CRM → resultado → siguiente contacto. Una conversación abre su revisión; buzón o fallo no se presentan como conversación completada.

### UX-03 · P1 · Los pendientes adicionales quedan inaccesibles

**F05.** El navegador mostró **«293 más»**, pero era texto sin interacción. Backend recorta a siete; frontend no tiene expansión ni petición de continuación. Tampoco hay enlace a la tarea concreta cuando no se ha podido resolver contacto.

**Evidencia:** [recorte del servidor](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/hoy/scheduler.py:311), [contador sin acción](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/today/components/TodayPanel.tsx:111), [tarea sin fallback](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/today/components/TodayItemList.tsx:90).

**Cierre exigible:** acceder al octavo elemento y a una tarea sin contacto, conservando orden y contexto. Siete visibles es una decisión válida; las restantes deben poder descubrirse.

### UX-04 · P1 · El recorrido normal no produce el coaching que promete la interfaz

**F0/F09/F11. Objetivo:** evaluar el método de la empresa y entregar una mejora concreta respaldada por la conversación.

La extracción de inteligencia construye `playbook_observations: []` y no incluye el playbook en los mensajes enviados al modelo. El otro intérprete del worker tampoco construye observaciones del método. El ensamblador espera esas observaciones para puntuar y asigna siempre listas vacías a fortalezas y mejoras. El brief posterior consume precisamente esas listas.

**Evidencia:** [extract.py](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/intelligence/extract.py:100), [contexto del modelo](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/intelligence/extract.py:108), [interpret.py](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/intelligence/interpret.py:68), [score_assembly.py](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/coaching/score_assembly.py:143), [consumidor del brief](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/coaching/briefs.py:81).

Reproducción local del camino extracción → ensamblado, incluso con versión de playbook presente: `observations=[]`, `value=null`, `reason=insufficient_evidence`, `strengths=[]`, `improvements=[]`. Esto demuestra una conexión ausente; no es simplemente falta de datos en la cuenta inspeccionada.

**Cierre exigible:** publicar un método, procesar una conversación nueva por la ruta de usuario y obtener criterios evaluados, una mejora específica y una evidencia consultable, sin introducir el resultado a mano en una fixture.

### UX-05 · P1 · El checklist de desktop no recibe el contexto de la conversación y falla al tener varios procesos

**F01/F08/F12. Objetivo:** seguimiento automático de pasos durante meetings, aplicando la tipología correcta.

`buildListenSession` conserva modo y contacto, pero no captura o tipología. El request efectivo del checklist es solo `{call_mode: "meeting"}`. Sin captura, el servidor elige el único playbook de empresa y construye el checklist con extracción vacía. Si hay dos playbooks publicados, devuelve ausencia de contexto. El endpoint descarta los turnos finalizados si se le envían.

**Evidencia:** [sesión](/Users/danizal/getvocify/.worktrees/vocify-v1/desktop/lib/listen-policy.js:13), [inicio de grabación](/Users/danizal/getvocify/.worktrees/vocify-v1/desktop/renderer/app.js:1074), [request](/Users/danizal/getvocify/.worktrees/vocify-v1/desktop/lib/copilot-checklist.js:1), [fallback vacío](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/copilot/checklist.py:137), [restricción a un playbook](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/copilot/load_grounding.py:50), [turnos descartados](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/api/copilot.py:50).

Reproducciones locales: el request no lleva captura; con un playbook, `observed=0` y paso pendiente; con dos, `grounding=null`.

**Cierre exigible:** empresa con Descubrimiento y Cierre publicados; iniciar reunión con proceso identificable, pronunciar un criterio, comprobar auto-check por evidencia y conservar el mismo resultado al abrir la revisión. Pendiente de prueba nativa.

### UX-06 · P1 · Importar un proceso entero lo convierte en un solo criterio

**F08/F09/F12/F15.** La persistencia guarda todo el contenido importado como un único paso `imported`, con los primeros 80 caracteres como etiqueta y el documento entero como criterio. También crea una única entrada genérica `process`.

Esto pierde la estructura necesaria para responder «¿falló la apertura o la cualificación?», presentar un checklist útil y medir adherencia por paso.

**Evidencia:** [040_company_playbooks.sql](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/migrations/040_company_playbooks.sql:82), [store.py](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/playbooks/store.py:95).

**Cierre exigible:** un proceso con tres pasos y dos objeciones conserva cinco elementos distinguibles y revisables, con etiquetas y criterios legibles antes de publicar.

### UX-07 · P1 · El manager no puede mantener y revisar su proceso desde la interfaz actual

**F08.** Tras publicar, el condicional oculta el editor y tampoco ofrece lectura del contenido publicado. Al volver a la pantalla solo se cargan estados, no el texto del borrador. La recuperación pide un ID de importación dentro de «Añadir tipología», pero la respuesta de recuperación no contiene `sales_motion_key`, campo que el cliente necesita para usarla. La entrada por audio tampoco está disponible en esta pantalla.

**Evidencia:** [estado inicial y carga](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/playbooks/components/PlaybooksSection.tsx:47), [recuperación](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/playbooks/components/PlaybooksSection.tsx:164), [editor oculto](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/playbooks/components/PlaybooksSection.tsx:226), [respuesta de importación](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/playbooks/store.py:83).

**Cierre exigible:** guardar → salir → volver con el mismo borrador → revisar → publicar → consultar versión vigente → preparar una corrección. El manager no necesita conocer identificadores técnicos.

### UX-08 · P1 · Un error de lectura puede convertirse en «cero actividad» y «no hay objeciones»

**F15. Objetivo:** visibilidad fiable de lo que ocurre en el equipo.

El cargador captura excepciones y conserva listas vacías. La agregación las convierte en cero intentos/conversaciones/reuniones y cero categorías de objeción. La UI interpreta categorías vacías como «No hay objeciones esta semana». El tratamiento de resultados CRM sí mantiene `unavailable`; la inconsistencia está en las otras fuentes.

**Evidencia:** [aggregate.py](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/team_insights/aggregate.py:194), [excepción silenciada](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/team_insights/aggregate.py:262), [ObjectionBreakdown.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/team-insights/components/ObjectionBreakdown.tsx:13).

Reproducción local con lectura que lanza `TimeoutError`: `attempts=0`, `connected=0`, `meetings=0`, `objection_categories=[]`. No se simuló un fallo en la base de datos real.

**Cierre exigible:** fallo de cada fuente conserva los datos válidos y diferencia desconocido, procesándose y cero confirmado. Una caída nunca equivale a ausencia de trabajo.

### UX-09 · P1 · El manager pierde el análisis al abrir la conversación de un compañero

**F09/F10/F11/F15.** Equipo enlaza a memos para revisar evidencia, pero el detalle monta objeciones, brief posterior y scoring solo si `isOwnMemo`. La restricción de escritura del seguimiento es razonable; el análisis que necesita leer el manager desaparece con la misma condición.

**Evidencia:** [MemoDetail.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/pages/dashboard/MemoDetail.tsx:563), [enlaces desde Equipo](/Users/danizal/getvocify/.worktrees/vocify-v1/src/pages/dashboard/TeamInsightsPage.tsx:170).

**Cierre exigible:** owner/admin abre una interacción ajena desde Equipo y puede revisar criterio, objeción y evidencia en modo lectura; la autorización de editar o enviar sigue siendo independiente. Comprobación pendiente con ese recorrido real.

### UX-10 · P2 · La jerarquía visual de Inicio deja el trabajo diario en segundo plano

**F05/UI.** En la captura de escritorio, la grabadora ocupa aproximadamente 370 px antes de «Hoy». El acceso a tareas útiles empieza pasada media pantalla; Recientes queda después de una lista larga. La home prioriza la entrada de información sobre la acción que el producto quiere preparar proactivamente.

**Evidencia:** observación visual y [DashboardHome.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/pages/dashboard/DashboardHome.tsx:10).

**Dirección de corrección:** Hoy y la siguiente acción ocupan el primer plano; grabar/importar siguen accesibles con peso acorde al uso. Historial aparece separado. La primera pantalla debería permitir entender qué merece atención sin recorrer formularios de captura.

### UX-11 · P2 · La revisión posterior obliga a recorrer módulos antes de terminar la tarea

**F02/F03/F09/F10/F11/F14/UI.** Antes de los campos y la acción del CRM se montan brief previo, objeciones, formulario de nota, propuesta de reunión, brief posterior, score y seguimiento. En la captura observada, una llamada ya sincronizada abría con mensajes de análisis incompleto y varios estados pendientes, mientras la información administrativa quedaba más abajo.

El usuario necesita distinguir con rapidez qué está guardado, qué requiere decisión y qué puede revisar después. «Sin conversación todavía» se observó antes del arreglo de briefs y se trata como hallazgo histórico, no como prueba del código corregido.

**Evidencia:** [orden de componentes](/Users/danizal/getvocify/.worktrees/vocify-v1/src/pages/dashboard/MemoDetail.tsx:560).

**Dirección de corrección:** encabezado con contacto y estado real; decisiones pendientes y cambio CRM en primer plano; seguimiento accesible; coaching breve ampliable; transcripción y evidencias a demanda. El coaching en segundo plano no debería bloquear ni desplazar el cierre administrativo.

### UX-12 · P2 · La pantalla de coaching no permite entender su evaluación

**F09.** «Ver criterios» muestra el valor numérico y la adherencia, sin criterios, estado individual ni citas. El modelo de presentación descarta esa información. La ausencia de respuesta de API oculta el componente. En Equipo, «Sin adherencia» describe también la ausencia de evaluación, pudiendo leerse como incumplimiento.

**Evidencia:** [CoachingScore.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/components/dashboard/memos/CoachingScore.tsx:50), [ocultación por falta de datos](/Users/danizal/getvocify/.worktrees/vocify-v1/src/components/dashboard/memos/CoachingScore.tsx:15), [AdherenceBreakdown.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/team-insights/components/AdherenceBreakdown.tsx:10).

**Cierre exigible:** entender qué paso se cumplió, qué falta, qué no pudo evaluarse y qué frase lo respalda. Mostrar «Sin evaluaciones disponibles» cuando corresponda, separado de una adherencia evaluada de 0 %.

### UX-13 · P2 · Equipo muestra cifras, pero ofrece poca ayuda para decidir dónde intervenir

**F15.** No presenta periodo visible, selector temporal ni evolución. Internamente se calcula la semana actual de Madrid. «Para revisar» selecciona los tres resúmenes más recientes, sin justificar por qué requieren atención, sin autor/fecha en la fila y sin selección por desviación del proceso. La distribución de objeciones no enlaza a las conversaciones que componen cada categoría. La cobertura de evaluación llega de API, pero no se incorpora al modelo visible de métricas.

**Evidencia:** [filtros y modelo](/Users/danizal/getvocify/.worktrees/vocify-v1/src/pages/dashboard/TeamInsightsPage.tsx:25), [selección de ejemplos](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/team_insights/aggregate.py:172), [semana fija](/Users/danizal/getvocify/.worktrees/vocify-v1/backend/app/services/team_insights/aggregate.py:38), [categorías sin navegación](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/team-insights/components/ObjectionBreakdown.tsx:23).

**Cierre exigible:** el manager identifica periodo, muestra evaluada y una desviación concreta; abre un ejemplo relevante con autor y fecha; compara con el periodo anterior sin confundir cambio de cobertura con mejora.

### UX-14 · P2 · Preguntar pierde contexto de pantalla y continuidad al cerrarse

**F07.** El panel se monta globalmente sin contacto/memo actual; los turnos envían solo texto. Sin embargo, su ejemplo dice «este contacto». Al cerrar, se desmonta. Al reabrir recupera únicamente el último turno, no la secuencia de preguntas y respuestas. La confirmación específica utiliza un ID de contacto y no incluye un resumen estructurado de los campos/cambios en ese bloque. Un fallo de confirmación se guarda en `view.notice`, que no se renderiza.

**Evidencia:** [montaje](/Users/danizal/getvocify/.worktrees/vocify-v1/src/components/dashboard/DashboardLayout.tsx:282), [recuperación](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/ask/components/AskPanel.tsx:58), [payload](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/ask/components/AskPanel.tsx:132), [confirmación](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/ask/components/AskPanel.tsx:283).

**Cierre exigible:** abrir desde un contacto identifica ese contexto de forma visible; cerrar/reabrir conserva conversación; confirmar permite reconocer destino y cambio; un error explica cómo continuar. El arreglo reciente del fallo del motor no resuelve estos puntos de presentación.

### UX-15 · P2 · La campana no permite recorrer los informes

**F13.** La campana enlaza al primer informe recibido; no muestra lista ni acceso a los anteriores. Sin informe —o con error de lectura— navega a Inicio. El detalle no muestra el periodo del informe y usa rutas como texto de los enlaces de ejemplo.

**Evidencia:** [ReportBell](/Users/danizal/getvocify/.worktrees/vocify-v1/src/components/dashboard/DashboardLayout.tsx:43), [ReportPage.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/pages/dashboard/ReportPage.tsx:55).

**Cierre exigible:** distinguir sin informes de fallo de carga; encontrar un informe anterior; conocer periodo y destinatario; abrir ejemplos por un texto que explique qué se va a revisar.

### UX-16 · P2 · La priorización adicional no identifica al destinatario de la acción

**F04.** Cada entrada de prioridades muestra motivo y `next_action` como párrafos. No renderiza nombre del contacto ni control para actuar. Aunque el ranking fuera perfecto, ese bloque no permite resolver «a quién y qué hago ahora».

**Evidencia:** [ContactPriorities.tsx](/Users/danizal/getvocify/.worktrees/vocify-v1/src/features/today/components/ContactPriorities.tsx:26).

**Cierre exigible:** contacto identificable, contexto mínimo y acción ejecutable que conserve ese contacto.

### UX-17 · P2 · El idioma y la gramática de interacción cambian dentro del mismo recorrido

**UI/transversal.** La interfaz observada mezcla «Hoy», «Preguntar» y «Ajustes» con «Record», «Paste transcript», «Review», «Synced», «Transcript», «Write correction» y «You». «Notas de voz» contiene también llamadas y reuniones. Los estados de análisis aparecen con tratamientos diferentes: algunos ocultan el bloque, otros reservan espacio y otros muestran un mensaje sin recuperación. Se alternan tarjetas compartidas, tarjetas React y secciones de texto sin una jerarquía consistente.

La paleta sobria y la navegación corta son una buena base. La mejora visual necesaria está en ordenar la importancia, unificar estados y hacer evidentes las acciones; no se ha medido contraste ni validado teclado completo, así que no se declara conformidad de accesibilidad.

**Cierre exigible:** recorrer captura → detalle → CRM → seguimiento con un solo idioma, nombres de objetos consistentes y una distinción estable entre disponible, pendiente, fallido y terminado.

## Hallazgos anteriores corregidos o que requieren una nueva comprobación

| Tema | Situación en el corte actual |
|---|---|
| Crash completo del memo al fallar propuesta de reunión | Reproducido en dos interacciones antes del arreglo. `a3c7e26` aporta `phrases`; `653f0c9` sincroniza copias. Corregido en código; pendiente repetir en el servidor de V1 con error de API. |
| Lectura de importación de otro tenant | `692b9cb` añade el scope de empresa. Se retira como defecto abierto de esa ruta. |
| Brief que no encuentra el contacto | `36d319b` y `7afc03a` corrigen filtro/lectura. Se retira el fallo original como vigente. Queda por verificar comportamiento completo, campos de inteligencia y conexiones. |
| Reloj congelado en prioridades | `e7c31c3` cambia el reloj. Se retira como defecto abierto. |
| Ask pendiente cuando el motor devuelve vacío | `50ef17d` lo pasa a fallo. Pendiente ver recuperación visible; UX-14 sigue abierto. |
| Hoy vacío siempre incompleto | `aec15e4` trata la ausencia de señales como cobertura completa. Corrige el caso original; no prueba por sí solo que una lectura/producción fallida se distinga de ausencia legítima. |
| Firma/notarización/enlace público de descarga | Fuera del alcance por decisión explícita. No son bloqueadores de esta rama. |
| Veinte conversaciones de evaluación | La decisión admite conversaciones sintéticas. No se exige un dataset de empresa. Sigue siendo necesario que evalúen el comportamiento real, y UX-04 permanece. |
| Worker | La decisión documentaba el flag apagado, pero la configuración observada durante la primera revisión lo tenía activado. No se usa el supuesto de flag apagado para justificar los fallos. |

## Orden de corrección recomendado

1. **Cerrar el recorrido del comercial:** responsables/fechas de Hoy, acceso a todos los pendientes y una acción real por recomendación. Verificar hasta el resultado y el siguiente contacto.
2. **Cerrar el recorrido del método:** proceso estructurado y mantenible, captura ligada a tipología/versión, observaciones con evidencia, checklist/scoring/brief que consuman esas mismas observaciones.
3. **Hacer fiable la lectura del manager:** errores separados de ceros, cobertura y periodo visibles, ejemplos pertinentes y detalle de compañero accesible.
4. **Ordenar la experiencia conjunta:** home centrada en el trabajo del día, revisión centrada en decisiones, contexto persistente en Ask, informes recuperables e idioma uniforme.

No hace falta ampliar el alcance funcional para resolver estos puntos. Son condiciones para que las capacidades V1 ya acordadas produzcan el resultado que motivó construirlas.

## Pruebas de aceptación de producto

| Recorrido | Resultado que debe poder observarse |
|---|---|
| Manager publica Descubrimiento y Cierre | Puede leer/corregir ambos; cada interacción usa el proceso correcto. |
| Comercial abre el día | Ve su trabajo ordenado, fechas claras y acceso a todo el resto. |
| Ejecuta una recomendación | Contexto → llamada/CRM → resultado → siguiente contacto, sin buscar de nuevo a la persona. |
| Meeting con varios pasos | El checklist cambia por lo dicho; la revisión conserva la evidencia y la versión evaluada. |
| Termina conversación | Distingue lo guardado y lo pendiente; puede completar la administración sin esperar al coaching. |
| Manager investiga una desviación | Pasa del indicador al comercial, conversación, criterio y evidencia. |
| Falla una fuente o un trabajo | El resto sigue siendo usable; se explica lo desconocido y cómo recuperarlo; no se inventa un cero. |
| Reabre Ask o un informe anterior | Conserva contexto, puede entender el resultado y continuar sin reconstruirlo. |

