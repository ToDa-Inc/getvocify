# Vocify desktop: causas de la captura y distancia respecto al plan

Revisión: 25-09-2026. Base: `feat/vocify-v1`, HEAD `653f0c9`, **incluyendo cambios locales sin commit**. No se ha modificado código de producto.

## Veredicto

La captura tiene errores concretos de estado/renderizado, además de una implementación incompleta del recorrido del AE. Corregir el CSS quitaría contradicciones visuales; todavía quedaría por cumplir la home y la revisión previstas. Los tests ejecutados no cubren esas condiciones.

## Qué app se está revisando

- El proceso abierto es `desktop/macos/Vocify.app/Contents/MacOS/VocifyHost` del worktree `/Users/danizal/getvocify/.worktrees/vocify-v1`. Es un host SwiftUI/WKWebView.
- El repositorio hermano `/Users/danizal/getvocify-desktop` está en `5f3730e`, conserva un renderer y host Electron diferentes, y tiene modificaciones locales. Su HTML no contiene la estructura `app-shell`/`home-hoy` de esta captura.
- El plan ejecutable F05, línea 69, aclara que las referencias al repositorio hermano son históricas y que, tras F01, el desktop se modifica en el monorepo. El directorio del proceso es coherente con esa decisión.
- Comparados SHA-256 de `renderer/app.js`, `styles.css`, `index.html`, `theme.css` y `lib/home-hoy.js`: fuente y recursos empaquetados coinciden. El proceso arrancó después de las modificaciones de esos archivos. No hay evidencia de que esta captura se explique por un bundle antiguo.
- `WebShell.swift:52` resuelve los recursos y `scripts/build-app.sh:34` los copia al paquete. Es necesario reconstruir y comprobar **esa** app para validar una corrección.

## Evidencia y límites

1. Captura aportada por el usuario.
2. Lectura de código, cambios locales, planes y recursos empaquetados.
3. Inspección en Chrome del renderer servido por el propio proceso nativo, en su puerto loopback. Sin iniciar sesión ni modificar datos. Esto comprueba CSS/DOM; no reproduce el bridge ni la sesión autenticada de WKWebView.
4. Reproducciones puras de idioma, filas del historial y body de checklist, con entradas sintéticas locales.
5. `node --test desktop/lib/server.test.js desktop/lib/shell.test.js desktop/lib/notes-list.test.js desktop/lib/home-hoy.test.js`: **16 tests pasan**.

La inspección directa de la ventana nativa quedó bloqueada por permisos pendientes de Accesibilidad/Screen Recording. No se ha grabado una reunión ni probado envío a CRM. No hay veredicto Reticle de funcionamiento. Al ser una revisión/documentación, no se ha aplicado una modificación de UI que dar por verificada.

## Hallazgos priorizados

Las rutas siguientes son relativas a `/Users/danizal/getvocify/.worktrees/vocify-v1`.

### D01 · P1 · El CSS rompe el contrato de `hidden`

**Evidencia:** `desktop/renderer/styles.css:28–42`, `:126`, `:132`; `desktop/renderer/app.js:637–646`.

`setLiveUi(false)` oculta correctamente el indicador y la ayuda con `.hidden = true`. Sin embargo, las reglas de autor les dan `display: inline-flex`; la rail tiene `display:flex` y el bloque idle `display:grid`. No existe un contrato global que preserve `[hidden]`.

**Reproducción:** en el renderer servido por la app, `notes-rail.hidden === true`, pero su estilo calculado es `display:flex` y tiene un rectángulo visible de 1470 × 199,4 CSS px en la ventana de inspección. El login muestra «New note». `live-chip` tiene `hidden:true` y `display:inline-flex`; su rectángulo en este login es cero porque su sección padre sí está oculta. Al mostrarse la sección de escucha, queda expuesto el indicador, coherente con el `00:00` rojo de la captura.

**Impacto:** la pantalla presenta señales de grabación cuando está idle; también puede mantener el contenido de home durante una captura. No prueba que el micrófono esté activo: prueba que la señal visual no es fiable.

**Solución:** establecer una regla de visibilidad que prevalezca en estas superficies, por ejemplo `[hidden] { display:none !important; }`, o restringir explícitamente las reglas de layout a `:not([hidden])`. Validar idle/live/login/review en el paquete nativo. No basta con añadir más asignaciones de `.hidden` en JS.

### D02 · P2 · El menú de cuenta se abre en cada actualización del shell

**Evidencia:** `desktop/renderer/app.js:616–622`, `styles.css:48–51`.

El cambio local introduce `if (loggedIn) accountMenu.open = true` dentro de `notifyShell()`. No es una hipótesis sobre un `<details>` defectuoso: el programa lo abre explícitamente. Sus botones participan en el flujo normal del header y aumentan su altura.

**Impacto:** logout/dashboard ocupan permanentemente el espacio principal. Si el usuario lo cierra, la siguiente notificación puede reabrirlo. La cuenta domina sobre la tarea que venía a realizar.

**Solución:** separar sincronización de sesión y apertura del menú; abrir solo por interacción. Presentar las opciones en una capa anclada que no empuje el contenido, con foco y cierre accesibles. Mantener email en caja normal, sin tratarlo como etiqueta de estado.

### D03 · P1 · La home no tiene estados suficientes para orientar al usuario

**Plan:** `docs/features/PLAN_INTEGRACION.md:60–62`: home con próxima reunión cuando haya calendario, Hoy y botón de escuchar.

**Evidencia:** `desktop/renderer/index.html:51–74`; `app.js:390–439`.

El bloque idle contiene únicamente Hoy y brief. Si faltan ambos, no queda encabezado, explicación ni contexto. Hoy borra sus hijos y se oculta con cero tarjetas. El `catch` de `/today` solo limpia `homeHoyFlight`: una caída inicial tampoco tiene representación visual. El CTA contiene únicamente una esfera; su nombre se establece mediante `aria-label`, sin texto visible.

**Impacto:** ausencia de pendientes, carga, falta de configuración y fallo de red se parecen a una app vacía. El usuario tampoco ve con claridad qué inicia el botón.

**Solución:** una home explícita con acción visible «Escuchar reunión»; estados separados de carga, vacío válido, fuente no conectada y fallo con reintento. Mostrar próxima reunión solo con datos reales de calendario. Mantener accesible la captura aunque no haya tarjetas. No rellenar con contenido ficticio.

### D04 · P1 · Hoy no ofrece la acción comercial prevista

**Plan:** `PLAN_INTEGRACION.md:187`: nombre/empresa, motivo y acción Llamar/Escribir/Abrir.

**Evidencia:** `desktop/lib/home-hoy.js:3–10`; `desktop/renderer/shared/ui/today-card.js:61`; `app.js:1500–1508`.

El adaptador conserva id, reason, status, version y undoDeadline. El renderer pinta motivo y botones de descartar/deshacer. El controlador solo maneja esas dos acciones. No hay acción principal ni identidad visible del contacto en esta tarjeta.

**Impacto:** incluso cuando `/today` devuelve datos, el desktop presenta una lista que se puede quitar, pero que no ayuda a ejecutar el trabajo propuesto.

**Solución:** completar el contrato de presentación y navegación de la tarjeta con la identidad y destino reales; reutilizarlo en las superficies. Comprobar desde una tarjeta que se abre el contexto correcto y que hay un resultado visible. Si no existe destino utilizable, explicarlo sin un CTA inerte.

### D05 · P2 · Los estilos globales de formularios contaminan la ayuda

**Evidencia:** `styles.css:42–43`, `:132–142`, `:153–164`; `index.html:68–70`.

El cambio local convierte todos los `label` en flex vertical. `.assist-toggle` redefine display y alineación, pero no `flex-direction`; por eso conserva `column`. Inspección calculada: `assist-toggle` tiene `flexDirection:column`. La corrección local de tamaño del checkbox no elimina esa dirección.

**Impacto:** casilla y «Help» se apilan y parecen un control ajeno al botón. Antes de corregir visibilidad, además se muestran en idle.

**Solución:** acotar el estilo vertical a campos de formulario y definir el layout de la ayuda expresamente. Revisar su texto como una acción comprensible y su disponibilidad según estado; no convertir todos los labels de la app al corregir el login.

### D06 · P2 · La mezcla de idiomas proviene de un contrato de tipos roto

**Evidencia:** `app.js:85–87`, `:563`, `:584`, `:1123–1126`; `shared/ui/i18n.js:235`; `desktop/lib/notes-list.js:5`.

`uiLang()` devuelve el objeto de entrada de `uiLangInput`, que `strings()` sí entiende. Otras funciones esperan una cadena y comparan `lang === 'en'` o `lang === 'es'`. Esas comparaciones fallan al recibir el objeto.

**Reproducción local:** con navegador `en-US`, el botón es «New note» y el historial devuelve «25 sept, 11:23». La etiqueta de envío local cae en español; el progreso de checklist cae en inglés aunque se seleccione español.

**Solución:** resolver un código canónico `es|en` una vez y usarlo para strings, fechas, mensajes y progreso. Añadir pruebas con el valor real que devuelve `uiLang()`, no solo con cadenas introducidas directamente en los tests. Quedan también mensajes de revisión escritos en inglés, por ejemplo `app.js:1369`.

### D07 · P2 · El historial duplica información y presenta duración desconocida como cero

**Evidencia:** `desktop/lib/notes-list.js:8–17`; `app.js:595–610`.

Sin contacto/empresa, el título usa la misma fecha que la segunda línea. `audioDuration || 0` convierte la ausencia de duración en cero. El redondeo muestra también cero para clips cortos. Cinco estados distintos se reducen a un punto bronce sin etiqueta; el punto está oculto a lectores de pantalla.

**Impacto:** explica directamente las filas de la captura. El usuario no sabe qué grabó, qué requiere revisión o qué sigue procesándose. La captura por sí sola no prueba que los audios duren realmente cero.

**Solución:** título útil sin duplicar fecha, duración real o ausencia explícita, formato de segundos para clips cortos y estados comprensibles. Mantener diferenciados pendiente de revisar, procesando y fallo recuperable. Verificar el scroll con muchas notas; `min-height:100vh` en el shell no establece por sí solo un límite de altura para el scroll interior.

### D08 · P1 · La revisión conserva el orden del formulario anterior

**Plan:** `PLAN_INTEGRACION.md:80–83` y `:193`: estado/confirmación CRM → seguimiento → resumen/próximos pasos → campos plegados. Una decisión principal según confianza.

**Evidencia:** `desktop/renderer/index.html:77–101`.

El orden real es transcripción → textarea de resumen de ocho filas → próximos pasos → bloque de campos CRM → seguimiento → acciones. No hay contenedor plegable para esos campos en el marcado. Este orden no depende de una preferencia visual: contradice el orden acordado.

**Impacto:** la persona debe atravesar contenido y formularios antes de llegar al seguimiento. El trabajo de interpretación del sistema vuelve a convertirse en revisión manual de campos.

**Solución:** componer la pantalla según el resultado real de la captura. Encabezar con estado CRM/decisión pendiente y seguimiento. Resumen debajo y campos al ampliar. Mostrar «Guardado» exclusivamente tras confirmación del servidor; no arreglar el orden inventando un resultado de sincronización.

### D09 · P1 · La checklist live no recibe la identidad de la captura

**Evidencia:** `app.js:1072–1083`; `desktop/lib/listen-policy.js:13–18`; `desktop/lib/copilot-checklist.js:1–5`; `backend/app/services/copilot/checklist.py:126–142`.

Se crea `clientCaptureId`, pero `buildListenSession()` produce solo callMode/contactId. El body de la checklist live termina siendo exactamente `{"call_mode":"meeting"}`. El backend sin `capture_id` calcula la checklist con `extraction={}`, usando contexto de empresa. La revisión posterior sí envía el memoId en otra ruta del renderer; eso no repara el live.

**Impacto:** este camino no puede mostrar progreso basado en la extracción de esta reunión. Es un fallo funcional detrás de una superficie que puede parecer completa.

**Solución:** unir captura local, identidad persistida del servidor, playbook y evidencias de la reunión durante todo el ciclo. No basta con mandar un UUID local: el backend busca un memo existente y autorizado. Definir cuándo se crea/sincroniza y cómo llegan observaciones parciales. Probar que una evidencia concreta cambia el paso correspondiente, sin marcar progreso por tiempo transcurrido.

### D10 · P2 · El layout y la tipografía no completan la integración visual

**Evidencia:** `styles.css:28–59`, `:195`; `theme.css:14–16`; `PLAN_INTEGRACION.md:183`.

El panel principal tiene max-width y márgenes automáticos, pero no ocupa explícitamente el ancho disponible. El header abierto participa en su tamaño; no hay una composición de home que dé sentido al espacio restante. El email usa el chip en mayúsculas. El tema sigue usando la fuente del sistema, aunque el plan pide incorporar el desktop a la tipografía compartida.

**Solución:** contenedor principal estable con ancho disponible y mínimo cero, zonas de navegación/contenido/acción claras y scroll definido. Aplicar tipografía y tokens comunes con activos empaquetados. Comprobar el tamaño mínimo nativo 880×640 y el predeterminado 1040×760. El tamaño de la imagen adjunta no debe confundirse con CSS px.

## Por qué han pasado estos problemas

La evidencia permite describir el mecanismo, sin atribuir intenciones a quien implementó:

- **Los tests comprueban piezas, no el recorrido.** `server.test.js` busca cadenas en HTML y comprueba HTTP 200. `home-hoy.test.js` comprueba arrays. No verifican visibilidad, apertura de menú, siguiente acción o resultado en WKWebView.
- **Hay correcciones locales que no cierran la causa.** Ocultar transcripción en idle ayuda, pero deja sin resolver `[hidden]`; dimensionar el checkbox deja `flex-direction:column`. Forzar el menú abierto es una regresión introducida en el diff local.
- **Añadir un componente se ha quedado corto respecto al contrato.** Existe `home-hoy`, pero no la acción principal; existe followup, pero al final del formulario; existe checklist, pero sin identidad de la captura live.
- **El paquete real no forma parte de los 16 tests ejecutados.** Compilar Swift y servir HTML no demuestra que los estados de producto se vean y funcionen como se acordó.

## Orden de corrección y condiciones de aceptación

1. **Estado visual fiable:** hidden, menú y estilos de formulario. Idle no muestra grabación; live sí; login no muestra historial. El menú permanece cerrado hasta interacción y no mueve la pantalla.
2. **Home útil:** carga, vacío, error y tareas con acción; CTA visible de escucha. Entrar con cero datos deja claro qué se puede hacer.
3. **Historial e idioma:** fechas/textos coherentes, duración honesta y estados legibles.
4. **Captura y checklist conectadas:** identidad persistida y evidencia real; capturar, interrumpir/red recuperada, parar y recuperar la misma reunión sin duplicar.
5. **Revisión según plan:** decisión CRM y seguimiento primero, campos plegados, errores y reintentos conservando el trabajo.
6. **Gate del artefacto distribuible:** compilar el paquete con trazabilidad de revisión/build y probar el recorrido en WKWebView, incluyendo tamaño mínimo, notas largas, cero tareas, fallo API y cambio de cuenta. Conservar pruebas de DOM/layout para D01/D02/D05 y un recorrido nativo para permisos/captura/bridge.

El criterio de cierre es que una persona pueda abrir Vocify, entender qué toca hacer, capturar con un estado fiable y terminar con el resultado y la siguiente acción claros. La mera existencia de paneles, endpoints o tests unitarios no acredita ese resultado.
