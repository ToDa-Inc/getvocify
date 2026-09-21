# Plan de integración — la experiencia en web, extensión, desktop y WhatsApp

*El qué está en `docs/EXPERIENCIA_PRODUCTO.md`. Los datos, en `docs/features/ESTRUCTURA_INTELIGENTE.md`. Esto es el cómo: qué hace cada superficie, cómo se ve, cómo se conecta por detrás y en qué orden se construye. Es insumo para el proceso de 6 etapas de `MASTER_PLAN.md`: cada slice de la §4 pasa después por su propio spec y design.*

---

## 0. La tesis en cuatro líneas

1. **Un cerebro.** El backend decide qué toca, por qué y cuándo. Las superficies solo pintan lo que reciben — ninguna calcula inteligencia por su cuenta.
2. **Una columna vertebral.** Cinco piezas que son el mismo objeto en todas partes: **Tarjeta de Hoy, Brief, Pastilla en vivo, Revisión, Seguimiento** — más la **nota del manager**, que viaja dentro de ellas.
3. **Cuatro casas.** SDR → extensión. AE → desktop. Field → WhatsApp. Manager → web. Nadie cambia de casa para usar Vocify.
4. **Un idioma visual con cuatro marcas, cada una con un solo significado.** Papel = contenido. Cristal = lo que flota o está en vivo. Filete bronce = esto viene de tu equipo. Serif en cursiva = la voz de tu manager.

---

## 1. Qué es cada superficie — y qué no

| Superficie | Casa de | Lo primero que ve | Momento estrella | Lo que NO hace |
|---|---|---|---|---|
| **Extensión** (side panel, ya existe: `manifest.json` → `side_panel`) | SDR | Hoy, en formato cola | "Empezar a llamar": la lista se convierte en cola y mueve HubSpot sola | Coaching de equipo, configuración, analítica |
| **Desktop** | AE | Próxima reunión + Hoy | La pastilla durante la reunión y el seguimiento listo al terminar | Dialer, configuración |
| **Web** | Manager (y archivo de todos) | Rep: Hoy completo. Manager: Equipo | Corregir una llamada y convertirlo en regla | Pastilla en vivo |
| **WhatsApp** | Field | El resumen de la mañana | Nota de voz → aprobado → seguimiento de vuelta | Todo lo que necesite pantalla |

### 1.1 Extensión — el bucle del SDR

Un solo bucle, sin navegar: **Hoy → Empezar → brief → Llamar → pastilla → revisión con seguimiento → Siguiente.**

La pieza que lo hace sentir mágico: al avanzar la cola, la extensión lleva la pestaña de HubSpot a la ficha del siguiente contacto (el permiso `tabs` ya está). El SDR nunca busca a nadie.

```
┌──────────────────────────────────┐   ┌──────────────────────────────────┐
│ Vocify                       Hoy │   │ ← Hoy                   2 de 7   │
├──────────────────────────────────┤   ├──────────────────────────────────┤
│ 4 llamadas hoy · 1 por revisar   │   │ Marina Ortiz                     │
│                                  │   │ Dir. de Operaciones · Tenéis     │
│ ┌──────────────────────────────┐ │   │                                  │
│ │ Marina Ortiz · Tenéis        │ │   │ Última vez · hace 12 días        │
│ │ Pidió que la llamaras en dos │ │   │ Dudó por el precio; pidió volver │
│ │ semanas. Hace 12 días.       │ │   │ a hablar en dos semanas.         │
│ │ ┃ Precio: así lo cerró Alex  │ │   │                                  │
│ │ [ Llamar ]   Posponer    ··· │ │   │ Quedó pendiente                  │
│ └──────────────────────────────┘ │   │ Enviar el caso de logística.     │
│ ┌──────────────────────────────┐ │   │                                  │
│ │ Jordi Puig · Loop Energía    │ │   │ ┃ Lo que funcionó con precio     │
│ │ Le prometiste el precio por  │ │   │ ┃ "Compáralo con el coste de un  │
│ │ email el lunes.              │ │   │ ┃ comercial más." Alex · 3 de 4  │
│ │ [ Escribir ]  Posponer   ··· │ │   │                                  │
│ └──────────────────────────────┘ │   │ ✎ Gon: pregúntale primero qué    │
│                                  │   │   pasó con el piloto.            │
│      [ Empezar a llamar → ]      │   │                                  │
└──────────────────────────────────┘   │ [       Llamar a Marina       ]  │
         Hoy (lista)                   │  Saltar                          │
                                       └──────────────────────────────────┘
                                                  Hoy (modo cola)
```

Cuando el SDR ya está en una ficha de HubSpot sin venir de la cola, el panel muestra directamente el brief de ese contacto — la cola es un atajo, no un requisito.

### 1.2 Desktop — la casa del AE, estilo Granola

La secuencia actual (Login → Permisos → Escuchando → Revisión, más pastilla y bandeja) se queda. Se añade una **home** entre Permisos y Escuchando: próxima reunión arriba (cuando haya calendario conectado; sin calendario, solo Hoy y el botón de escuchar), Hoy debajo. En la bandeja del sistema: *"Hoy: 3 pendientes"*.

**Una pastilla, dos estados** — corrijo lo que dije en `EXPERIENCIA_PRODUCTO.md`: en vez de dos ventanas flotantes, una sola pastilla que crece una fila cuando tiene algo que decir, y vuelve a su tamaño después.

```
Escuchando (casi siempre)
╭────────────────────────────────────────────────────────╮
│ ●  "…y el año pasado ya lo intentamos con…" [ Parar ]  │
╰────────────────────────────────────────────────────────╯

Con sugerencia (solo si tiene respaldo; ~10 s y se recoge)
╭────────────────────────────────────────────────────────╮
│ ●  "…ahora mismo no tenemos presupuesto…"   [ Parar ]  │
│ ┃ Precio · Pregunta qué les cuesta no hacerlo          │
│ ┃ este trimestre.                       Alex · 4 de 6  │
╰────────────────────────────────────────────────────────╯
```

**La revisión: una pantalla, una decisión — la que el sistema no puede tomar solo.**

- **Confianza alta** (contacto y deal claros): el CRM se guarda solo y aparece como una línea — *"Guardado en HubSpot · Deshacer"* — y la única acción principal es **Enviar seguimiento**. Ya existe un flag de auto-sync (`crm_configurations.auto_sync_hubspot_calls`, migración 033); se extiende por nivel de confianza.
- **Necesita a un humano** (deal ambiguo, deal nuevo, confianza baja): la acción principal pasa a ser **Confirmar en HubSpot**, y el seguimiento queda justo debajo con su propio botón.

```
┌──────────────────────────────────────────────────────────┐
│ Reunión con Marina Ortiz · 32 min                        │
│ Guardado en HubSpot · Tenéis — Expansión Q4     Deshacer │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Seguimiento para Marina           marina@tenes.io    │ │
│ │ Caso de logística y lo que hablamos                  │ │
│ │                                                      │ │
│ │ Hola Marina, gracias por el rato de hoy. Como        │ │
│ │ quedamos, te paso el caso de logística y la          │ │
│ │ propuesta para empezar con el equipo de Barcelona…   │ │
│ │                                                      │ │
│ │ [ Enviar ]    WhatsApp    Copiar                     │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ Resumen                     Próximos pasos               │
│ …                           …                            │
│ CRM · 7 campos guardados                           Ver ⌄ │
└──────────────────────────────────────────────────────────┘
```

El cuerpo del email se lee como texto, no como un formulario: se edita tocándolo.

### 1.3 Web — la casa del manager, y el archivo de todos

- **Rep:** la home deja de ser *"Welcome back — Ready to update your CRM?"* (`DashboardHome.tsx`) y pasa a ser Hoy en su densidad completa. El grabador (`VoiceRecorderWidget`) se queda como botón de captura siempre visible; la actividad pasa a "Recientes".
- **Manager:** su home es **Equipo** — primero la cola de coaching (las 3 llamadas que importan esta semana), después cómo va Hoy en el equipo (quién tiene seguimientos prometidos vencidos). Los patrones de objeciones existen, pero como vista secundaria, nunca como portada.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Equipo · esta semana                                                         │
│                                                                              │
│ Para revisar · 3             │ Lucía → Marina · 14 min   │ Al margen         │
│ ──────────────────────────── │ ───────────────────────── │ ───────────────── │
│ Lucía → Marina · 14 min      │ Marina: "Ahora mismo no   │                   │
│ Precio, sin respuesta        │ tenemos presupuesto       │                   │
│                              │ para esto."               │                   │
│ Pau → Grupo Rovira · 22 min  │                           │                   │
│ Primera llamada de Pau       │ Lucía: "Vale, entiendo.   │ ✎ Aquí, pregunta  │
│                              │ Te escribo en unas        │   qué les cuesta  │
│ Ana → Loop · 9 min           │ semanas."                 │   no hacerlo este │
│ 3 semanas sin contacto       │                           │   trimestre.      │
│                              │                           │ ☐ Convertir en    │
│                              │                           │   regla · Precio  │
└──────────────────────────────────────────────────────────────────────────────┘
```

La transcripción se lee como una página de cuaderno. El manager toca un turno y escribe al margen. Si marca "Convertir en regla", esa nota aparece desde ese momento en el brief y en la pastilla de cualquier comercial que se cruce con esa objeción. Eso es "corriges una llamada, aprende todo el equipo" hecho interfaz.

**Configuración** (aquí sí puede haber más profundidad, como pediste): playbook por categoría de objeción, tono del seguimiento, mapeo del CRM (ya existe), zonas horarias del resumen de la mañana.

### 1.4 WhatsApp — la casa del field

- **Resumen de la mañana** como mensaje de lista de WhatsApp (hasta 10 filas): una fila por tarjeta de Hoy, con su motivo. Opt-in por comercial.
- **Después de aprobar** una nota de voz: el borrador del seguimiento vuelve como mensaje, con botones de respuesta (máximo 3): *Enviar por email · Copiar · Descartar*.
- **El chat** (`crm_copilot`) no cambia de forma — gana herramientas nuevas (ver `ESTRUCTURA_INTELIGENTE.md` §3.4).

---

## 2. Styling — extender el sistema actual, no inventar otro

### 2.1 Lo que ya es verdad

La autoridad visual es el código, no `src/lib/theme/VISUAL_GUIDE.md`: esa guía describe un mundo anterior (Inter en black, tarjetas de cristal, radios de 2–4rem) que el código ya dejó atrás. Conviene actualizarla cuando se unifiquen los tokens (§2.3).

Lo que las tres superficies ya comparten, escrito en su propio código:

- **Papel para el contenido, cristal solo para lo que flota** — está literalmente en `tokens.ts`, en `desktop/renderer/theme.css` y en `popup/styles.css`.
- **Cuaderno silencioso**: Geist a 400, jerarquía por tamaño y color, no por peso (`popup/styles.css`; el web ya lo sigue en `tokens.ts`, donde todo es `font-normal` y `capsLabel` ya ni siquiera va en mayúsculas).
- **Un solo acento, bronce.** Estrategia de color restringida — la correcta para superficies de trabajo.
- **Pills** en botones e inputs, **hairlines** en vez de sombras, movimiento de **150 ms**.

### 2.2 La gramática nueva: cuatro marcas, un significado cada una

Esto es lo único que se añade al sistema. Su fuerza está en no usarlas para nada más:

| Marca | Significa | Dónde aparece |
|---|---|---|
| **Papel** (blanco, hairline, sin sombra) | Contenido que lees o editas | Tarjetas de Hoy, brief, revisión, seguimiento |
| **Cristal** (blur + luz interior) | Algo que flota o está en vivo | Pastilla, cabecera del side panel, franja del copiloto en la extensión |
| **Filete bronce** a la izquierda | "Esto viene de tu equipo" — lo que funcionó, una regla del playbook | Tarjeta de Hoy, brief, fila de sugerencia de la pastilla, cola de coaching |
| **Instrument Serif en cursiva** | La voz de tu manager | Notas al margen en el brief, la revisión y el coaching. Nada más (salvo el wordmark) |

El rojo se reserva para grabar y para destruir. Un seguimiento vencido nunca se pinta en rojo: se dice en texto (*"hace 12 días"*), en bronce oscuro.

### 2.3 La deriva a corregir, con números

Hoy hay tres formatos de token distintos: la web usa tripletas HSL con Tailwind, el desktop copia esas tripletas a mano y la extensión usa colores completos con otros nombres. Y los valores no coinciden. Regla para elegir el canónico: **solo se cambia donde lo exige la accesibilidad; en lo demás gana la web, que es donde menos se toca.**

| Token | Web | Extensión | Canónico | Por qué |
|---|---|---|---|---|
| Texto secundario | `30 6% 46%` → **4,18:1** sobre crema | `30 6% 42%` → **4,86:1** | **`30 6% 42%`** | El de la web falla AA (4,5) sobre crema, y es justo el color de las líneas de motivo y evidencia de Hoy |
| Éxito | `142 76% 36%` → **3,35:1** sobre blanco | `#346538` → **6,85:1** | **`#346538`** | El verde de la web falla AA como texto (se usa en `badge-success`); el terroso de la extensión además encaja mejor con la paleta |
| Beige claro como texto | 3,60:1 sobre blanco | — | Solo texto grande o decorativo | Falla AA a tamaño normal |
| Texto principal | `30 10% 14%` (14,3:1) | `30 12% 12%` (15,2:1) | **Web** | Los dos pasan de sobra |
| Bronce | 6,31:1 sobre blanco · 5,84:1 crema sobre bronce | igual | Sin cambios | Pasa en los dos usos |

Deriva del desktop que hay que traer al cuaderno: usa la fuente del sistema en vez de Geist, títulos y botones a peso 600, y etiquetas en mayúsculas con tracking 0.14em. Las dos otras superficies ya dejaron eso atrás.

### 2.4 Las piezas, una a una (intención, no CSS)

**Tarjeta de Hoy** — papel. Primera línea: nombre (foreground) y empresa (secundario). Segunda línea, la protagonista: el motivo, en una frase, a tamaño de cuerpo. Tercera línea, opcional: la jugada del equipo, con filete bronce. Acciones: una sola pill primaria (*Llamar*, *Escribir* o *Abrir*, según lo que toque) y acciones de texto en gris (*Posponer*, *Ya no aplica*). Nunca número de prioridad ni score. Densidades: dos líneas en la extensión; completa en desktop y web.

**Brief** — papel, cuatro filas como máximo: *Última vez · Quedó pendiente · Objeción abierta · Lo que funcionó*. La última lleva el filete bronce. Si hay nota del manager, va al final, al margen, en serif cursiva a 15 px como mínimo (a tamaños menores la cursiva pierde legibilidad).

**Pastilla** — cristal, la misma forma que ya existe (`overlay-pill`). Estado base: punto de grabación y una línea de transcripción en gris. Estado sugerencia: una segunda fila con el filete bronce, la categoría en caja normal (*Precio ·*), la frase (≤ 90 caracteres) y la atribución (*Alex · 4 de 6*). Se recoge sola a los ~10 s o cuando el comercial vuelve a hablar.

**Revisión** — papel. Orden nuevo: 1) la línea de estado del CRM o el bloque de confirmación, según la confianza; 2) el seguimiento; 3) resumen y próximos pasos; 4) campos del CRM plegados (*"7 campos guardados · Ver"*); 5) el deal emparejado. Una sola acción principal por pantalla.

**Seguimiento** — papel. Destinatario como chip, asunto a peso 450, cuerpo como texto legible. *Enviar* (pill bronce) · *WhatsApp* (pill fantasma, solo si hay teléfono) · *Copiar* (texto). Sin selector de plantillas, sin "Generar".

**Nota del manager** — serif cursiva al margen, con el nombre del manager. Dentro del coaching lleva la casilla *Convertir en regla*.

**Nombres de las categorías de objeción** (una sola taxonomía, ver §3.6): Precio · Momento · Decisor · Competidor · Statu quo · Confianza · Otra.

### 2.5 Estados que hay que diseñar sí o sí

- **Hoy, primera vez:** *"Graba tu primera llamada y aquí aparecerá lo que toca después."* — con el botón de captura como única acción.
- **Hoy, vacío:** *"Nada urgente hoy. Buen momento para prospectar."*
- **Hoy, cargando:** tres siluetas de tarjeta en papel. Nada de spinners.
- **Tarjeta resuelta en otra superficie:** desaparece con un fundido de 150 ms la próxima vez que esa superficie recibe foco.
- **Seguimiento sin email del contacto:** campo de email en línea o, si hay teléfono, WhatsApp como opción principal.
- **Seguimiento aún no listo** (caso raro, ver §3.4): el resumen aparece primero y el seguimiento dice *"Escribiendo el seguimiento…"* con un brillo discreto. Si el diseño técnico funciona, casi nadie debería verlo nunca.
- **Pastilla sin respaldo:** silencio. Ese es el estado por defecto.
- **Desktop, conexión caída:** *"Sin conexión — seguimos grabando en local."* (depende de guardar el audio, §4).
- **Coaching sin nada que revisar:** *"Esta semana no hay nada que revisar."* — como un buen resultado, no como un vacío.

---

## 3. Integración técnica — lo más smart

### 3.1 Tres stacks, una sola implementación de cada pieza

Web en React 18, extensión y desktop en JS vanilla. Reescribir la extensión (`popup.js`, 160 KB) o el desktop en React no compensa. Tampoco hace falta:

**Custom elements sin shadow DOM** — `<v-today-card>`, `<v-brief>`, `<v-followup>`, `<v-review>`, `<v-pill-suggestion>`, `<v-manager-note>`. Son Web Components nativos: funcionan igual en las páginas de la extensión, en el renderer de Electron y en React. Sin shadow DOM, heredan los tokens y una hoja común (`vocify-ui.css`) sin pelearse con Tailwind (clases con prefijo `v-`). Reciben los datos como propiedad (`el.data = item`) y emiten un único evento (`v-action`, con `{id, action}`).

- **En React 18** hace falta un hook de ~20 líneas (`useVElement`) para pasar la propiedad y escuchar el evento. Si esa fricción molesta, la web puede reimplementar las piezas en React con las mismas clases CSS: se pierde la implementación única, pero no la coherencia visual.
- **Estrategia de estrangulamiento:** las piezas nuevas nacen compartidas desde el primer día. Las pantallas de revisión que ya existen se migran a `<v-review>` cuando se toquen, no antes.

**Dónde vive el código compartido.** Hoy la extensión y el desktop ya duplican lógica a mano (`extraction-omit.js` está "kept in lockstep" entre los dos repos). Recomiendo **traer el desktop al monorepo**, en la carpeta `desktop/` que ya existe como puntero, con una carpeta `shared/` (`tokens/` + `ui/`). Una restricción real que marca el diseño: **una extensión de Chrome no puede cargar archivos fuera de su carpeta**, así que un script (`scripts/sync-shared.mjs`) copia `shared/` dentro de `chrome-extension/shared/` y `desktop/renderer/shared/` al construir. La web lo importa con un alias de Vite.

### 3.2 Tokens: una fuente, tres salidas

`shared/tokens/tokens.json` → `scripts/build-tokens.mjs` (~40 líneas) → tres archivos generados con los mismos nombres:

- `src/styles/tokens.css` — tripletas HSL, lo que espera Tailwind/shadcn (`hsl(var(--beige))`).
- `chrome-extension/popup/tokens.css` — colores completos, que es lo que ya usa la extensión (`var(--beige)`). Así no hay que reescribir los 53 KB de `styles.css`.
- `desktop/renderer/tokens.css` — tripletas, como `theme.css` hoy.

Un check en CI falla si alguien edita un archivo generado a mano. Los valores canónicos son los de §2.3.

### 3.3 El backend devuelve pantallas, no datos

Los clientes no montan frases ni deciden el orden: reciben *view-models* listos para pintar. Así el mismo motivo se lee idéntico en las cuatro superficies y se corrige en un solo sitio.

| Endpoint | Devuelve | Notas |
|---|---|---|
| `GET /api/v1/today` | `{items: TodayItem[], pulse}` | `TodayItem` = `{id, contact, deal (con URL del CRM), reason, evidence?, play?, due_label, primary_action, secondary_actions}` — con `reason` y `due_label` ya escritos |
| `POST /api/v1/today/{id}/resolve` | — | `done`, `snooze` (con `until`) o `dismiss` |
| `GET /api/v1/briefs?contact_id=&deal_id=` | `Brief` | **v1 sin llamadas nuevas al LLM:** "Última vez" reutiliza `extraction.summary`; lo pendiente sale de `nextSteps` y las señales; la jugada, de patrones y playbook |
| `GET /api/v1/memos/{id}/preview` (ya existe, `ApprovalPreview`) | + `followup` | `{to, channel_suggested, subject, body, language, status: ready\|generating\|unavailable}` |
| `POST /api/v1/memos/{id}/followup` | — | `{action: sent\|copied\|opened_whatsapp, channel, final_body}`. Registra en el CRM y resuelve la señal correspondiente |
| `GET /api/v1/coaching/queue` · `POST /api/v1/coaching/notes` · `GET/PUT /api/v1/playbook` | — | Web del manager |
| `/api/v1/copilot/suggest` (ya existe, SSE) | + `grounded`, `source_label` | Ver §3.7 |

**Los motivos se escriben con plantillas deterministas, no con el LLM.** Una plantilla por tipo de señal e idioma (ES/EN) en el backend, con huecos rellenados desde el payload de la señal. Es la frase más leída del producto: tiene que ser idéntica, instantánea, sin coste y sin riesgo de inventar. Y se prueba con TDD, como pide vuestro proceso para la lógica determinista. El LLM se queda donde el contenido es único: el seguimiento.

### 3.4 El seguimiento tiene que existir antes de que se abra la revisión

La sensación "instantánea" es un problema de secuencia, no de UI:

- **En el pipeline, después de la extracción y antes de pasar el memo a `pending_review`.** Sale después y no en paralelo a propósito: con el resumen, los próximos pasos y el contacto ya extraídos, el email puede citar lo que de verdad se dijo. Con un tope de tiempo (del orden de 8 s): si se pasa, el memo pasa a revisión igual con `followup.status = generating` y el borrador termina en segundo plano; el cliente vuelve a pedir el preview.
- **En el idioma de la conversación**, que ya se detecta.
- **Con la voz del comercial, y aprendiéndola sola.** v1: tono de empresa + 2–3 emails de ejemplo por comercial (`user_profiles.writing_samples`), como pide B3 en `MASTER_PLAN.md` ("few-shot con sus emails reales"). v2 casi gratis: cada `final_body` que el comercial edita y envía se guarda como un ejemplo más. Cada seguimiento escribe mejor el siguiente — la misma tesis del producto, aplicada al email.
- **Enviar, v1 sin OAuth:** *Enviar* abre el cliente de correo del comercial con todo relleno (`mailto:`, o la URL de redacción de Gmail u Outlook web si lo tiene configurado); *WhatsApp* abre `wa.me/<número>?text=…`; *Copiar* copia. Límite honesto: sin OAuth no podemos confirmar que salió, solo que el comercial lo abrió para enviarlo. La nota del CRM tiene que decir exactamente eso. v2: OAuth de Gmail/Outlook para enviar directo y registrar el hilo — solo cuando la v1 demuestre uso.
- **La métrica de B3 sale sola:** comparar `final_body` con el borrador da el % de envíos sin editar.
- Recordatorio del research anterior: el mensaje comercial por WhatsApp o email a quien no ha dado consentimiento tiene su régimen (LSSI). El botón existe; el uso correcto es del cliente.

### 3.5 Hoy se limpia sola

- **Dos disparadores.** Por evento: cuando un memo llega a revisión o se aprueba, se crean o resuelven las señales de ese contacto y ese deal. Por calendario: un job de mañana por empresa (en su zona horaria) calcula las señales de tiempo — silencios, callbacks que vencen — y envía el resumen de WhatsApp a quien lo haya activado. En Railway, un servicio cron que ejecuta `python -m app.jobs.morning`.
- **Autoresolución.** Una señal se resuelve sola cuando cambia la condición que la creó: llega una nueva interacción con ese contacto, se hace el callback, el deal cambia de etapa. El comercial casi nunca tiene que "completar" una tarjeta: llamar ya la resuelve. Por eso Hoy no se convierte en otra bandeja de tareas pendientes.
- **Orden** (reglas explícitas, las mismas que propone B6): callbacks prometidos que vencen hoy o ya vencieron → leads con interés que se enfrían → objeciones abiertas con jugada conocida → el resto por cadencia. Con un tope visible (del orden de 7) y el resto plegado. El número exacto se valida con los betas.
- **Sincronía entre superficies.** v1: volver a pedir `/today` al recibir foco y después de cada acción. v2, solo si hace falta: Supabase Realtime sobre `action_signals` — ya usáis Supabase, no es infraestructura nueva.

### 3.6 Una sola taxonomía para todo

El copiloto en vivo ya clasifica objeciones en `price | timing | authority | competitor | status_quo | trust | other` (`services/copilot/prompts.py:39`). Esa lista se reutiliza tal cual como `interaction_patterns.objection_category`, como categoría del playbook y como etiqueta del coaching. Cero diseño de taxonomía nuevo, y una objeción detectada en vivo, un patrón histórico y una regla del manager hablan de lo mismo.

### 3.7 La pastilla solo habla cuando tiene respaldo

Hoy el prompt del copiloto solo tiene `product_context` para apoyarse (`prompts.py:31,53`). Cambio: cuando detecta una objeción, el servidor busca las entradas del playbook y los mejores patrones de esa categoría en esa empresa, y los mete en el prompt como "lo que funciona en este equipo". La respuesta añade `grounded` y `source_label` (*"Alex · 4 de 6"*). Los clientes solo muestran la fila de sugerencia si `is_objection && grounded`.

Consecuencia importante: **"callado por defecto" deja de ser una decisión de interfaz y pasa a ser un contrato de datos.** Sin patrones ni reglas, la pastilla no dice nada — mejor eso que un consejo genérico idéntico al de Aircall. Con reglas del manager, habla desde el primer día.

### 3.8 Coaching: notas ancladas a un turno

- `transcript_turns.py` separa por hablante, pero no he encontrado marcas de tiempo por turno. v1: la nota se ancla al índice del turno. Para reproducir el clip hacen falta tiempos y el audio guardado; habría que comprobar si `transcript_stt_meta` ya trae los tiempos.
- **Dependencia real:** el desktop hoy sube solo texto, sin audio. Las reuniones de los AE no tendrán clips de coaching hasta que el desktop guarde el audio. Eso sube de prioridad esa tarea (§4, carril B).
- Nota con *Convertir en regla* → entrada del playbook para su categoría → aparece en el brief y en la pastilla de todo el equipo.
- El score (C1) existe por debajo para ordenar la cola de revisión. El producto que ve la gente es la nota.

### 3.9 Datos nuevos, en resumen

Además de lo ya propuesto en `ESTRUCTURA_INTELIGENTE.md` (`memos.interaction_type`, `memos.score`, `action_signals`, `interaction_patterns`):

| Qué | Forma | Para qué |
|---|---|---|
| `memos.followup` | JSONB (1:1 con el memo, igual que `extraction`) | Borrador, estado, cuerpo final, acción y fecha |
| `user_profiles.writing_samples` | JSONB, últimos N | Voz del comercial; crece sola con cada envío editado |
| `playbook_entries` | `{company_id, objection_category, guidance, source_memo_id?, source_turn?, author_id, active}` | Reglas del equipo — lo normativo |
| `coaching_notes` | `{memo_id, turn_index, author_id, body, promoted_entry_id?}` | Feedback de una llamada concreta |

`playbook_entries` y `interaction_patterns` se quedan separadas a propósito: una dice lo que queremos, la otra lo que pasó. Mezclarlas rompería la señal de "lo que funcionó".

---

## 4. Orden de construcción

**Principio: slices verticales.** Cada slice sale entero — backend + pieza compartida + todas las superficies donde tenga sentido. Nada de "primero todo el backend y luego todas las pantallas".

**Dos carriles, uno por founder** — respeta el límite de 2 features en construcción de `MASTER_PLAN.md`:

### Carril A — la columna vertebral

| # | Slice | Superficies | Por qué en este orden | Tamaño* |
|---|---|---|---|---|
| 0 | **Cimientos:** tokens únicos + `shared/` + tablas nuevas + decisión del monorepo | todas | Todo lo demás se apoya aquí | M |
| 1 | **Seguimiento** (B3 v1) | desktop, extensión, web (`MemoDetail`), WhatsApp | Es el más pequeño de punta a punta, va sobre pantallas de revisión que ya existen, lo pide la gente y deja dos cosas para siempre: la métrica de envíos sin editar y los ejemplos de voz | S–M |
| 2 | **Hoy v0** (B6 v0) | extensión (lista + cola), web (home), desktop (home), WhatsApp (resumen de la mañana) | Es la joya; la v0 se construye sobre lo que ya extraéis y empieza a acumular señal desde ya | M |
| 3 | **Brief** (B4/B5 v1) | extensión (ficha + cola), web (tarjeta expandida), desktop (home) | Sin llamadas nuevas al LLM; con Hoy ya en marcha, el brief es la tarjeta abierta | S |
| 4 | **Coaching** (C1/C2 v1): cola + notas + playbook | web (manager) + nota del manager en brief y revisión | Necesita historia acumulada y alimenta la pastilla | L |
| 5 | **Pastilla con respaldo** | desktop, extensión | Llega cuando ya hay reglas y patrones que la respalden | S–M |

### Carril B — captura y desktop

1. **Prefijo 400** en el dialer, antes del 17 de octubre (`ESTRUCTURA_INTELIGENTE.md` §0).
2. **Desktop:** commit + push del trabajo local; cuaderno silencioso + Geist (va con el slice 0); diarización multi-hablante; **audio guardado** (desbloquea los clips de coaching del §3.8).
3. Después, lo que ya planea `MASTER_PLAN.md`: bot de reuniones con Recall.ai (A3) e ingesta de otros dialers (A9).

*\*Tamaño relativo (S ≤ 1 semana, M 1–2, L 2–3), sin contar las etapas de teardown/spec/QA de vuestro proceso. Estimación, no compromiso.*

**Frente a `MASTER_PLAN.md`:** adelanta B3 y la v0 de B6 respecto a la ampliación de captura, que sigue en paralelo en el carril B. El motivo es el mismo de `ESTRUCTURA_INTELIGENTE.md`: la captura ya es fuerte en cuatro superficies, y cada semana sin la columna vertebral es una semana de datos capturados que no se convierten en nada.

**Qué medir por slice:** 1 → % de seguimientos enviados sin editar y % de revisiones con seguimiento enviado. 2 → % de tarjetas resueltas actuando (no descartando) y tiempo desde abrir Hoy hasta la primera llamada. 3 → % de llamadas con el brief visto antes. 4 → notas por manager y semana, y reglas creadas que luego se usan. 5 → % de objeciones que acaban en reunión cuando hubo sugerencia con respaldo frente a cuando no la hubo.

---

## 5. Lo que no vamos a hacer

- Reescribir la extensión o el desktop en React.
- Montar un paquete npm de componentes: una carpeta basta.
- OAuth de Gmail/Outlook antes de que `mailto:` demuestre uso.
- Enseñar scores en la interfaz del comercial.
- Una segunda ventana flotante para el copiloto.
- Integrar calendario solo para avisar antes de las reuniones, antes de que el brief demuestre su valor en la extensión.
- Usar el LLM para escribir los motivos de Hoy.
- Infraestructura de tiempo real antes de que "volver a pedir al recibir foco" se quede corto.
- Usar el filete bronce o la serif cursiva para decorar.

---

## 6. Decisiones que son vuestras

1. **¿Desktop dentro del monorepo?** Recomiendo que sí: elimina la duplicación a mano que ya existe y hace posible `shared/` sin copiar entre repos.
2. **¿Los valores canónicos de §2.3?** Recomiendo los de la tabla: solo se cambia donde falla la accesibilidad.
3. **Enviar por defecto:** ¿`mailto:` o redacción de Gmail/Outlook web? Depende de qué usan vuestros betas.
4. **Resumen de la mañana:** ¿a qué hora y para qué roles? Recomiendo opt-in, activado por defecto solo para field.
5. **Windows para el desktop:** solo si vuestros AE lo necesitan. Hoy solo hay build de Mac.
