# Vocify: composición — máxima señal, mínima superficie

Usa este archivo al diseñar o implementar UI. SKILL.md manda el criterio;
aquí se decide el control. Si dudas entre dos controles, elige el de menos
superficie que conserve la acción descubrible.

## 0. Densidad: desvelar poco, revelar mucho

Cada bit en pantalla debe cambiar una decisión. Si no cambia qué hace la
persona a continuación, sobra.

| Capa | Qué vive ahí | Test |
|---|---|---|
| Superficie | Identidad, estado, acción principal, 1–3 datos que ordenan la siguiente acción | ¿Se entiende la fila/pantalla en <2s sin hover? |
| Hover / tooltip | Nombre de un icono, atajo, consecuencia corta, dato secundario | ¿El tooltip dice *qué es*, no un párrafo? |
| Clic (expand, sheet, tab) | Detalle, historial, configuración, lote | ¿El clic revela un bloque, no un laberinto? |
| Nunca aquí | Preferencias raras, debug, copy de onboarding, IDs internos | ¿Esto pertenece a otra superficie o a ajustes? |

**Coherencia enlazada a la función.** El layout predice el comportamiento:
lista densa → seleccionar y actuar; timeline → leer y seguir; composer →
escribir y enviar. No mezcles paradigmas en el mismo bloque (p. ej. cards
enormes dentro de una lista operativa).

**Proactivo sin ruido.** Infiere defaults, preselecciona lo obvio, agrupa
lo que la persona va a hacer juntas. No anticipes con banners, tours ni
texto de "puedes…". La proactividad es estado listo, no explicación.

Mal: título + subtítulo + 3 botones con verbo + helper de 2 líneas.
Bien: fila compacta (quién / qué / cuándo) + 1 acción primaria + iconos
con tooltip para el resto.

## 1. Botones

Una acción primaria **por bloque visible**. No por página entera si hay
columnas; sí por el foco actual.

| Situación | Control | Variante |
|---|---|---|
| La acción de este momento (Grabar, Enviar, Guardar, Crear) | Botón con verbo | `default` / `hero` / `recording` |
| Deshacer / destructivo claro | Botón o `IconAction` danger, nunca al lado del primario sin separación | `destructive` o `tone="danger"` |
| Secundaria frecuente (Filtrar, Exportar) | Ghost o link, o icono si el significado es universal | `ghost` / `link` |
| Terciaria o de fila (abrir, copiar, más) | Solo icono + tooltip | `IconAction` o `Button size="icon"` |
| Preferencia rara | No es botón de pantalla. Ajustes / menú | — |

Reglas:

- Verbo en infinitivo o sustantivo corto: `Grabar`, `Enviar`, `Guardar`.
  No `Haz clic para comenzar a grabar tu reunión`.
- No apiles dos primarios. Si hay dos de igual peso, el flujo está mal
  cortado: tabs, pasos o un menú.
- No inventes un botón nuevo "por claridad". Si el icono existente +
  tooltip basta, el botón de texto es peso de más.
- Pending: el mismo control, spinner (`VocifySpinner` / `IconAction pending`),
  no un segundo botón ni un texto "Procesando, espera…".
- En extensión / chip desktop: máximo un primario. El resto icono o menú.

## 2. Iconos

Los iconos comprimen abundancia. Una toolbar de 6 verbos es un fallo;
una toolbar de 4 iconos conocidos + un `Más` es el patrón.

- Solo iconos **universales** o **ya usados en Vocify** (grabar, buscar,
  ajustes, cerrar, más, copiar, eliminar). Si hay que adivinar, no es icono
  solo: es botón con verbo, o icono + label en ese sitio.
- Todo icono clicable: `aria-label` + tooltip (`IconAction`). Sin tooltip
  no hay icono de acción.
- Misma acción = mismo icono en dashboard, extensión y desktop.
- No decorar. Un icono que no dispara ni aclara estado sobra.
- No sustituyas un dato (nombre, hora, puntuación) por un icono críptico.
- Iconos que se mueven: solo cuando **pasa algo** (un reintento corre, una
  copia entra, una llamada suena, llega un informe). Usa el módulo
  compartido `shared/ui/components/anim-icon.js` (`AnimIcon` en web,
  `renderAnimIcon` / `data-v-icon` + `hydrateAnimIcons` en extensión y
  desktop): `refresh` gira en `busy` (no lo cambies por un spinner), `copy`
  pasa a check en `done` (`flashCopied`, sin toast), `phone` suena en
  `ringing`, `bell` suena una vez con `play()`. Dentro de un botón o enlace
  hacen una vista previa en hover. Guardado en el CRM = `DoneMark`.
  Nunca animar iconos decorativos (sparkles, papelera, ajustes, logout).

## 3. Tooltips

El tooltip es la capa hover del mapa de densidad. No es ayuda contextual
larga ni un placeholder de copy que no cupo.

**Sí:** nombre de la acción (`Eliminar`, `Copiar enlace`), atajo, estado
corto (`Sincronizando`), un número o condición que no cabe (`3 sin leer`).

**No:** frases de onboarding, disclaimers, instrucciones de 2+ líneas,
repetir el label que ya está al lado, tooltips en botones con verbo
visible (salvo atajo).

- Delay del provider: el de la app (`delayDuration={200}`). No pongas
  tooltips instantáneos en cada fila al pasar el ratón en diagonal.
- Un trigger, un tooltip. No anides.
- Móvil / touch: si la acción solo existe en tooltip, no existe. Debe
  haber equivalente (menú, sheet, label).

## 4. Tabs

Tabs parten **un mismo objeto** en vistas mutuamente excluyentes que la
persona cambia sin perder contexto (Hoy | Hecho; Audio | Notas; Equipo |
Mía).

| Usa tabs | No uses tabs |
|---|---|
| 2–5 vistas del mismo sitio, mismo nivel | Wizard / pasos (eso es un flujo, no tabs) |
| La persona compara o alterna a menudo | Navegación a otra feature (eso es nav / ruta) |
| Cada tab cabe en viewport sin page-scroll | Más de ~5: menú, sidebar o agrupación |
| El recuento cabe en el label (`Notas 12`) si ordena | Tabs que esconden la acción principal |

- La tab activa se lee sin color-only: peso + indicador ya del componente
  `Tabs`.
- No pongas un primario distinto por tab si el primario de la pantalla
  es otro; el primario sigue al foco.
- Settings ya tiene nav por sección (`visibleSettingsTabs`). No dupliques
  un segundo nivel de tabs sin necesidad.

## 5. Scroll vs paginación vs recorte

La página no es un documento infinito. El scroll vive **dentro del bloque
que lo necesita**, no en el body si se puede evitar.

| Volumen / tipo | Patrón |
|---|---|
| Cabe en ~1 viewport (≤ ~12 filas compactas) | Lista completa, sin pager |
| Lista operativa larga (contactos, memos, cuentas) | Paginación. Default `PAGINATION.DEFAULT_PAGE_SIZE` (20), tope 100 |
| Feed continuo de un evento (transcripción en vivo) | Scroll interno del panel + pin al final. No paginar el vivo |
| Historial largo consultable | Paginación o "cargar más" al pie del **panel**, no de la página |
| Texto largo (nota, email) | Recorte a 2–4 líneas + expandir. No un muro |
| Muchas secciones de settings | Nav por sección, no un scroll de 2000px |

Reglas:

- Si hay que scrollear "muchísimo" para llegar a la acción o al siguiente
  bloque, el layout falló: tabs, sticky action, o recorta.
- Paginación visible: dónde estás, cuántos hay, siguiente/anterior. No
  inventes un pager custom si `Pagination` sirve.
- Al paginar, no saltes el scroll al top de la ventana: al top de la lista.
- Búsqueda / filtro cuando la persona busca un ítem concreto; no sustituye
  paginación en listados grandes, la acompaña.
- Nunca `overflow: auto` en cascada (página + columna + card + lista).
  Un solo eje de scroll por región.

## 6. Multi-select

Aparece cuando la persona va a hacer **la misma acción sobre N ítems**
(archivar, asignar, exportar, eliminar). No cuando N=1 es el 95% de los
casos.

- Checkbox a la izquierda de la fila, no un modo especial escondido.
- Toolbar de lote: aparece **al seleccionar**, compacta, con recuento
  (`3 seleccionados`) y 1–3 acciones. Desaparece al vaciar.
- `Seleccionar todas las de esta página` ≠ seleccionar las 10k. Si hay
  "todas", que el copy lo diga.
- Teclado: shift-click para rango cuando la lista es densa.
- En extensión / chip: casi nunca. Ahí el lote es del dashboard.

## 7. Drag

Drag reordena o suelta un objeto **cuya posición es el dato** (prioridad,
orden de playbook, adjuntar archivo). No es adorno.

- Affordance: handle o cursor `grab` en el ítem, no "arrastra para
  reordenar" como copy permanente.
- Preview / gap durante el drag; al soltar, el orden queda. Sin salto.
- Alternativa no-pointer: mover arriba/abajo en menú o teclas. Si no cabe
  en v1, el drag no es el único camino para una acción crítica.
- Drop de archivos: zona clara al arrastrar *un fichero*, no un recuadro
  vacío permanente que come la acción principal (`PlaybookStart` como
  referencia: el estado `dragging` revela la zona).
- No mezcles drag de filas con multi-select sin definir qué gana el gesto.

## 8. Cómo se usa la UI (affordance, no tutorial)

La persona descubre la UI por densidad, no por texto.

- Hover en icono → nombre. Fila → click abre. Handle → drag. Checkbox →
  lote. Tab → otra vista del mismo sitio.
- Atajos solo si ya existen en el producto; no estrenes un atajo en una
  feature lateral.
- Estados: default / hover / active / pending / disabled / empty / error.
  Disabled dice por qué en tooltip, no un alert.
- No bloquees el canvas con un modal si un `Sheet` / popover / inline
  edit basta. Modal = decisión o peligro.
- Primera vez: el estado vacío *es* el onboarding (una acción para
  construir). No un carrusel.

## 9. No hardcodear lo que queda mal o no se entiende

Hardcodear aquí no es solo "string en JSX". Es dejar en la UI un valor
que no es del dominio, no se traduce, o no escala.

**Prohibido en superficie**

- IDs (`usr_…`, UUIDs), nombres de enum crudos (`IN_PROGRESS`,
  `crm_sync_failed`), rutas, nombres de campo internos.
- Fechas en ISO crudo. Usa el formateo del repo / locale de la persona.
- Conteos `undefined` / `0 items` / `null`. Vacío diseñado, o el número
  real.
- Copy de desarrollo: `TODO`, `lorem`, `Test user`, `Click here`,
  `Submit`, placeholders en inglés si la UI está en el idioma de la
  persona.
- Labels que solo un ingeniero entiende (`Force reindex`, `Upsert
  contact`). Si es poder de ajustes, copy de persona.
- Duplicar la misma frase en título, subtítulo y tooltip.

**Datos**

- Nombres, empresas, idiomas, listas: de API / settings / i18n, no
  arrays literales de demo en el componente.
- Plurals y recuentos correctos (`1 nota`, `12 notas`).
- Truncar con sentido (nombre + tooltip con el full). No cortar a 8
  caracteres fijos.
- Si falta un dato, el hueco se diseña (— / ocultar la fila), no se
  imprime `N/A` o el JSON.

## 10. Mini checklist de composición (por pantalla)

Para cada bloque nuevo, una línea en el plan:

`bloque → control → capa (superficie|hover|clic) → volumen (0/12/80/400) → por qué no el siguiente control más pesado`
