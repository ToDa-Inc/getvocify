# Plan · Dashboard Head of Sales + Coaching

> Fecha: 2026-09-28. Referencia de diseño: *Motor de Ventas OS* (motordeventas-os.vercel.app), analizada a partir de capturas de las pestañas Inicio, Deals, Actividad comercial y Forecast.
> Alcance de este documento: el **plan** (qué se construye, en qué orden y con qué datos). Cada fase tendrá después su propio `spec.md` según `_TEMPLATE/`.

---

## 0. La idea en una frase

**Motor de Ventas te dice QUÉ está pasando en tu equipo, sacándolo de lo que el CRM registra. Vocify te dice además POR QUÉ, sacándolo de lo que se dijo en cada llamada y reunión.**

Copiamos de Motor de Ventas el esqueleto: sus métricas de actividad y conversión, y su rigor al definirlas. Encima ponemos la capa que solo nosotros podemos tener, la de **calidad y contexto de las conversaciones**.

```
             ┌─────────────────────────────────────────────────────────┐
  CALIDAD    │ score, adherencia al playbook, objeciones superadas,    │  ← solo Vocify
  (por qué)  │ decisor identificado, próximo paso acordado, competidor │
             ├─────────────────────────────────────────────────────────┤
  CONVERSIÓN │ conexión → conversación → reunión → realizada → deal    │  ← mix
             │ → ganado; ciclo, win rate, no-show                      │
             ├─────────────────────────────────────────────────────────┤
  ACTIVIDAD  │ llamadas, conectadas, contactos creados, reuniones      │  ← lo que ya hace
  (qué)      │ agendadas, pipeline generado                            │    Motor de Ventas
             └─────────────────────────────────────────────────────────┘
```

---

## 1. Principios de diseño

1. **El Head of Sales no tiene tareas; tiene visibilidad.** El dashboard no es una lista de cosas que hacer hoy, sino una **radiografía del equipo**: cómo vamos, por qué, quién necesita ayuda y en qué, y qué está diciendo el mercado. Las anomalías se muestran como *señales* dentro de la analítica ("la conexión de Dani ha caído un 40 %"), nunca como tareas pendientes.
2. **Cada número dice a qué período responde** (copiado de Motor de Ventas). Unos bloques son una foto "a día de hoy" (pipeline abierto, deals activos) y otros dependen del período (actividad, win rate). Lo indicamos en el subtítulo de cada bloque.
3. **Un solo filtro de tiempo global** (Esta semana · Este mes · Últimos 30 días · Trimestre · Personalizado), más el filtro de persona o rol. No ponemos un selector repetido en cada bloque como hace Motor de Ventas; un bloque solo puede fijarse a su propio período si lo necesita.
4. **Dos ejes de fecha para las reuniones** (copiado): *agendadas* se cuentan por la fecha en que se agendaron y *realizadas* por la fecha en que se celebraron. Cada columna ambigua lleva un `(?)` que lo explica.
5. **Estados vacíos que explican.** Nunca "0,0 %" con 0 de 0: se muestra "—" y el motivo ("sin deals cerrados en el período").
6. **Progressive disclosure (§7.1 de la planificación).** Primero cuatro números, después la tabla del equipo y, al hacer clic, el detalle de cada comercial. Máximo **4 pestañas**.
7. **Todo número de calidad enlaza a su evidencia**: la llamada y el minuto exactos. Es lo que convierte una métrica en coaching, y es nuestra ventaja.
8. **No competimos con los reportes de HubSpot** (§1.5). Revenue, MRR y forecast se muestran solo como contexto. Lo diferencial es actividad × calidad.

---

## 2. Requisito previo: SDR y AE son dos perfiles distintos

Hoy `company_members.role` solo tiene `owner / admin / member`, que son **permisos**. Hace falta además una **función comercial**:

- Nuevo campo `company_members.sales_role`: `sdr | ae | manager | other`. Lo asigna el admin en la página Team, y por defecto vale `other`.
- Las métricas, la tabla del equipo, los playbooks y el coaching **se separan por `sales_role`**. Un SDR y un AE no se comparan entre sí nunca.

| | **SDR** (prospección, cold call) | **AE** (discovery → demo → cierre) |
|---|---|---|
| Su trabajo | Generar reuniones cualificadas | Convertir reuniones en ingresos |
| Métrica de volumen | Llamadas, contactos alcanzados | Reuniones realizadas, deals activos |
| Métrica de conversión | Conectada → reunión agendada; agendada → realizada | Reunión → deal avanzado; deal → ganado |
| Métrica de resultado | Reuniones realizadas y **pipeline generado €** | Revenue cerrado, win rate, ciclo |
| Métrica de calidad (Vocify) | Apertura, pitch, objeciones superadas, cierre de la cita con fecha y hora | Discovery completo (pain, decisor, presupuesto, timing), siguiente paso acordado, gestión de objeciones y competidores |

---

## 3. Dashboard Head of Sales

### 3.1 Estructura: cuatro pestañas

| Pestaña | Pregunta que responde | Inspirado en |
|---|---|---|
| **Pulso** | ¿Cómo va el equipo este período y qué ha cambiado? | MdV · Inicio |
| **Equipo** | ¿Quién rinde, en qué punto se atasca cada uno y por qué? | MdV · Actividad comercial |
| **Pipeline** | ¿Qué deals están en riesgo y qué se ha movido? | MdV · Deals + Forecast (Movimiento) |
| **Mercado** | ¿Qué nos dicen los clientes: objeciones, competidores, motivos de pérdida? | *No existe en MdV; es 100 % Vocify* |

### 3.2 Pulso (pantalla de entrada)

- **Cabecera:** filtros de período y rol, y "Actualizado hh:mm" con botón de refrescar (copiado).
- **Cuatro KPIs**, cada uno comparado con el período anterior (▲▼ y porcentaje):
  1. Reuniones realizadas (SDR) / Revenue cerrado (AE). Se muestran según el filtro de rol; en "Todos" se muestran ambos.
  2. Tasa de conexión → reunión, que es la conversión clave.
  3. **Adherencia al playbook del equipo** (§7.4). Es la métrica que el Head of Sales reporta hacia arriba.
  4. **Score medio de las conversaciones.**
- **Funnel del equipo** con barras por etapa, como el de MdV, pero con nuestras etapas:
  - SDR: `Llamadas → Conectadas → Conversaciones útiles → Reuniones agendadas → Realizadas`
  - AE: `Reuniones → Discovery completo → Propuesta → Ganado`
- **Tendencia semanal**, gráfico de área como el de MdV: actividad (llamadas) frente a resultado (reuniones), con la línea de adherencia superpuesta.
- **Señales del período.** Son como mucho 3–5 frases generadas a partir de reglas, no de un LLM libre. Cada una enlaza a su evidencia. Ejemplos:
  - "La objeción *'ya tenemos proveedor'* ha subido del 12 % al 27 % de las llamadas conectadas."
  - "Ringover aparece en 4 de los 5 deals perdidos este mes."
  - "La adherencia en *cualificación* del equipo SDR ha pasado del 48 % al 63 % en 4 semanas."

### 3.3 Equipo: la tabla central

Es la tabla "Actividad del equipo" de MdV, ampliada. Tiene columnas configurables (copiado), fila de **total del equipo** y **mediana** (copiado y ampliado), un orden por defecto configurable y exportación a CSV.

**Vista SDR**

| Columna | Definición | Fuente | Fase |
|---|---|---|---|
| Llamadas | Nº de `outbound_calls` y llamadas de HubSpot en el período | `outbound_calls`, memos `hubspot_call` | F1 |
| Resultado de las llamadas | Conectadas / buzón / sin respuesta / otras (desplegable como el "+63 otros" de MdV) | `call_disposition`, `screening_outcome` | F1 |
| % de conexión | conectadas ÷ llamadas | ídem | F1 |
| Conversaciones útiles | Conectadas con duración ≥ umbral (p. ej. 60 s) | `recording_duration` | F1 |
| Reuniones agendadas `(?)` | Reunión acordada en la llamada, **detectada por IA** con fecha y hora (§5), por fecha de agendado | clasificador nuevo | F2 |
| Realizadas / no show `(?)` | Reuniones de HubSpot celebradas, por fecha de celebración | sincronización de reuniones de HubSpot | F2 |
| Conv. → reunión | agendadas ÷ conversaciones útiles | derivada | F2 |
| Pipeline generado € | Importe de los deals creados a partir de sus reuniones. Atribución por el owner del deal y por el creador de la reunión; así evitamos el "Otros 100 %" de MdV | HubSpot | F2 |
| **Score medio** | Media del score de sus conversaciones | scoring | F3 |
| **Adherencia** | % de pasos del playbook cumplidos, con desglose por fase | scoring | F3 |
| **Objeciones superadas** | objeciones rebatidas ÷ objeciones recibidas | clasificador de objeciones | F2/F3 |
| **Foco de coaching** | El cuello de botella principal de ese comercial (§4.3) | motor de diagnóstico | F3 |

**Vista AE**: reuniones realizadas, deals activos, deals avanzados de etapa, win rate (con "—" si no hay cierres), ciclo medio en días (global y del período, desglosable por producto, como en MdV), ticket medio, revenue frente a objetivo (objetivo editable en línea, como en MdV), **discovery completo %**, **siguiente paso acordado %**, adherencia, score y foco de coaching.

**Ficha del comercial** (se abre al hacer clic en una fila): su funnel comparado con la mediana del equipo, su evolución en 8 semanas, adherencia por fase, sus 3 objeciones principales y cómo las gestiona, sus mejores y peores llamadas con enlace, y el foco de coaching. **Esta ficha sirve de preparación para el 1:1**: el Head of Sales la abre 5 minutos antes y tiene la conversación preparada.

### 3.4 Pipeline

- **Tabla de deals ordenada por riesgo** (copiado): empresa, etapa, importe, días sin actividad (coloreado), siguiente actividad ("Sin actividad" en rojo) y owner.
- **Columnas Vocify:**
  - resumen de la última conversación;
  - **siguiente paso acordado en la llamada, y si existe o no como tarea en el CRM**;
  - objeción abierta;
  - competidor mencionado;
  - si se ha identificado al decisor.
- **Riesgo explicable, basado en reglas**, combinando las señales del CRM (días sin actividad, sin siguiente paso) con las de la conversación (objeción de presupuesto o timing sin resolver, sin decisor, competidor presente, fecha de cierre retrasada). Cada deal muestra *por qué* está en riesgo.
- **Movimiento** (inspirado en Forecast → Movimiento): qué ha cambiado desde la foto anterior (etapa, importe, fecha de cierre retrasada, deals nuevos o perdidos), **con la causa extraída de la llamada** que lo provocó. Requiere guardar fotos del pipeline (§5, F4).
- Forecast y precisión se dejan para V2.

### 3.5 Mercado (voz del cliente)

- **Ranking de objeciones:** frecuencia, tendencia, % de veces que se superan y **qué comercial las supera mejor**, con clips de ejemplo. Enlaza con el coaching (§4).
- **Competidores:** menciones, en qué etapa aparecen, win rate cuando aparecen y qué se dice de ellos.
- **Motivos de pérdida:** el `lost_reason` de la migración 021 más el contexto de la llamada, agrupados.
- **Pains más repetidos** (`painPoints`) por segmento. Alimenta a marketing y producto.

---

## 4. Coaching

### 4.1 Filosofía (resumen de §4.1 de la planificación)

No enseñamos a vender. **Estandarizamos el proceso que ya tiene la empresa, medimos la desviación de cada comercial y señalamos el momento exacto.** Como mucho 1–2 focos por comercial y semana: nadie mejora en diez cosas a la vez.

### 4.2 El ciclo de coaching

```
 ① Playbook ─→ ② Cada interacción ─→ ③ Debrief ─→ ④ Resumen ─→ ⑤ 1:1 con ─→ ⑥ Evolución
  (manager)     se puntúa             (rep, tras    semanal     el Head of     (¿ha mejorado
                                      la llamada)   (rep+HoS)   Sales          el foco?)
     ↑                                                                             │
     └─────────────────── el manager ajusta el playbook ───────────────────────────┘
```

1. **Playbook por tipo de interacción** (§4.2 y §4.3): cold call SDR, discovery, demo y cierre. El manager lo escribe o lo sube (texto, PDF o audio), o parte de una plantilla (BANT / SPICED / MEDDIC). Se guarda **como dato**: una checklist de pasos por fase, las objeciones esperadas con su respuesta recomendada y el criterio de "buena llamada".
2. **Puntuación de cada interacción**, como background job después de la extracción. Es una clasificación acotada (booleanos por paso, patrón Jev.ai de §6.4), no un LLM razonando en abierto:
   - pasos cumplidos o no, cada uno con la marca de tiempo de la evidencia;
   - objeciones recibidas, cada una con su tipo, si era *objeción* u *obstáculo*, y si se superó;
   - flag de **dificultad**: una llamada "fácil" (el lead ya venía convencido) no puntúa más que una batallada (§4.4);
   - score = adherencia ponderada + gestión de objeciones, ajustado por dificultad.
3. **Debrief de la interacción** (§4.6): qué se hizo bien, **una sola** cosa a mejorar con el minuto exacto, y cómo lo hace el mejor del equipo. No interrumpe al comercial; lo lee cuando quiere.
4. **Resumen semanal** (§4.10): email al comercial y una versión agregada al Head of Sales (§4.5).
5. **1:1**: la ficha del comercial (§3.3) es el guion.
6. **Evolución**: el foco de la semana pasada se mide esta semana. ¿Ha subido la adherencia en esa fase?

### 4.3 El motor de diagnóstico: de la métrica al foco de coaching

Esta es la pieza que une Motor de Ventas con Vocify. Toma el funnel del comercial, lo compara con **la mediana de su mismo rol** y elige **un** cuello de botella. Después usa las conversaciones para explicar la causa. Funciona con reglas deterministas y explicables.

**SDR**

| Síntoma frente a la mediana | Diagnóstico | Foco de coaching | Evidencia de Vocify |
|---|---|---|---|
| Pocas llamadas | Volumen | Disciplina y bloques de llamada | Distribución horaria de su actividad |
| Conexión baja con volumen normal | Listas u horario, **no técnica** | Franjas y calidad de los datos | Mejores franjas de conexión del equipo |
| Conecta pero corta rápido (pocas conversaciones útiles) | Apertura | Primeros 30 segundos | Aperturas con más retención en el equipo |
| Conversaciones útiles pero pocas reuniones | Pitch u objeciones | La objeción que más pierde | Cómo la rebate el mejor SDR (clip) |
| Agenda pero muchos no-show | Cualificación y confirmación | Fijar fecha y hora y cualificar | % de citas sin fecha y hora exactas |

**AE**

| Síntoma frente a la mediana | Diagnóstico | Foco de coaching | Evidencia de Vocify |
|---|---|---|---|
| Reuniones que no avanzan | Discovery incompleto | Pain, decisor, presupuesto, timing | Qué campos del discovery le faltan |
| Deals sin siguiente paso | Control del proceso | Cerrar cada reunión con un siguiente paso fechado | % de reuniones sin siguiente paso acordado |
| Win rate bajo en la etapa final | Cierre u objeciones | La objeción final más frecuente | Motivos de pérdida y momento en que aparecen |
| Ciclo más largo que el equipo | Falta de urgencia o decisor | Multi-threading | % de deals con un solo interlocutor |
| Pierde contra un competidor concreto | Posicionamiento | Battlecard | Qué dice el cliente del competidor |

### 4.4 Pestaña Coaching: lo que ve el comercial

Cada comercial ve **solo lo suyo**. SDR y AE ven la misma estructura con sus propias métricas.

- **Mi semana**: 3–4 números frente a la semana anterior y frente a la **mediana del equipo**, anónima. No hay ranking nominal por defecto; es configurable por el manager (§7.5).
- **Mi foco**: el cuello de botella que ha salido del diagnóstico, en una sola frase, con 2–3 clips propios y 1 clip del mejor del equipo.
- **Mi adherencia por fase**: barras (apertura, cualificación, pitch, objeciones, cierre de la cita o siguiente paso) con su evolución de 8 semanas.
- **Mis objeciones**: las que más recibo, mi % de éxito en cada una y la respuesta del playbook.
- **Mis interacciones**: lista con score, que abre el debrief de cada una.
- **Biblioteca de mejores momentos** (V2): clips del equipo por objeción y por fase.

### 4.5 Reporting al Head of Sales

- **Email semanal** (lunes, vía Resend), siguiendo el mismo esquema que Pulso para que sea coherente:
  1. Cuatro KPIs frente a la semana anterior.
  2. Qué ha cambiado: las señales del período.
  3. **Por comercial, una línea**: resultado, foco de coaching y si mejoró el foco de la semana pasada.
  4. Voz del mercado: la objeción y el competidor de la semana.
  5. Movimiento del pipeline con su causa.
- **Campana en el dashboard** con las mismas señales (§8).
- **Informe mensual para "reportar hacia arriba"**: evolución de la adherencia y de la conversión del equipo. Es el argumento de retención de Vocify (§7.4).

---

## 5. Base de datos y cálculo

- **Capa de métricas única** en el backend: un endpoint `/api/team/metrics?from&to&role&user` más vistas o funciones SQL en Supabase. **Toda métrica tiene una sola definición** y la usan por igual el dashboard, el email y el coaching. Así evitamos que un número no cuadre entre dos sitios.
- **Diccionario de métricas** (documento hermano): nombre, fórmula, eje de fecha, fuente y la tooltip `(?)` que ve el usuario.
- **Sincronización de HubSpot hacia Supabase** (job diario): deals (etapa, importe, fecha de cierre, owner, creador), reuniones (fecha y resultado) y owners. Guardar **una foto diaria** de los deals permite la pestaña de Movimiento y, en V2, Forecast y Precisión.
- **Relación entre usuario y owner de HubSpot**: ya se hace por email (ver `TeamPage`). Hay que mostrar quién no está vinculado, porque es lo que provoca el "Otros" de MdV.
- **Nuevas tablas** (orientativo): `playbooks`, `interaction_scores` (una por memo: score, pasos, dificultad), `interaction_objections` (tipo, objeción u obstáculo, superada, marca de tiempo), `crm_deal_snapshots`, `coaching_focus` (una por comercial y semana).

**Qué existe ya y qué falta**

| Dato | Estado |
|---|---|
| Llamadas, disposición y duración | ✅ `outbound_calls` (`call_disposition`, `recording_duration`, `answered_at`) |
| Conectada / buzón / sin respuesta por memo | ✅ `memos.screening_outcome` |
| Resultado converted / on hold / lost con motivo | ✅ migración 021 |
| Objeciones, competidores, pains, siguientes pasos, decisores (texto libre) | ✅ `MemoExtraction`. Falta **clasificarlos** en taxonomía cerrada |
| Reunión agendada detectada en la llamada | ❌ clasificador nuevo (§5 de la planificación) |
| Reuniones realizadas / no-show, deals, owners | ❌ sincronización de HubSpot |
| SDR vs AE | ❌ `sales_role` |
| Playbooks, scoring, adherencia | ❌ nuevo |
| Fotos del pipeline | ❌ nuevo |

---

## 6. Fases (una a la vez, cada una verificable antes de empezar la siguiente)

| Fase | Entregable visible | Contenido | Depende de |
|---|---|---|---|
| **F0 · Fundamentos** | Página Team con rol SDR / AE; diccionario de métricas | `sales_role`, capa de métricas, sincronización diaria de HubSpot (deals, reuniones, owners) | — |
| **F1 · Dashboard de actividad** | Pulso + Equipo con **datos que ya tenemos** | Llamadas, conexión, conversaciones útiles, resultados, tendencia, tabla por comercial con total y mediana, ficha básica, CSV. Mercado v0: objeciones y competidores en texto libre agrupados | F0 |
| **F2 · Clasificadores** | Columnas de reuniones y objeciones; Mercado completo | Reunión agendada (booleano + fecha y hora), taxonomía de objeciones (tipo, objeción u obstáculo, superada), competidores normalizados, reuniones realizadas y no-show desde HubSpot, pipeline generado | F0 |
| **F3 · Playbooks + scoring** | Columnas de adherencia y score; pestaña Coaching; debrief | Configuración del playbook (texto, PDF, plantilla), scoring con dificultad, motor de diagnóstico, foco de coaching. Criterio de salida: ≥ 80 % de acuerdo entre IA y manager en 20 llamadas (MASTER_PLAN C1) | F2 |
| **F4 · Pipeline + reporting** | Pestaña Pipeline, email semanal y campana | Riesgo explicable, foto diaria y Movimiento con causa, emails al comercial y al Head of Sales | F1–F3 |
| **V2** | — | Forecast y Precisión por comercial (comercial demasiado optimista o conservador), biblioteca de mejores momentos, dashboard personalizado vía chat, leaderboards | F4 |

**Por qué este orden:** F1 da valor desde el primer día con los datos que ya existen y valida el diseño con los betas. F2 y F3 añaden la capa de calidad, que es lo diferencial. El reporting va al final porque **reutiliza** exactamente la misma capa de métricas y señales.

---

## 7. Decisiones abiertas

1. **Visibilidad entre compañeros:** ¿el comercial ve solo la mediana anónima o también un ranking nominal? Propuesta: la mediana por defecto y el ranking como opción del manager.
2. **Umbral de "conversación útil":** ¿60 s? ¿Configurable por empresa?
3. **Plantilla de playbook por defecto:** ¿SPICED para AE y una checklist propia de cold call para SDR?
4. **Pipeline generado por SDR:** ¿se atribuye por el creador de la reunión, por un campo "SDR" del deal o por la reunión detectada por Vocify?
5. **Objetivos:** ¿se editan en línea en el dashboard, como en MdV, o en Settings?
