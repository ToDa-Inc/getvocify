# Plan · Dashboard Head of Sales + Proceso de venta + Coaching

> Fecha: 2026-09-28 (v2). Referencia de diseño: *Motor de Ventas OS* (motordeventas-os.vercel.app), analizada a partir de capturas de Inicio, Deals, Actividad comercial y Forecast.
> Este documento es el **plan**: qué se construye, en qué orden y con qué datos. Cada fase tendrá después su propio `spec.md` según `_TEMPLATE/`.

---

## 0. La idea en una frase

**Motor de Ventas te dice QUÉ está pasando en tu equipo, sacándolo de lo que el CRM registra. Vocify te dice POR QUÉ, sacándolo de lo que se dijo en cada interacción. Y como Vocify conoce el proceso de venta, también te dice si el fallo está en la persona o en el proceso.**

Cuando las ventas no van bien, hay dos causas posibles, y Vocify tiene que distinguirlas:

| | El resultado es bueno | El resultado es malo |
|---|---|---|
| **Sigue el playbook** | ✅ El playbook funciona: se refuerza | 🔧 **El problema es el playbook.** Feedback al Head of Sales para corregirlo (§5.2) |
| **No sigue el playbook** | 💡 El comercial ha encontrado algo mejor: **candidato a mejorar el playbook** | 🎯 **El problema es el comercial.** Coaching (§6) |

Todo el producto gira alrededor de esta matriz. Motor de Ventas solo ve la columna del resultado; Vocify ve también la fila.

---

## 1. Principios

1. **Poca información, mucha claridad.** El Head of Sales no necesita cincuenta métricas; necesita saber si va bien, por qué, y si el problema está en las personas o en el proceso. Cada pantalla responde **una pregunta**, se abre con **un máximo de 4 números** y el resto aparece solo al pedirlo (progressive disclosure, §7.1 de la planificación).
2. **El Head of Sales no tiene tareas; tiene visibilidad.** Las anomalías aparecen como *señales* con su evidencia, no como pendientes.
3. **Cada número dice a qué período responde** (copiado de Motor de Ventas), con **un solo filtro de tiempo global** en lugar de un selector por bloque.
4. **Dos ejes de fecha para las reuniones** (copiado): agendadas por la fecha en que se agendaron, realizadas por la fecha en que se celebraron.
5. **Estados vacíos que explican.** Nunca "0,0 %" con 0 de 0, sino "—" y el motivo. Y **nunca una conclusión sin muestra suficiente**: si no hay datos para afirmar algo, se dice ("faltan 18 llamadas para poder evaluar este paso").
6. **Todo número de calidad enlaza a su evidencia**: la llamada y el minuto exactos.
7. **El proceso de venta es la fuente de verdad.** Scoring, coaching, diagnóstico y feedback se miden contra lo que el Head of Sales ha definido en §4. Sin proceso definido no hay calidad que medir; por eso configurarlo es parte del onboarding.
8. **No competimos con los reportes de HubSpot** (§1.5). Revenue y forecast aparecen como mucho como contexto.

---

## 2. Navegación: cuatro pestañas para el Head of Sales y una para el comercial

| Pestaña | Pregunta | Quién la ve |
|---|---|---|
| **Resumen** | ¿Cómo va el equipo y dónde está el problema? | Head of Sales |
| **Equipo** | ¿Cómo va cada persona y qué necesita? | Head of Sales |
| **Proceso de venta** | ¿Cuál es mi proceso, y está funcionando? | Head of Sales (edita); el comercial ve su playbook en modo lectura |
| **Ajustes** | Equipo, permisos, objetivos, integraciones, notificaciones | Head of Sales / Owner |
| **Mi coaching** | ¿Cómo lo estoy haciendo y qué mejoro? | Cada comercial, solo lo suyo |

Respecto a la v1 del plan, **Pipeline** y **Mercado** dejan de ser pestañas:
- Objeciones, competidores y motivos de pérdida pasan a **Proceso de venta → Salud**, porque en realidad son feedback sobre el playbook.
- El pipeline en riesgo y el movimiento de deals se resumen en el email semanal. La pestaña completa se deja para V2.

---

## 3. Resumen y Equipo (lo mínimo)

### 3.1 Resumen

- **Filtros:** período y rol (SDR / AE). Arriba a la derecha, "Actualizado hh:mm" con botón de refrescar.
- **Cuatro números**, cada uno frente al período anterior:

  | SDR | AE |
  |---|---|
  | Reuniones realizadas | Revenue cerrado frente a objetivo |
  | Conversión conectada → reunión | Win rate |
  | **Adherencia al proceso** | **Adherencia al proceso** |
  | Pipeline generado € | Ciclo medio (días) |

- **Una frase de diagnóstico**, construida con reglas a partir de la matriz del §0. Ejemplos:
  - "Los SDR siguen el proceso (adherencia 78 %), pero la conversión a reunión ha bajado: revisa el pitch del playbook de cold call." → enlaza a Proceso de venta → Salud.
  - "La conversión cae en 2 de 5 AE que no están haciendo discovery completo." → enlaza a Equipo.
- **Funnel del rol seleccionado**, una sola visualización (como la de MdV) con las etapas del proceso definidas en §4.

Nada más en esta pantalla.

### 3.2 Equipo

La tabla "Actividad del equipo" de MdV, con **5 columnas por defecto**. El resto están disponibles en "Columnas" (copiado), junto con fila de total y mediana y exportación a CSV.

| Por defecto (SDR) | Por defecto (AE) |
|---|---|
| Llamadas | Reuniones realizadas |
| % de conexión | Win rate |
| Reuniones agendadas | Revenue frente a objetivo |
| Adherencia | Adherencia |
| **Foco** (el cuello de botella, §6.3) | **Foco** |

**Columnas opcionales:** resultado de las llamadas desglosado, conversaciones útiles, realizadas / no-show, pipeline generado, score, objeciones superadas, ciclo, ticket medio, discovery completo %, siguiente paso acordado %.

Al hacer clic en una fila se abre la **ficha de la persona**, que sirve para preparar el 1:1: su funnel frente a la mediana, la adherencia por paso del proceso, su foco de coaching con clips y su evolución de 8 semanas.

**Definición y fuente de cada métrica**

| Métrica | Definición | Fuente | Fase |
|---|---|---|---|
| Llamadas / resultado / % de conexión | `outbound_calls` y memos `hubspot_call`; conexión = `connected` ÷ total | ✅ existe (`call_disposition`, `screening_outcome`) | F1 |
| Conversaciones útiles | Conectadas con duración ≥ umbral de Ajustes | ✅ `recording_duration` | F1 |
| Reuniones agendadas `(?)` | Detectadas por IA en la llamada, con fecha y hora (§5 de la planificación) | ❌ clasificador | F2 |
| Realizadas / no-show `(?)` | Reuniones de HubSpot, por fecha de celebración | ❌ sincronización de HubSpot | F2 |
| Pipeline generado, revenue, win rate, ciclo | Deals de HubSpot, con la atribución configurada en Ajustes | ❌ sincronización de HubSpot | F2 |
| Adherencia, score, objeciones superadas | Contra el proceso de §4 | ❌ scoring | F3 |

---

## 4. Proceso de venta (definido por el Head of Sales)

Aquí el Head of Sales escribe **cómo se vende en su empresa**. Es la base de todo lo demás.

### 4.1 Estructura

```
PROCESO SDR                                    PROCESO AE
┌──────────────┐   ┌────────────────┐  handoff  ┌───────────┐  ┌──────┐  ┌───────────┐  ┌────────┐
│ Cold call    │ → │ Cualificación  │ ───────→  │ Discovery │→ │ Demo │→ │ Propuesta │→ │ Cierre │
│ (playbook)   │   │ (playbook)     │ criterios │ (playbook)│  │ (pb) │  │ (pb)      │  │ (pb)   │
└──────────────┘   └────────────────┘           └───────────┘  └──────┘  └───────────┘  └────────┘
```

- **Un proceso por puesto** (SDR y AE), formado por **etapas**. Cada etapa se mapea a las etapas de su pipeline de HubSpot, en Ajustes → Integraciones.
- **Criterios de handoff SDR → AE:** qué tiene que cumplir una reunión para contar como cualificada (p. ej. decisor presente, pain confirmado, fecha y hora cerradas). Es lo que permite medir la calidad de las reuniones que genera cada SDR.
- **Un playbook por tipo de interacción** (§4.2 de la planificación), con:
  1. **Pasos**: checklist ordenada, p. ej. apertura → motivo de la llamada → pregunta de cualificación → pitch → cierre de la cita. Cada paso tiene su nombre, lo que significa "hecho bien" y si es obligatorio u opcional.
  2. **Objeciones esperadas**, con la respuesta recomendada para cada una.
  3. **Criterio de "buena llamada"** (§4.4): lo que el Head of Sales considera un éxito en esa interacción.
  4. **Competidores**, con el posicionamiento frente a cada uno.
- **Formas de crearlo** (§4.3), todas self-serve: escribirlo, subir un PDF, grabar un audio explicándolo o partir de una plantilla (cold call estándar, SPICED, BANT, MEDDIC). Vocify lo convierte en esta estructura y el Head of Sales la revisa y edita.
- **Versionado:** cada cambio crea una versión nueva (v1, v2…) con fecha. Es imprescindible para medir si un cambio mejoró los resultados (§5.3).
- El comercial ve su playbook en **modo lectura**: es su guion.

---

## 5. Salud del proceso (feedback al Head of Sales sobre su playbook)

Es la segunda causa de que las ventas no vayan bien: **el equipo hace lo que dice el playbook y aun así no funciona.** Esta sección está dentro de la pestaña Proceso de venta, al lado del playbook al que se refiere.

### 5.1 Vista para el Head of Sales (sencilla)

Para cada playbook se muestra:

- **Un estado:** 🟢 funciona · 🟡 revisar · 🔴 no funciona · ⚪ datos insuficientes.
- **La matriz del §0** con sus cuatro porcentajes. Ejemplo: "72 % de las llamadas siguen el playbook; de esas, solo el 8 % acaban en reunión, frente al 14 % de las que no lo siguen." Esta frase ya dice que el problema es el playbook.
- **Como mucho 3 recomendaciones** en lenguaje claro, cada una con su evidencia (clips y números) y tres botones: **Aplicar al playbook** · Editar · Descartar. Ejemplos:
  - "El paso *'Presentar la empresa'* no cambia el resultado y alarga la llamada 40 s de media. Propuesta: quitarlo o acortarlo."
  - "La objeción *'ya trabajamos con X'* aparece en el 23 % de las llamadas y no está en el playbook. Así la rebate Toni con un 45 % de éxito: [clip]. ¿La añadimos?"
  - "La respuesta recomendada a *'envíame info'* funciona el 11 % de las veces. Los comerciales que proponen fecha directamente consiguen el 31 %."
  - "El 40 % de las reuniones que agendan los SDR no pasan de discovery porque falta el decisor. Propuesta: añadir 'decisor presente' a los criterios de handoff."

### 5.2 Análisis técnico (una capa más, desplegable)

Para quien quiera entrar al detalle, por playbook:

| Análisis | Qué mide | Qué detecta |
|---|---|---|
| **Impacto de cada paso** | Conversión cuando el paso se hace frente a cuando no se hace, con tamaño de muestra | Pasos que no aportan o que restan; pasos clave que se saltan |
| **Orden y momento** | En qué minuto se hace cada paso y si el orden importa | "Hablar de precio antes del minuto 2 reduce la conversión" |
| **Objeciones** | Frecuencia, % de éxito de la respuesta del playbook frente a respuestas alternativas | Objeciones no cubiertas y respuestas que no funcionan |
| **Competidores** | Menciones, en qué etapa aparecen y win rate cuando aparecen | Posicionamiento que falla frente a un competidor concreto |
| **Motivos de pérdida** | `lost_reason` y contexto de la llamada, agrupados | Patrones que el proceso no está resolviendo |
| **Handoff SDR → AE** | Reuniones "cualificadas" por el SDR que el AE no consigue avanzar | Criterios de cualificación mal definidos |
| **Desviaciones ganadoras** | Llamadas que no siguen el playbook y aun así consiguen el resultado (cuadrante 💡) | Buenas prácticas que el playbook todavía no recoge |
| **Etapa donde se rompe** | Conversión etapa a etapa del proceso, con adherencia alta | Qué etapa del proceso es la que falla |

**Regla de honestidad:** ninguna recomendación se muestra sin una muestra mínima (p. ej. ≥ 30 interacciones por grupo comparado, configurable). Las recomendaciones salen de comparaciones calculadas con reglas; el LLM **solo redacta** la frase y elige los clips, no decide la conclusión.

### 5.3 Ciclo de mejora del playbook

```
Datos de interacciones → Recomendación → Head of Sales aplica o edita → Playbook v(n+1)
        ↑                                                                    │
        └──────── Antes / después: ¿v(n+1) convierte mejor que v(n)? ←───────┘
```

Cada versión del playbook muestra su comparación con la anterior (adherencia y conversión), para que el Head of Sales vea el efecto de sus cambios.

---

## 6. Coaching del comercial (la primera causa: no se sigue el playbook)

### 6.1 Ciclo

Proceso (§4) → **cada interacción se puntúa** contra su playbook → **debrief** al comercial (lo que hizo bien, **una** cosa a mejorar con el minuto exacto, y cómo lo hace el mejor del equipo) → **resumen semanal** → **1:1** con la ficha de la persona → se mide si el foco de la semana pasada mejoró.

### 6.2 Puntuación de cada interacción (background job, clasificación acotada estilo Jev.ai)

- Cada paso del playbook: hecho o no hecho, con marca de tiempo.
- Cada objeción: tipo, si es *objeción* u *obstáculo*, y si se superó.
- Flag de **dificultad** (§4.4), para que una llamada fácil no puntúe más que una batallada.
- **Adherencia** = pasos cumplidos ÷ pasos obligatorios. **Score** = adherencia + gestión de objeciones, ajustado por dificultad.

### 6.3 Motor de diagnóstico: un solo foco por persona y semana

Compara el funnel del comercial con **la mediana de su puesto**, elige el cuello de botella y lo cruza con su adherencia en el paso del playbook correspondiente:
- **Adherencia baja en ese paso** → coaching al comercial.
- **Adherencia alta en ese paso** → el problema no es la persona, y la señal se suma a la Salud del proceso (§5).

| Puesto | Síntoma frente a la mediana | Foco |
|---|---|---|
| SDR | Conexión baja con volumen normal | Listas u horario (no es técnica) |
| SDR | Conecta pero corta rápido | Apertura |
| SDR | Conversa pero agenda poco | Pitch y la objeción que más pierde |
| SDR | Agenda pero muchos no-show o reuniones no cualificadas | Cierre de la cita y criterios de handoff |
| AE | Reuniones que no avanzan | Discovery (pain, decisor, presupuesto, timing) |
| AE | Deals sin siguiente paso | Cerrar cada reunión con un siguiente paso fechado |
| AE | Pierde en la etapa final o frente a un competidor | La objeción final o el posicionamiento |

### 6.4 Pestaña "Mi coaching" (SDR y AE ven la misma estructura con sus propias métricas)

- **Mi semana:** 3 números frente a mi semana anterior y la mediana anónima del equipo.
- **Mi foco:** una frase, 2–3 clips propios y 1 clip de referencia del equipo.
- **Mi adherencia por paso:** barras con la evolución de 8 semanas.
- **Mis interacciones:** lista con score, que abre el debrief de cada una.
- **Mi playbook:** en modo lectura.

---

## 7. Reporting al Head of Sales (email semanal, lunes)

Mismo orden que el Resumen, y breve:
1. Los 4 números frente a la semana anterior y la frase de diagnóstico.
2. **Personas:** una línea por comercial con su resultado, su foco y si mejoró el de la semana pasada.
3. **Proceso:** el estado de cada playbook y como mucho 1–2 recomendaciones nuevas, con enlace para aplicarlas.
4. **Deals:** los que se han movido o están en riesgo, con la causa sacada de la llamada.

A esto se suma la campana en el dashboard (§8 de la planificación) y un informe mensual para reportar hacia arriba (evolución de adherencia y conversión).

---

## 8. Ajustes (el Head of Sales configura todo)

Se amplía el `SettingsLayout` actual (`calling`, `offer`, `glossary`, `team`, `integrations`, `usage`, `billing`).

| Sección | Qué contiene | Estado |
|---|---|---|
| **Equipo** | Invitar, desactivar y transferir miembros (ya existe). **Nuevo:** puesto de cada persona (SDR / AE / Head of Sales / otro), manager o equipo al que pertenece, relación con su owner de HubSpot (con aviso de los que no tienen owner vinculado, que es lo que provoca el "Otros" de MdV) y fecha de alta (para no comparar a un junior de 2 semanas con la mediana) | Ampliar `TeamPage` |
| **Permisos** | Matriz de roles (tabla más abajo) | Nuevo |
| **Proceso de venta** | Acceso directo a la pestaña §4 | Nuevo |
| **Objetivos** | Por puesto y por persona, mensuales: reuniones, pipeline generado, revenue, llamadas | Nuevo |
| **Métricas** | Umbral de conversación útil (60 s por defecto), días y horas laborables, atribución del pipeline generado de los SDR (creador de la reunión, campo del deal o reunión detectada por Vocify), muestra mínima para las recomendaciones del §5 | Nuevo |
| **Coaching** | Qué ve el comercial de sus compañeros (solo la mediana anónima o también un ranking con nombres), frecuencia del debrief, número de focos por semana (1 por defecto), si se comparten clips del equipo | Nuevo |
| **Reportes y notificaciones** | Quién recibe qué email (Head of Sales, comercial), día y hora de envío, campana | Nuevo |
| **Integraciones** | CRM (ya existe). **Nuevo:** qué pipeline usar y el mapeo de sus etapas a las del proceso de §4 | Ampliar |
| **Oferta y glosario** | Ya existen; alimentan los playbooks | Existe |
| **Llamadas, uso, facturación** | Ya existen | Existe |
| **Datos y privacidad** | Aviso de grabación, retención de audios, quién puede escuchar grabaciones | Nuevo |

**Matriz de permisos**

Hoy `company_members.role` tiene `owner / admin / member`, que son **permisos**. El **puesto** (SDR / AE) es un campo aparte (`sales_role`), porque una misma persona puede ser admin y AE a la vez.

| Permiso | Owner | Admin (Head of Sales) | Team lead (V2) | Miembro (SDR / AE) |
|---|---|---|---|---|
| Facturación y plan | ✅ | — | — | — |
| Invitar y editar equipo, puestos y objetivos | ✅ | ✅ | — | — |
| Editar proceso y playbooks | ✅ | ✅ | proponer | ver |
| Ver Resumen, Equipo y Salud del proceso | ✅ | ✅ | su equipo | — |
| Escuchar grabaciones del equipo | ✅ | ✅ | su equipo | solo las suyas y los clips compartidos |
| Mi coaching | — | opcional | ✅ | ✅ |

---

## 9. Datos

- **Capa de métricas única** (`/api/team/metrics`, más vistas o funciones SQL en Supabase): una definición por métrica, compartida por el dashboard, los emails y el coaching.
- **Sincronización diaria de HubSpot hacia Supabase**: deals, reuniones y owners, más una foto diaria de los deals para detectar movimientos.
- **Tablas nuevas (orientativo):**
  - `sales_processes` y `process_stages`: proceso por puesto y mapeo a las etapas del CRM.
  - `playbooks` y `playbook_versions`: pasos, objeciones, criterios y competidores.
  - `interaction_scores`: por memo, con la versión del playbook aplicada.
  - `interaction_steps` e `interaction_objections`.
  - `playbook_recommendations`: estado propuesta / aplicada / descartada, más su evidencia.
  - `coaching_focus`.
  - `targets`.
  - `crm_deal_snapshots`.
- **Campo nuevo:** `company_members.sales_role` y `team_id`.
- **Ya existe:** llamadas con su disposición y duración, `screening_outcome`, resultado converted / on hold / lost con motivo (migración 021), y en `MemoExtraction` objeciones, competidores, pains, siguientes pasos y decisores en texto libre.

---

## 10. Fases (una a la vez, cada una verificable antes de empezar la siguiente)

| Fase | Entregable | Contenido |
|---|---|---|
| **F0 · Ajustes base** | Ajustes → Equipo con puestos, Permisos, Objetivos y Métricas | `sales_role`, matriz de permisos, capa de métricas, sincronización de HubSpot y mapeo de etapas |
| **F1 · Proceso de venta + Resumen/Equipo de actividad** | El Head of Sales define su proceso y ve la actividad de su equipo | Editor de proceso y playbooks (texto, PDF, audio, plantillas) con versionado; Resumen y Equipo con los datos que ya existen |
| **F2 · Clasificadores** | Reuniones, objeciones y resultados de HubSpot en el dashboard | Reunión agendada con fecha y hora, taxonomía de objeciones, competidores normalizados, realizadas / no-show, pipeline generado |
| **F3 · Scoring + Mi coaching** | Adherencia y foco en la tabla; pestaña del comercial con debrief | Puntuación contra el playbook, dificultad, motor de diagnóstico. Criterio de salida: ≥ 80 % de acuerdo entre IA y manager en 20 llamadas |
| **F4 · Salud del proceso + reporting** | Estado de cada playbook, recomendaciones aplicables, email semanal | Análisis del §5.2 con muestra mínima, ciclo de mejora y comparación entre versiones, emails y campana |
| **V2** | — | Team leads, pestaña Pipeline y forecast con precisión, biblioteca de mejores momentos, dashboard personalizable vía chat |

**Por qué este orden:** el proceso de venta tiene que existir **antes** que el scoring (F3), porque el scoring mide contra él. La Salud del proceso (F4) va al final porque necesita volumen de interacciones puntuadas para no sacar conclusiones con muestras pequeñas.

---

## 11. Decisiones abiertas

1. **Visibilidad entre compañeros:** ¿solo la mediana anónima (propuesta por defecto) o también un ranking con nombres?
2. **Conversación útil:** ¿60 s?
3. **Plantillas iniciales:** ¿cold call propia para SDR y SPICED para AE?
4. **Atribución del pipeline de los SDR:** ¿por el creador de la reunión, por un campo "SDR" del deal o por la reunión detectada por Vocify?
5. **Team leads** (un nivel entre Head of Sales y comercial): ¿hace falta en V1 para los betas o se deja para V2?
6. **Muestra mínima para las recomendaciones:** ¿30 interacciones por grupo comparado?
