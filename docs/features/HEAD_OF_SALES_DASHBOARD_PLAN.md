# Plan · Dashboard del Head of Sales

> Fecha: 2026-09-28. Referencia de diseño: *Motor de Ventas OS* (motordeventas-os.vercel.app), analizada a partir de capturas de Inicio, Deals, Actividad comercial y Forecast.
> Plan hermano: [`COACHING_PLAN.md`](./COACHING_PLAN.md), que cubre el coaching dentro de los dashboards de SDR y AE. Este documento es el **plan**; cada fase tendrá después su `spec.md` según `_TEMPLATE/`.

---

## 0. La idea

**Motor de Ventas te dice QUÉ está pasando en tu equipo, sacándolo de lo que el CRM registra. Vocify te dice POR QUÉ, sacándolo de lo que se dijo en cada interacción. Y como Vocify conoce el proceso de venta, también te dice si el fallo está en la persona o en el proceso.**

Cuando las ventas no van bien, hay dos causas, y el dashboard tiene que distinguirlas:

| | El resultado es bueno | El resultado es malo |
|---|---|---|
| **Sigue el playbook** | ✅ El playbook funciona | 🔧 **El problema es el playbook.** Feedback al Head of Sales (§5) |
| **No sigue el playbook** | 💡 El comercial ha encontrado algo mejor: candidato a mejorar el playbook (§5) | 🎯 **El problema es el comercial.** Coaching (plan de coaching) |

**Qué cubre este plan:** Resumen, Equipo, Proceso de venta (definición y salud del playbook), Ajustes y reporting al Head of Sales.
**Qué NO cubre:** la puntuación de cada interacción, el diagnóstico por comercial y lo que ve el propio comercial. Todo eso está en `COACHING_PLAN.md`, y este dashboard **consume** sus resultados (§9).

---

## 1. Principios

1. **Poca información, mucha claridad.** Cada pantalla responde **una pregunta**, se abre con **un máximo de 4 números** y el resto aparece solo al pedirlo (progressive disclosure, §7.1 de la planificación).
2. **El Head of Sales no tiene tareas; tiene visibilidad.** Las anomalías aparecen como *señales* con su evidencia, no como pendientes.
3. **Cada número dice a qué período responde** (copiado de Motor de Ventas), con **un solo filtro de tiempo global** en lugar de un selector por bloque.
4. **Dos ejes de fecha para las reuniones** (copiado): agendadas por la fecha en que se agendaron, realizadas por la fecha en que se celebraron.
5. **Estados vacíos que explican.** Nunca "0,0 %" con 0 de 0, sino "—" y el motivo. **Nunca una conclusión sin muestra suficiente.**
6. **Todo número de calidad enlaza a su evidencia**: la llamada y el minuto exactos.
7. **El proceso de venta es la fuente de verdad.** El scoring, el coaching y el feedback se miden contra lo que el Head of Sales ha definido en §4. Por eso configurarlo forma parte del onboarding.
8. **No competimos con los reportes de HubSpot** (§1.5). Revenue y forecast aparecen solo como contexto.

---

## 2. Navegación: cuatro pestañas

| Pestaña | Pregunta que responde |
|---|---|
| **Resumen** | ¿Cómo va el equipo y dónde está el problema? |
| **Equipo** | ¿Cómo va cada persona y qué necesita? |
| **Proceso de venta** | ¿Cuál es mi proceso, y está funcionando? |
| **Ajustes** | Equipo, permisos, objetivos, integraciones, notificaciones |

Lo que en otros dashboards serían pestañas propias se reubica:
- Objeciones, competidores y motivos de pérdida van dentro de *Proceso de venta → Salud*.
- El pipeline en riesgo va en el email semanal. La pestaña Pipeline completa, con forecast, queda para V2.

---

## 3. Resumen y Equipo

### 3.1 Resumen

- **Filtros:** período y puesto (SDR / AE). Arriba a la derecha, "Actualizado hh:mm" con botón de refrescar.
- **Cuatro números**, cada uno frente al período anterior:

  | SDR | AE |
  |---|---|
  | Reuniones realizadas | Revenue cerrado frente a objetivo |
  | Conversión conectada → reunión | Win rate |
  | Adherencia al proceso | Adherencia al proceso |
  | Pipeline generado € | Ciclo medio (días) |

- **Una frase de diagnóstico**, calculada con reglas a partir de la matriz del §0. Ejemplo: "Los SDR siguen el proceso (78 %), pero la conversión a reunión ha bajado: revisa el pitch del playbook de cold call." → enlaza a *Proceso de venta → Salud* o a *Equipo*, según el cuadrante.
- **Funnel** del puesto seleccionado, con las etapas del proceso del §4 (una visualización como la de MdV).

Nada más en esta pantalla.

### 3.2 Equipo

La tabla "Actividad del equipo" de MdV, con **5 columnas por defecto**. El resto están en "Columnas" (copiado), junto con fila de **total** y **mediana** y exportación a CSV.

| Por defecto (SDR) | Por defecto (AE) |
|---|---|
| Llamadas | Reuniones realizadas |
| % de conexión | Win rate |
| Reuniones agendadas | Revenue frente a objetivo |
| Adherencia *(plan de coaching)* | Adherencia *(plan de coaching)* |
| Foco *(plan de coaching)* | Foco *(plan de coaching)* |

**Columnas opcionales:** resultado de las llamadas desglosado, conversaciones útiles, realizadas / no-show, pipeline generado, score, objeciones superadas, ciclo, ticket medio, discovery completo %, siguiente paso acordado %.

Al hacer clic en una fila se abre la **ficha de la persona**, pensada para preparar el 1:1: su funnel frente a la mediana, la adherencia por paso del proceso, su foco de coaching con clips y su evolución de 8 semanas. Los datos de calidad los aporta el plan de coaching.

**Definición y fuente de cada métrica**

| Métrica | Definición | Fuente | Fase |
|---|---|---|---|
| Llamadas / resultado / % de conexión | `outbound_calls` y memos `hubspot_call`; conexión = `connected` ÷ total | ✅ `call_disposition`, `screening_outcome` | H1 |
| Conversaciones útiles | Conectadas con duración ≥ umbral de Ajustes | ✅ `recording_duration` | H1 |
| Reuniones agendadas `(?)` | Detectadas por IA en la llamada, con fecha y hora (§5 de la planificación), por fecha de agendado | ❌ clasificador | H2 |
| Realizadas / no-show `(?)` | Reuniones de HubSpot, por fecha de celebración | ❌ sincronización de HubSpot | H2 |
| Pipeline generado, revenue, win rate, ciclo | Deals de HubSpot, con la atribución configurada en Ajustes | ❌ sincronización de HubSpot | H2 |
| Adherencia, score, foco, objeciones superadas | Contra el proceso del §4 | ❌ plan de coaching | H3 |

---

## 4. Proceso de venta (lo define el Head of Sales)

### 4.1 Estructura

```
PROCESO SDR                                  PROCESO AE
┌────────────┐   ┌───────────────┐  handoff  ┌───────────┐  ┌──────┐  ┌───────────┐  ┌────────┐
│ Cold call  │ → │ Cualificación │ ───────→  │ Discovery │→ │ Demo │→ │ Propuesta │→ │ Cierre │
│ (playbook) │   │ (playbook)    │ criterios │ (playbook)│  │ (pb) │  │ (pb)      │  │ (pb)   │
└────────────┘   └───────────────┘           └───────────┘  └──────┘  └───────────┘  └────────┘
```

- **Un proceso por puesto** (SDR y AE), formado por **etapas**. Cada etapa se mapea a su etapa del pipeline de HubSpot (Ajustes → Integraciones).
- **Criterios de handoff SDR → AE:** qué tiene que cumplir una reunión para contar como cualificada (p. ej. decisor presente, pain confirmado, fecha y hora cerradas).
- **Un playbook por tipo de interacción** (§4.2 de la planificación), con:
  1. **Pasos**: checklist ordenada. Cada paso tiene nombre, qué significa "hecho bien" y si es obligatorio u opcional.
  2. **Objeciones esperadas**, con la respuesta recomendada.
  3. **Criterio de "buena llamada"** (§4.4).
  4. **Competidores**, con el posicionamiento frente a cada uno.
- **Formas de crearlo** (§4.3), todas self-serve: escribirlo, subir un PDF, grabar un audio o partir de una plantilla (cold call estándar, SPICED, BANT, MEDDIC). Vocify lo convierte en esta estructura y el Head of Sales la revisa.
- **Versionado:** cada cambio crea una versión nueva (v1, v2…) con fecha, para poder medir si el cambio mejoró los resultados (§5.3).
- **Este plan es el dueño del proceso**, y el plan de coaching lo lee: puntúa cada interacción contra él y se lo enseña al comercial en modo lectura.

---

## 5. Salud del proceso (feedback al Head of Sales sobre su playbook)

Cubre la segunda causa: **el equipo hace lo que dice el playbook y aun así no funciona.** Está dentro de *Proceso de venta*, al lado del playbook al que se refiere.

### 5.1 Vista sencilla

Para cada playbook se muestra:

- **Un estado:** 🟢 funciona · 🟡 revisar · 🔴 no funciona · ⚪ datos insuficientes.
- **La matriz del §0 con sus porcentajes.** Ejemplo: "72 % de las llamadas siguen el playbook; de esas, solo el 8 % acaban en reunión, frente al 14 % de las que no lo siguen." Esa frase ya dice que el problema es el playbook.
- **Como mucho 3 recomendaciones**, cada una con su evidencia (números y clips) y tres botones: **Aplicar al playbook** · Editar · Descartar. Ejemplos:
  - "El paso *'Presentar la empresa'* no cambia el resultado y alarga la llamada 40 s. Propuesta: quitarlo o acortarlo."
  - "La objeción *'ya trabajamos con X'* aparece en el 23 % de las llamadas y no está en el playbook. Así la rebate Toni con un 45 % de éxito: [clip]. ¿La añadimos?"
  - "La respuesta recomendada a *'envíame info'* funciona el 11 % de las veces. Proponer fecha directamente funciona el 31 %."
  - "El 40 % de las reuniones de los SDR no pasan de discovery porque falta el decisor. Propuesta: añadir 'decisor presente' a los criterios de handoff."

### 5.2 Análisis técnico (una capa más, desplegable)

| Análisis | Qué mide | Qué detecta |
|---|---|---|
| **Impacto de cada paso** | Conversión cuando el paso se hace frente a cuando no se hace, con tamaño de muestra | Pasos que no aportan o que restan; pasos clave que se saltan |
| **Orden y momento** | En qué minuto se hace cada paso y si el orden importa | "Hablar de precio antes del minuto 2 reduce la conversión" |
| **Objeciones** | Frecuencia, y % de éxito de la respuesta del playbook frente a las alternativas | Objeciones no cubiertas y respuestas que no funcionan |
| **Competidores** | Menciones, etapa en la que aparecen y win rate cuando aparecen | Posicionamiento que falla |
| **Motivos de pérdida** | `lost_reason` más el contexto de la llamada, agrupados | Patrones que el proceso no resuelve |
| **Handoff SDR → AE** | Reuniones "cualificadas" que el AE no consigue avanzar | Criterios de cualificación mal definidos |
| **Desviaciones ganadoras** | Cuadrante 💡: no siguen el playbook y aun así consiguen el resultado | Buenas prácticas que el playbook no recoge |
| **Etapa donde se rompe** | Conversión etapa a etapa con adherencia alta | Qué parte del proceso falla |

**Regla de honestidad:** no se muestra ninguna recomendación sin una muestra mínima (≥ 30 interacciones por grupo comparado, configurable). Las conclusiones se calculan con reglas; el LLM **solo redacta** la frase y elige los clips.

### 5.3 Ciclo de mejora

```
Interacciones puntuadas → Recomendación → Head of Sales aplica o edita → Playbook v(n+1)
          ↑                                                                   │
          └──────── Antes / después: ¿v(n+1) convierte mejor que v(n)? ←──────┘
```

---

## 6. Reporting al Head of Sales

- **Email semanal** (lunes, vía Resend), en el mismo orden que el Resumen:
  1. Los 4 números frente a la semana anterior y la frase de diagnóstico.
  2. **Personas:** una línea por comercial con su resultado, su foco y si mejoró el de la semana pasada (datos del plan de coaching).
  3. **Proceso:** el estado de cada playbook y 1–2 recomendaciones nuevas, con enlace para aplicarlas.
  4. **Deals:** los que se han movido o están en riesgo, con la causa sacada de la llamada.
- **Campana** en el dashboard con las mismas señales (§8 de la planificación).
- **Informe mensual para reportar hacia arriba:** evolución de la adherencia y de la conversión del equipo.

---

## 7. Ajustes (el Head of Sales configura todo)

Se amplía el `SettingsLayout` actual (`calling`, `offer`, `glossary`, `team`, `integrations`, `usage`, `billing`).

| Sección | Qué contiene | Estado |
|---|---|---|
| **Equipo** | Invitar, desactivar y transferir miembros (ya existe). **Nuevo:** puesto de cada persona (SDR / AE / Head of Sales / otro), su manager o equipo, su owner de HubSpot (con aviso de los que no están vinculados, que es lo que provoca el "Otros" de MdV) y fecha de alta (para no comparar a alguien que lleva 2 semanas con la mediana) | Ampliar `TeamPage` |
| **Permisos** | Matriz de roles (tabla más abajo) | Nuevo |
| **Proceso de venta** | Acceso directo al §4 | Nuevo |
| **Objetivos** | Mensuales, por puesto y por persona: reuniones, pipeline generado, revenue, llamadas | Nuevo |
| **Métricas** | Umbral de conversación útil (60 s por defecto), días y horas laborables, atribución del pipeline de los SDR, muestra mínima para las recomendaciones | Nuevo |
| **Coaching** | Qué ve cada comercial de sus compañeros (mediana anónima o ranking con nombres), frecuencia del debrief, focos por semana, si se comparten clips del equipo. Estas opciones las usa el plan de coaching | Nuevo |
| **Reportes y notificaciones** | Quién recibe qué email, día y hora de envío, campana | Nuevo |
| **Integraciones** | CRM (ya existe). **Nuevo:** qué pipeline usar y el mapeo de sus etapas a las del proceso | Ampliar |
| **Oferta y glosario** | Ya existen; alimentan los playbooks | Existe |
| **Llamadas, uso, facturación** | Ya existen | Existe |
| **Datos y privacidad** | Aviso de grabación, retención de audios, quién puede escuchar qué | Nuevo |

**Matriz de permisos**

`company_members.role` (`owner / admin / member`) son **permisos**. El **puesto** es un campo aparte (`sales_role`), porque una misma persona puede ser admin y AE a la vez.

| Permiso | Owner | Admin (Head of Sales) | Team lead (V2) | Miembro (SDR / AE) |
|---|---|---|---|---|
| Facturación y plan | ✅ | — | — | — |
| Invitar y editar equipo, puestos y objetivos | ✅ | ✅ | — | — |
| Editar proceso y playbooks | ✅ | ✅ | proponer | ver |
| Ver Resumen, Equipo y Salud del proceso | ✅ | ✅ | su equipo | — |
| Escuchar grabaciones del equipo | ✅ | ✅ | su equipo | solo las suyas y los clips compartidos |

---

## 8. Datos

- **Capa de métricas única** (`/api/team/metrics`, más vistas o funciones SQL en Supabase): una sola definición por métrica, compartida por el dashboard, los emails y el plan de coaching.
- **Sincronización diaria de HubSpot hacia Supabase:** deals, reuniones y owners, más una foto diaria de los deals para detectar movimientos.
- **Tablas que son de este plan:**
  - `sales_processes` y `process_stages`: incluyen el mapeo a las etapas del CRM.
  - `playbooks` y `playbook_versions`.
  - `playbook_recommendations`: estado propuesta / aplicada / descartada, con su evidencia.
  - `targets`.
  - `crm_deal_snapshots`.
  - Campos nuevos `company_members.sales_role` y `team_id`.
- **Ya existe:** llamadas con disposición y duración, `screening_outcome`, resultado converted / on hold / lost con motivo (migración 021), y en `MemoExtraction` objeciones, competidores, pains, siguientes pasos y decisores en texto libre.

---

## 9. Contrato con el plan de coaching

| Este plan **da** al de coaching | Este plan **recibe** del de coaching |
|---|---|
| `sales_role` de cada persona | `interaction_scores`: score, adherencia, dificultad y versión del playbook, por interacción |
| Procesos y playbooks versionados | `interaction_steps` e `interaction_objections` |
| Ajustes de coaching y umbrales | `coaching_focus`: foco semanal por persona |
| Capa de métricas y medianas por puesto | |

Mientras el plan de coaching no esté listo, las columnas Adherencia y Foco muestran "—" con su explicación, y la Salud del proceso aparece en estado ⚪.

---

## 10. Fases (una a la vez, cada una verificable antes de la siguiente)

| Fase | Entregable | Contenido |
|---|---|---|
| **H0 · Ajustes base** | Ajustes → Equipo con puestos, Permisos, Objetivos y Métricas | `sales_role`, permisos, capa de métricas, sincronización de HubSpot y mapeo de etapas |
| **H1 · Proceso de venta + actividad** | El Head of Sales define su proceso y ve la actividad de su equipo | Editor de proceso y playbooks (texto, PDF, audio, plantillas) con versiones; Resumen y Equipo con los datos que ya existen |
| **H2 · Resultados comerciales** | Reuniones, pipeline y win rate en el dashboard | Clasificador de reunión agendada, reuniones realizadas / no-show, deals, pipeline generado con atribución |
| **H3 · Capa de calidad** | Adherencia, score y foco en la tabla y la ficha | Consumir las salidas del plan de coaching (necesita su fase C1) |
| **H4 · Salud del proceso + reporting** | Estado de cada playbook, recomendaciones aplicables, email semanal | Análisis del §5.2 con muestra mínima, ciclo de versiones, emails y campana |
| **V2** | — | Team leads, pestaña Pipeline con forecast y precisión, dashboard personalizable vía chat |

### Estado (2026-09-28)

- ✅ **H0 (parcial):** `company_members.sales_role` + `started_on`, `companies.sales_settings` (migración 037); puesto por persona y umbral de "conversación útil" en Ajustes → Team; capa de métricas `backend/app/services/team_metrics.py` + `GET /api/v1/team/metrics`.
- ✅ **H1 (actividad):** página *Sales team* (`/dashboard/sales-team`, solo owner/admin) con Overview (3 KPIs vs periodo comparable, embudo, llamadas por semana) y Team (tabla por persona con mediana, total y CSV). Fuente: dialer de Vocify (`outbound_calls`).
- ⏳ **Pendiente de H0/H1:** matriz de permisos, objetivos, sincronización de HubSpot + mapeo de etapas, editor de proceso de venta y playbooks.

**H1 es bloqueante para el plan de coaching**, porque sin proceso no hay nada contra lo que puntuar.

---

## 11. Decisiones abiertas

1. **Atribución del pipeline de los SDR:** ¿por el creador de la reunión, por un campo "SDR" del deal o por la reunión detectada por Vocify?
2. **Conversación útil:** ¿60 s?
3. **Plantillas iniciales:** ¿cold call propia para SDR y SPICED para AE?
4. **Team leads:** ¿en V1 o en V2?
5. **Muestra mínima para las recomendaciones:** ¿30 interacciones por grupo comparado?
