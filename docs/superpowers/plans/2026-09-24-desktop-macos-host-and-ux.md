# Vocify Desktop — host macOS nativo y UX estilo Granola: plan ejecutable

> **Para agentes:** SUB-SKILL OBLIGATORIA: `superpowers:subagent-driven-development` (recomendada) o `superpowers:executing-plans`. Una tarea cada vez, en orden. Cada paso usa casillas `- [ ]`. Antes de cada tarea, relee §0 y §1. Aplica `~/getvocify/.cursor/skills/vocify-ux-coherence/SKILL.md` en cada pantalla que toques.

**Objetivo:** una app de Mac instalable que se siente nativa (ventana, Dock, pastilla flotante, permisos, audio) y que dentro muestra exactamente los mismos componentes que el dashboard y la extensión (`shared/ui`), con una nota en vivo continua como Granola.

**Arquitectura:** el renderer actual de `desktop/renderer/` y `shared/ui` no se reescriben: solo hablan con su host a través de `window.vocifyDesktop` (hoy lo define `desktop/preload.cjs`). Un host SwiftUI nuevo en `desktop/macos/` sirve `desktop/renderer/` desde `http://127.0.0.1:<puerto>` a un `WKWebView` e implementa ese mismo objeto `window.vocifyDesktop` en Swift. Primero se arregla la UX del renderer (se prueba ya en Electron); después se cambia el host. Electron sigue funcionando hasta la tarea C1.

**Tech stack:** SwiftUI + AppKit (macOS 14+), WebKit (`WKWebView`, `WKScriptMessageHandlerWithReply`), Network.framework (`NWListener`), ScreenCaptureKit, AVFoundation; renderer en JS vanilla (módulos ES) con `node:test`; `shared/ui` sincronizado con `scripts/sync-shared.mjs`.

**Repo y rama:** worktree `/Users/danizal/getvocify/.worktrees/vocify-v1`, rama `feat/vocify-v1`. Todas las rutas de este plan son relativas a ese directorio salvo que digan lo contrario. `getvocify-desktop` (repo aparte) queda **fuera**: no se edita.

---

## 0. Reglas globales (valen para todas las tareas)

- **Una sola fuente de UI.** Cualquier pieza que ya exista en `shared/ui` se usa tal cual. No se reimplementa en Swift. Si falta algo compartido, se añade en `shared/ui`, se ejecuta `node scripts/sync-shared.mjs` y se commitea la copia.
- **Swift solo hace lo nativo:** ventana, menú, Dock, pastilla (`NSPanel`), permisos, captura de audio, archivo local de capturas, sesión segura, llamadas HTTP proxy.
- **Tokens:** colores, radios, sombras y tipografía salen de `desktop/renderer/theme.css`, alineado con `src/lib/theme/tokens.ts` y `src/lib/theme/materials.css` del dashboard. No se inventan valores nuevos.
- **Botones:** mismo lenguaje que `src/components/ui/button.tsx`: `rounded-full`, `font-normal`, altura 40 px (44 px solo la acción principal), `hover` con cambio de fondo, `active:scale(0.98)`, `focus-visible` con anillo, `cursor: pointer`, deshabilitado a 50 % de opacidad.
- **Texto:** ninguna frase explica lo obvio. Nada de «La misma cuenta del dashboard», «La transcripción aparece aquí», «Revisa las notas y aprueba». Máximo una línea de apoyo por pantalla, o ninguna.
- **Una acción principal por pantalla.** Nunca dos controles para lo mismo (p. ej. círculo que para + botón «Parar»).
- **Transcripción:** un párrafo por hablante; el tramo provisional va en gris al final del mismo párrafo y se sustituye en sitio; nunca una fila por chunk.
- **Estados diseñados:** vacío, carga (espacio reservado, sin saltos), error (qué falla + cómo seguir) en cada pantalla.
- **Idioma:** textos visibles vía `shared/ui/i18n.js` (`strings(lang)`), en español y en inglés. No se hardcodean cadenas en `app.js`.
- **Verificación:** ninguna tarea se da por hecha sin ejecutar sus comandos y pegar la salida en el informe `docs/superpowers/deliveries/DESKTOP-MAC/report.md`.
- **Commits:** uno por tarea, mensaje en inglés, en imperativo.

## 1. Recorrido (qué vive la persona)

Comercial entre llamadas, con prisa y la atención en la reunión.

1. **Instala:** abre el DMG y arrastra Vocify a Aplicaciones.
2. **Primera vez:** entra con email y contraseña. La sesión queda guardada.
3. **Antes de la reunión (reposo):** ve «Hoy» y, si hay contacto de HubSpot conocido, su brief.
4. **Empieza (momento crítico):** pulsa grabar. macOS pide micrófono y pantalla solo la primera vez. Si falta un permiso, lo sabe en el momento y tiene un botón que abre Ajustes.
5. **Durante:** la nota corre como texto continuo. La pastilla flotante sigue visible encima de Zoom/Meet, también en pantalla completa. La ayuda es opcional (apagada por defecto).
6. **Al parar (momento crítico):** la misma nota sigue arriba; debajo aparecen resumen, campos CRM, follow-up y Aprobar. Lo aprobado va al CRM.
7. **Después:** la reunión aparece en la lista lateral. Feedback y score viven en el dashboard (F09/F11); la nota enlaza allí.

## 2. Pantallas y peso visual

| Pantalla | Qué se ve | Acción principal | Qué NO aparece |
|---|---|---|---|
| Entrar | Marca pequeña, título «Entra para escuchar», email, contraseña, botón | Entrar | URL del API, textos de ayuda |
| Reposo | Lista lateral de notas · a la derecha: Hoy, brief (si hay contacto), control de grabar | Grabar | Etiquetas «EN REPOSO», reloj a 00:00 |
| En vivo | Nota continua (casi toda la ventana) · chip rojo con el tiempo · interruptor Ayuda pequeño · línea de ayuda si hay respaldo · checklist compacto | Parar (un solo control) | Segundo botón de parar, texto de estado |
| Pastilla | Stop · última frase o línea de ayuda · «N de M» del checklist | Parar | Otros botones salvo Ayuda |
| Al parar | Nota completa arriba · huecos reservados mientras extrae · resumen y siguientes pasos · deal y campos CRM con «Quitar» · `<v-followup>` · checklist del meeting | Aprobar | Pantalla vacía de carga |
| Nota anterior | Misma revisión en solo lectura + «Abrir en el dashboard» | — | Controles de edición |

Peso: grabar/parar, la nota y Aprobar son protagonistas. Hoy y brief pesan medio y solo en reposo. Ayuda, Salir, abrir dashboard: enlace o menú. Lista lateral: discreta, 220 px.

## 3. Edge cases (qué ve la persona y cómo sigue)

| Caso | Qué se ve | Cómo sigue |
|---|---|---|
| Primera vez, sin notas | Lista lateral vacía sin texto; a la derecha solo el control de grabar | Pulsa grabar |
| Sin permiso de micrófono | Línea «Falta el micrófono» + botón «Abrir Ajustes» | Concede y vuelve a pulsar grabar |
| Sin permiso de pantalla | Graba igual con micrófono; aviso «Sin audio de la reunión» + «Abrir Ajustes» | Concede sin perder lo grabado |
| Red cortada en vivo | Chip «Sin conexión»; el audio sigue guardándose en local | Reconecta solo; al parar se reintenta el envío |
| App cerrada a mitad | Al abrir, la nota pendiente aparece la primera en la lista con «Enviar» | Un clic la envía (usa `capture:pending`) |
| Extracción falla | La nota sigue arriba; «No se pudo preparar. Reintentar» | Reintentar sin volver a grabar |
| Sesión caducada | Pantalla de entrar; la nota pendiente se conserva | Entra y se envía |
| Reunión larga (> 1 h) | La nota no se redibuja entera; scroll fluido; «Volver al directo» si subes | — |
| Sin playbook | Sin ayuda ni checklist; nada inventado | — |
| Parar sin texto | No se envía nada; aviso «No se oyó nada» | Volver a grabar |

## 4. Mapa de archivos

**Renderer (Parte A, se prueba ya en Electron):**
- Crear `desktop/lib/live-note.js` + `desktop/lib/live-note.test.js` — nota en vivo por hablante (committed/live).
- Crear `desktop/lib/notes-list.js` + `desktop/lib/notes-list.test.js` — filas de la lista lateral desde `GET /memos`.
- Crear `desktop/lib/session.js` + `desktop/lib/session.test.js` — decidir pantalla inicial y tratar 401.
- Modificar `desktop/renderer/index.html` — nueva estructura (lateral + contenido), fuera panel de permisos y botones sueltos.
- Modificar `desktop/renderer/app.js` — usar los tres módulos; una acción principal; estados.
- Modificar `desktop/renderer/styles.css` — interacción (hover, cursor, foco), layout lateral, nota continua.
- Modificar `shared/ui/i18n.js` + `shared/ui/i18n.test.js` — cadenas nuevas; luego `node scripts/sync-shared.mjs`.
- Modificar `desktop/renderer/overlay.html`, `desktop/renderer/overlay.js` — pastilla compacta.

**Host macOS (Parte B):**
- Crear `desktop/macos/Package.swift` — tres targets: `VocifyHostKit` (lógica sin UI, comprobable), `VocifyHost` (la app), `VocifyHostChecks` (comprobaciones; sustituye a XCTest, que no existe sin Xcode).
- Crear `desktop/macos/Sources/VocifyHost/App.swift` — ventana, Dock, menú.
- Crear `desktop/macos/Sources/VocifyHostKit/RendererServer.swift` — servidor estático en 127.0.0.1.
- Crear `desktop/macos/Sources/VocifyHostKit/SaasProxy.swift` — validación de host y petición HTTP.
- Crear `desktop/macos/Sources/VocifyHostChecks/main.swift` — comprobaciones de `VocifyHostKit`.
- Crear `desktop/macos/Sources/VocifyHost/WebShell.swift` — `WKWebView`, permisos de medios, puente.
- Crear `desktop/macos/Sources/VocifyHost/Bridge.swift` — implementa `window.vocifyDesktop`.
- Crear `desktop/macos/Sources/VocifyHost/bridge.js` (recurso) — el objeto JS que ve el renderer.
- Crear `desktop/macos/Sources/VocifyHost/SystemAudio.swift` — ScreenCaptureKit en proceso (portado de `desktop/native/macos-tap/main.swift`).
- Crear `desktop/macos/Sources/VocifyHost/Overlay.swift` — `NSPanel` con `overlay.html`.
- Crear `desktop/macos/Sources/VocifyHostKit/CaptureStore.swift` — mismo contrato que `desktop/lib/capture-store.js`.
- Crear `desktop/macos/Info.plist`, `desktop/macos/VocifyHost.entitlements`
- Crear `desktop/macos/scripts/build-app.sh`, `desktop/macos/scripts/package-dmg.sh`
- Modificar `.github/workflows/desktop-dmg.yml`, `desktop/README.md`

## 5. Contrato del puente (lo que el renderer ya usa)

Copiado de `desktop/preload.cjs`. El host Swift debe exponer **exactamente** esto:

```text
window.vocifyDesktop = {
  platform: 'darwin',
  systemAudio: { start(): Promise<{ok, backend?}>, stop(): Promise<void>, onPcm(cb:(ArrayBuffer)=>void): () => void },
  permissions: { status(): Promise<{microphone, systemAudio}>, request(type): Promise<any>, open(type): Promise<void> },
  shell: { setState(state): void, resize(size): Promise<void>, showOverlay(): Promise<void>, hideOverlay(): Promise<void>,
           openExternal(url): Promise<void>, command(name): void, onCommand(cb): () => void, onOverlayState(cb): () => void },
  saas: { request({base, path, method, headers, body}): Promise<{ok, status, data, error?}> },
  capture: { begin(p), append(p), channelAbsent(p), pending(), confirm(id), discard(id) }   // todas Promise
}
```

Valores de `permissions.status()`: `'granted' | 'denied' | 'not-determined'` (mismo formato que `desktop/lib/permissions.js` → `normalizeAccessStatus`). `type` es `'microphone' | 'systemAudio'` (constantes `PERMISSION` de `desktop/lib/permissions.js`).

---

# Parte 0 — Preparación

### Tarea 0: entorno y línea base

- [ ] **Paso 1:** Comprobar las herramientas de línea de comandos: `swift --version` (Swift 6.x). **No se instala Xcode.** Sin Xcode no hay `XCTest`: los tests Swift de este plan son un ejecutable `VocifyHostChecks` que termina con código 1 si una comprobación falla (ver B1).
- [ ] **Paso 2:** Railway ya está configurado (24 sep 2026): servicio `getvocify`, entornos `prod` y `production`, Watch Paths = `/backend/**`. Comprobar con el MCP de Railway (`get_service_config`) que sigue así; no cambiarlo.
- [ ] **Paso 3:** Línea base de tests:

```bash
cd desktop && npm install && npm test
cd .. && node --test shared/ui/*.test.js shared/ui/copilot/*.test.js
node scripts/sync-shared.mjs --check
```

Esperado: todo en verde. Si algo falla ya, anotarlo en el informe como «rojo previo» y no arreglarlo aquí.

- [ ] **Paso 4:** Crear `docs/superpowers/deliveries/DESKTOP-MAC/report.md` con la salida de los comandos.
- [ ] **Paso 5:** Commit `chore(desktop): record baseline for macOS host work`.

---

# Parte A — UX del renderer (se ve ya en Electron con `cd desktop && npm start`)

### Tarea A1: nota en vivo continua por hablante

**Archivos:** crear `desktop/lib/live-note.js`, `desktop/lib/live-note.test.js`; modificar `desktop/renderer/app.js` (función `renderTranscript`, el `onmessage` del WebSocket en `startListen`, `stopAndSend`), `desktop/renderer/styles.css`.

**Interfaces producidas:**
- `emptyNote(): { turns: Turn[] }`
- `applyChunk(note, { text: string, isFinal: boolean, speaker: 'rep'|'prospect'|'' }): Note` (pura, devuelve nota nueva)
- `noteUploadText(note, { you: string, them: string }): string`
- `latestFinal(note): string`
- `Turn = { speaker, committed, live }`

- [ ] **Paso 1: test que falla**

```js
// desktop/lib/live-note.test.js
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { applyChunk, emptyNote, latestFinal, noteUploadText } from './live-note.js';

const feed = (note, rows) => rows.reduce((n, r) => applyChunk(n, r), note);

describe('live note', () => {
  it('joins one-word finals from the same speaker into one paragraph', () => {
    const note = feed(emptyNote(), [
      { text: 'hola', isFinal: true, speaker: 'prospect' },
      { text: 'qué', isFinal: true, speaker: 'prospect' },
      { text: 'tal', isFinal: true, speaker: 'prospect' },
    ]);
    assert.equal(note.turns.length, 1);
    assert.equal(note.turns[0].committed, 'hola qué tal');
  });

  it('keeps interim as the live tail of the same paragraph and replaces it in place', () => {
    let note = feed(emptyNote(), [{ text: 'quedamos', isFinal: true, speaker: 'rep' }]);
    note = applyChunk(note, { text: 'el mar', isFinal: false, speaker: 'rep' });
    note = applyChunk(note, { text: 'el martes', isFinal: false, speaker: 'rep' });
    assert.equal(note.turns.length, 1);
    assert.equal(note.turns[0].live, 'el martes');
    note = applyChunk(note, { text: 'el martes', isFinal: true, speaker: 'rep' });
    assert.equal(note.turns[0].committed, 'quedamos el martes');
    assert.equal(note.turns[0].live, '');
  });

  it('opens a new paragraph only when the known speaker changes', () => {
    const note = feed(emptyNote(), [
      { text: 'hola', isFinal: true, speaker: 'rep' },
      { text: 'buenas', isFinal: true, speaker: '' },
      { text: 'sí', isFinal: true, speaker: 'prospect' },
    ]);
    assert.equal(note.turns.length, 2);
    assert.equal(note.turns[0].committed, 'hola buenas');
  });

  it('does not duplicate a final that repeats the committed text', () => {
    const note = feed(emptyNote(), [
      { text: 'hola', isFinal: true, speaker: 'rep' },
      { text: 'hola qué tal', isFinal: true, speaker: 'rep' },
    ]);
    assert.equal(note.turns[0].committed, 'hola qué tal');
  });

  it('uploads committed and live text with speaker labels', () => {
    let note = feed(emptyNote(), [{ text: 'hola', isFinal: true, speaker: 'rep' }]);
    note = applyChunk(note, { text: 'vale', isFinal: false, speaker: 'prospect' });
    assert.equal(noteUploadText(note, { you: 'Tú', them: 'Cliente' }), 'Tú: hola Cliente: vale');
    assert.equal(latestFinal(note), 'hola');
  });
});
```

- [ ] **Paso 2:** `cd desktop && node --test lib/live-note.test.js` → FAIL (módulo no existe).
- [ ] **Paso 3: implementación**

```js
// desktop/lib/live-note.js
const squash = (s) => String(s || '').replace(/\s+/g, ' ').trim();
const join = (a, b) => squash(`${a} ${b}`);

export function emptyNote() {
  return { turns: [] };
}

function openTurn(turns, speaker) {
  const last = turns[turns.length - 1];
  const changed = last && speaker && last.speaker && speaker !== last.speaker;
  if (last && !changed) {
    if (speaker && !last.speaker) turns[turns.length - 1] = { ...last, speaker };
    return turns.length - 1;
  }
  turns.push({ speaker: speaker || '', committed: '', live: '' });
  return turns.length - 1;
}

export function applyChunk(note, { text, isFinal, speaker = '' }) {
  const piece = squash(text);
  if (!piece) return note;
  const turns = note.turns.map((t) => ({ ...t }));
  const i = openTurn(turns, speaker);
  const turn = turns[i];
  if (!isFinal) {
    turn.live = piece;
    return { turns };
  }
  if (!turn.committed || piece.startsWith(turn.committed)) turn.committed = piece;
  else turn.committed = join(turn.committed, piece);
  turn.live = '';
  return { turns };
}

export function noteUploadText(note, { you, them }) {
  return note.turns
    .map((t) => {
      const body = join(t.committed, t.live);
      if (!body) return '';
      const label = t.speaker === 'rep' ? you : t.speaker === 'prospect' ? them : '';
      return label ? `${label}: ${body}` : body;
    })
    .filter(Boolean)
    .join(' ');
}

export function latestFinal(note) {
  for (let i = note.turns.length - 1; i >= 0; i -= 1) {
    if (note.turns[i].committed) return note.turns[i].committed;
  }
  return '';
}
```

- [ ] **Paso 4:** `node --test lib/live-note.test.js` → PASS.
- [ ] **Paso 5: conectar en `app.js`.**
  - Añadir `let liveNote = emptyNote();` junto a `transcriptState`.
  - En `startListen`, al empezar: `liveNote = emptyNote();`.
  - En `websocket.onmessage`, después de calcular `text` e `isFinal`, mapear el hablante con `const speaker = data.audio_channel === 'rep' ? 'rep' : data.audio_channel === 'prospect' ? 'prospect' : '';` y hacer `liveNote = applyChunk(liveNote, { text, isFinal, speaker });`. Mantener `transcriptState = applyTranscriptUpdate(...)` solo para `overlaySnippet`.
  - Sustituir el cuerpo de `renderTranscript()` por un render que reutiliza nodos: un `<div class="v-transcript-turn">` por `turn`, con `<span class="speaker">` (texto `t.speakerYou`/`t.speakerThem`, vacío si no hay hablante), `<span class="committed">` y `<span class="live">`. Solo tocar `textContent` si cambió. Conservar `stickToLive` y `btn-return-live`.
  - En `requestCopilotSuggest`, usar `latestFinal(liveNote)` como `latestTurn`.
  - En `stopAndSend`, usar `noteUploadText(liveNote, { you: t.speakerYou, them: t.speakerThem })` como `transcript`.
- [ ] **Paso 6: CSS** en `desktop/renderer/styles.css`:

```css
.transcript .v-transcript-turn { display: block; margin: 0 0 18px; }
.transcript .v-transcript-turn .speaker { display: block; font-size: 12px; color: hsl(var(--muted-foreground)); margin-bottom: 4px; }
.transcript .v-transcript-turn .committed { color: hsl(var(--foreground)); font-size: 16px; line-height: 1.6; }
.transcript .v-transcript-turn .live { color: hsl(var(--muted-foreground)); font-size: 16px; line-height: 1.6; transition: opacity var(--motion-fast); }
.transcript .v-transcript-turn .committed:not(:empty) + .live:not(:empty)::before { content: ' '; }
@media (prefers-reduced-motion: reduce) { .transcript .v-transcript-turn .live { transition: none; } }
```

- [ ] **Paso 7: verificación manual** con `cd desktop && npm start`: grabar 30 s hablando en frases cortas. Captura de pantalla en el informe. Criterio: nunca hay una fila por palabra; lo provisional es gris al final del mismo párrafo.
- [ ] **Paso 8:** `npm test` en verde. Commit `feat(desktop): render the live note as one paragraph per speaker`.

### Tarea A2: interacción y estilo de controles igual que el dashboard

**Archivos:** `desktop/renderer/styles.css`.

- [ ] **Paso 1:** Sustituir las reglas de `button`, `button.primary`, `button.ghost`, `button.danger` por:

```css
button {
  height: 40px; padding: 0 16px; border: 0; border-radius: var(--radius-pill);
  font: inherit; font-size: 14px; font-weight: 400; letter-spacing: 0.01em;
  cursor: pointer; transition: background-color var(--motion-fast), color var(--motion-fast), transform var(--motion-fast), opacity var(--motion-fast);
}
button:focus-visible { outline: none; box-shadow: 0 0 0 2px hsl(var(--background)), 0 0 0 4px hsl(var(--ring)); }
button:active:not(:disabled) { transform: scale(0.98); }
button:disabled { opacity: 0.5; cursor: default; }
button.primary { height: 44px; width: 100%; background: hsl(var(--beige)); color: hsl(var(--cream)); }
button.primary:hover:not(:disabled) { background: hsl(var(--beige) / 0.9); }
button.ghost { background: transparent; color: hsl(var(--muted-foreground)); }
button.ghost:hover:not(:disabled) { background: hsl(var(--muted)); color: hsl(var(--foreground)); }
button.danger { background: hsl(var(--destructive)); color: #fff; }
button.danger:hover:not(:disabled) { background: hsl(var(--destructive) / 0.9); }
a, [role="button"], summary { cursor: pointer; }
```

- [ ] **Paso 2:** Añadir el control de grabar (círculo del dashboard, `VoiceRecorderWidget.tsx` líneas del estado idle):

```css
.record-core { width: 80px; height: 80px; padding: 0; border-radius: 999px; display: grid; place-items: center;
  background: rgb(255 255 255 / 0.7); border: 1px solid rgb(255 255 255 / 0.7); box-shadow: var(--shadow-float); }
.record-core:hover:not(:disabled) { transform: scale(1.05); border-color: hsl(var(--beige) / 0.4); }
.record-core .dot { width: 28px; height: 28px; border-radius: 999px; background: hsl(var(--beige)); transition: transform var(--motion-fast); }
.record-core:hover .dot { transform: scale(1.1); }
.record-core.live .dot { width: 16px; height: 16px; border-radius: 3px; background: hsl(var(--destructive)); }
```

- [ ] **Paso 3:** Verificación manual: pasar el ratón por cada botón. Criterio: cursor de mano, cambio de fondo y anillo de foco con Tab. Captura en el informe.
- [ ] **Paso 4:** Commit `style(desktop): match dashboard button interaction and record control`.

### Tarea A3: estructura de ventana (lista lateral + contenido) y una sola acción

**Archivos:** `desktop/renderer/index.html`, `desktop/renderer/app.js` (`showScreen`, `enterApp`, `setLiveUi`, listeners de `btn-listen`/`btn-stop`), `desktop/renderer/styles.css`, crear `desktop/lib/notes-list.js` + test, `shared/ui/i18n.js`.

**Interfaces producidas:**
- `noteRows(memos: Memo[], { now: number, lang: string }): { id, title, when, minutes, pending: boolean }[]`
- `notesRequestPath(): '/memos?limit=50'`

- [ ] **Paso 1: test**

```js
// desktop/lib/notes-list.test.js
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { noteRows, notesRequestPath } from './notes-list.js';

describe('notes list', () => {
  const now = Date.parse('2026-09-24T12:00:00Z');
  it('titles a memo by contact, then company, then date', () => {
    const rows = noteRows([
      { id: 'a', createdAt: '2026-09-24T10:00:00Z', audioDuration: 1800, status: 'approved', extraction: { contactName: 'Ana Ruiz' } },
      { id: 'b', createdAt: '2026-09-23T09:00:00Z', audioDuration: 60, status: 'pending_review', extraction: { companyName: 'Acme' } },
      { id: 'c', createdAt: '2026-09-20T09:05:00Z', audioDuration: 0, status: 'extracting', extraction: null },
    ], { now, lang: 'es' });
    assert.equal(rows[0].title, 'Ana Ruiz');
    assert.equal(rows[1].title, 'Acme');
    assert.match(rows[2].title, /20/);
    assert.equal(rows[0].minutes, 30);
    assert.equal(rows[1].pending, true);
    assert.equal(rows[0].pending, false);
  });
  it('reads the latest 50 memos', () => {
    assert.equal(notesRequestPath(), '/memos?limit=50');
  });
});
```

- [ ] **Paso 2:** `node --test lib/notes-list.test.js` → FAIL.
- [ ] **Paso 3: implementación**

```js
// desktop/lib/notes-list.js
const PENDING = new Set(['pending_review', 'uploading', 'transcribing', 'extracting', 'pending_transcript']);

function dateLabel(iso, lang) {
  const d = new Date(iso);
  return d.toLocaleString(lang === 'en' ? 'en-GB' : 'es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export function noteRows(memos, { lang = 'es' } = {}) {
  return (Array.isArray(memos) ? memos : []).map((m) => {
    const x = m.extraction || {};
    const title = String(x.contactName || x.companyName || '').trim() || dateLabel(m.createdAt, lang);
    return {
      id: String(m.id),
      title,
      when: dateLabel(m.createdAt, lang),
      minutes: Math.round(Number(m.audioDuration || 0) / 60),
      pending: PENDING.has(String(m.status || '')),
    };
  });
}

export function notesRequestPath() {
  return '/memos?limit=50';
}
```

- [ ] **Paso 4:** PASS.
- [ ] **Paso 5: HTML.** Reemplazar el `<div class="app">` por:

```html
<div class="app-shell">
  <aside id="notes-rail" class="notes-rail" hidden>
    <button id="btn-new-note" class="ghost rail-new" type="button" data-i18n="desktopNewNote"></button>
    <nav id="notes-list" class="notes-list" aria-label="Notas"></nav>
  </aside>
  <main class="app">
    <header class="topbar">
      <div class="brand-lockup"><img class="brand-mark" src="./icon.png" alt="Vocify" /><span class="wordmark">Vocify</span></div>
      <details id="account-menu" class="account-menu" hidden>
        <summary id="session-chip" class="chip"></summary>
        <button id="btn-dashboard" class="ghost" type="button" data-i18n="desktopOpenDashboard"></button>
        <button id="btn-logout" class="ghost" type="button" data-i18n="desktopLogout"></button>
      </details>
    </header>
    <!-- login-panel, listen-panel, review-panel van aquí (ver pasos 6–8) -->
  </main>
</div>
```

- [ ] **Paso 6: login-panel.** Quitar `<p class="caps">`, `<p class="lede">` y `<details class="advanced">`. Dejar título, email, contraseña, botón y error. La URL del API se lee de `localStorage` o `PROD_API`; `document.getElementById('api-base')` deja de existir: en `apiBase()` sustituir por `(localStorage.getItem(STORAGE.api) || PROD_API)`.
- [ ] **Paso 7: permissions-panel.** Eliminar el panel entero. Los permisos se piden en `startListen` (ya existe `permissionGate()`); si el gate falla, mostrar en `#listen-error` el texto de `startDeniedMessage(gate.reason, { platform, lang })` (ya existe en `desktop/lib/listen-policy.js`, razones `no_mic` y `no_system_audio`) y un botón `ghost` con `t.desktopOpenSettings` que llama `desktop().permissions.open(type)` (`PERMISSION.microphone` para `no_mic`, `PERMISSION.systemAudio` para `no_system_audio`).
- [ ] **Paso 8: listen-panel.** Estructura:

```html
<section id="listen-panel" hidden>
  <div id="idle-block" class="idle-block">
    <div id="home-hoy"></div>
    <div id="contact-brief" class="v-paper" hidden></div>
  </div>
  <div id="live-chip" class="live-chip" hidden><span class="pulse-dot live"></span><span id="timer">00:00</span></div>
  <div id="transcript" class="transcript" aria-live="polite"></div>
  <button id="btn-return-live" class="v-transcript-jump ghost" type="button" hidden data-i18n="transcriptBackToLive"></button>
  <p id="assist-line" class="assist-line" hidden></p>
  <div id="live-checklist" class="overlay-checklist" hidden></div>
  <div class="record-row">
    <button id="btn-record" class="record-core" type="button" aria-label=""><span class="dot"></span></button>
    <label id="assist-toggle" class="assist-toggle" hidden><input type="checkbox" id="assist-input" /> <span data-i18n="helpOn"></span></label>
  </div>
  <p id="listen-error" class="error" hidden></p>
</section>
```

`btn-listen` y `btn-stop` desaparecen. Un solo listener en `btn-record`: si `listening`, `stopAndSend()`; si no, `startListen()`. `setLiveUi(on)` alterna `.live` en `btn-record`, muestra `live-chip` y `assist-toggle`, oculta `idle-block`, y pone `aria-label` con `t.listenIdleButton` / `t.desktopStopReview`. El interruptor Ayuda envía los mismos comandos que la pastilla (`assist-on` / `assist-off`).
- [ ] **Paso 9: lista lateral.** En `enterApp()`, mostrar `notes-rail`, llamar `request(notesRequestPath(), { token })`, pintar con `noteRows` (botón por fila: título, `when`, minutos; punto si `pending`). Clic en una fila → `openReview(id, { readOnly: memo.status === 'approved' })`. `btn-new-note` → `showScreen('listen')`. Vacío: lista vacía sin texto.
- [ ] **Paso 10: CSS de layout**

```css
.app-shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.app-shell:has(.notes-rail[hidden]) { grid-template-columns: 1fr; }
.notes-rail { border-right: 1px solid hsl(var(--hairline)); padding: 42px 10px 16px; display: flex; flex-direction: column; gap: 8px; }
.notes-list button { width: 100%; height: auto; text-align: left; padding: 8px 10px; border-radius: 10px; background: transparent; color: hsl(var(--foreground)); }
.notes-list button:hover, .notes-list button[aria-current="true"] { background: hsl(var(--muted)); }
.notes-list .meta { display: block; font-size: 12px; color: hsl(var(--muted-foreground)); }
.idle-block { display: grid; gap: 12px; margin-bottom: 20px; }
.live-chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; background: hsl(var(--destructive) / 0.1); color: hsl(var(--destructive)); font-size: 13px; }
.record-row { display: flex; align-items: center; justify-content: center; gap: 16px; margin-top: 20px; }
.assist-line { color: hsl(var(--beige)); font-size: 15px; margin: 12px 0 0; }
```

- [ ] **Paso 11: i18n.** En `shared/ui/i18n.js` añadir en `es` y `en`: `desktopNewNote` («Nueva nota» / «New note»), `desktopOpenDashboard` («Abrir en el dashboard» / «Open in dashboard»), `desktopLogout` («Salir» / «Log out»), `transcriptBackToLive` («Volver al directo» / «Back to live»), `desktopOpenSettings` («Abrir Ajustes» / «Open Settings»), `desktopNothingHeard` («No se oyó nada» / «Nothing was heard»), `desktopOffline` («Sin conexión» / «Offline»), `desktopRetry` («Reintentar» / «Retry»), `desktopPrepareFailed` («No se pudo preparar» / «Could not prepare»), `desktopNoMeetingAudio` («Sin audio de la reunión» / «No meeting audio»). Añadir un test en `shared/ui/i18n.test.js` que compruebe que cada clave existe en los dos idiomas. Ejecutar `node scripts/sync-shared.mjs`.
- [ ] **Paso 12:** `npm test`, `node --test shared/ui/*.test.js`, `node scripts/sync-shared.mjs --check` en verde. Captura de reposo, en vivo y lista lateral en el informe. Commit `feat(desktop): notes rail and a single record control`.

### Tarea A4: revisión que continúa la nota

**Archivos:** `desktop/renderer/index.html` (`review-panel`), `desktop/renderer/app.js` (`openReview`, `stopAndSend`, `approveReview`), `desktop/renderer/styles.css`.

- [ ] **Paso 1:** Orden del `review-panel`: `#review-note` (misma nota, solo lectura, reutiliza el render de A1) → `#review-summary` y `#review-next` (textareas) → `#review-deal`/`#review-deals`/`#review-fields` (ya existen) → `<v-followup id="review-followup">` → `#review-checklist` → `btn-approve`. Quitar `btn-review-back`: volver es la lista lateral o «Nueva nota».
- [ ] **Paso 2:** En `stopAndSend`, **antes** de subir: `showScreen('review')`, pintar la nota y poner `data-loading="true"` en `review-panel`. CSS: `[data-loading="true"] .review-slot { min-height: 96px; background: hsl(var(--muted)); border-radius: 12px; animation: pulse 1.4s ease-in-out infinite; }` con `@media (prefers-reduced-motion: reduce) { animation: none; }`. Los textareas y campos llevan la clase `review-slot` mientras carga.
- [ ] **Paso 3:** Si la subida o `waitForReview` fallan: la nota sigue, `#review-error` muestra `t.desktopPrepareFailed` y un botón `ghost` `t.desktopRetry` que vuelve a llamar la misma función con el mismo texto. No volver a la pantalla de grabar.
- [ ] **Paso 4:** Si `noteUploadText` está vacío al parar: no subir, mostrar `t.desktopNothingHeard` en `#listen-error` y quedarse en grabar.
- [ ] **Paso 5:** Modo `readOnly` (nota ya aprobada): textareas `readonly`, sin «Quitar», `btn-approve` oculto, enlace `ghost` `t.desktopOpenDashboard` a `dashboardMemosUrl(apiBase())` + `/${memoId}`.
- [ ] **Paso 6:** Verificación manual: grabar, parar, ver huecos reservados, ver revisión, aprobar. Forzar fallo apagando la wifi al parar y comprobar Reintentar. Capturas en el informe.
- [ ] **Paso 7:** Commit `feat(desktop): keep the note on screen through review`.

### Tarea A5: sesión y errores de red

**Archivos:** crear `desktop/lib/session.js` + test; modificar `desktop/renderer/app.js` (arranque, `request`).

**Interfaces producidas:** `isSessionError({ status, detail }): boolean`, `startScreen({ hasToken, meOk }): 'login'|'listen'`.

- [ ] **Paso 1: test**

```js
// desktop/lib/session.test.js
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { isSessionError, startScreen } from './session.js';

describe('session', () => {
  it('treats 401 and expired-session details as a lost session', () => {
    assert.equal(isSessionError({ status: 401 }), true);
    assert.equal(isSessionError({ status: 400, detail: 'Invalid or expired session' }), true);
    assert.equal(isSessionError({ status: 500, detail: 'boom' }), false);
  });
  it('shows login unless a stored token passes /auth/me', () => {
    assert.equal(startScreen({ hasToken: false, meOk: false }), 'login');
    assert.equal(startScreen({ hasToken: true, meOk: false }), 'login');
    assert.equal(startScreen({ hasToken: true, meOk: true }), 'listen');
  });
});
```

- [ ] **Paso 2:** FAIL. **Paso 3:** implementación:

```js
// desktop/lib/session.js
export function isSessionError({ status, detail } = {}) {
  if (status === 401) return true;
  return /session|sign in again|authorization token/i.test(String(detail || ''));
}

export function startScreen({ hasToken, meOk }) {
  return hasToken && meOk ? 'listen' : 'login';
}
```

- [ ] **Paso 4:** PASS. **Paso 5:** Al arrancar, si hay token, llamar `request('/auth/me', { token })`; con `startScreen` decidir. En `request`, si `isSessionError(...)`: borrar `STORAGE.token`, `showScreen('login')`, **sin** borrar capturas pendientes (siguen en `capture.pending()`). Tras entrar de nuevo, si hay pendientes, la primera fila de la lista las ofrece con «Enviar».
- [ ] **Paso 6:** Durante la grabación, `websocket.onclose` inesperado: mostrar `live-chip` con `t.desktopOffline` y reintentar la conexión cada 2 s hasta 5 veces; el audio sigue yendo a `capture.append`.
- [ ] **Paso 7:** `npm test` verde. Commit `fix(desktop): recover from expired sessions and dropped sockets`.

### Tarea A6: pastilla compacta

**Archivos:** `desktop/renderer/overlay.html`, `desktop/renderer/overlay.js`, `desktop/renderer/styles.css`, `desktop/lib/shell.js` (tamaño en `overlayBoundsForState`, con su test en `desktop/lib/shell.test.js`).

- [ ] **Paso 1:** `overlay.html`: `.overlay-pill` con `#overlay-stop` como círculo `record-core live` de 36 px, `#overlay-line` (una línea, elipsis), `#overlay-checklist` compacto («N de M») y `#overlay-assist` como `ghost` pequeño. Quitar `#overlay-label`.
- [ ] **Paso 2:** Posición abajo a la derecha, 24 px del borde, 340×64 px. Actualizar `overlayBoundsForState` y su test para esos valores.
- [ ] **Paso 3:** Doble clic en la pastilla → `shell.command('show')` (ya existe). Mantener las reglas de `pillDecision`.
- [ ] **Paso 4:** Verificación manual con Zoom en pantalla completa: la pastilla se ve y para. Captura en el informe.
- [ ] **Paso 5:** Commit `feat(desktop): compact floating pill`.

**Puerta de revisión Parte A:** pasar el checklist §5 de `vocify-ux-coherence` sobre las capturas. Si algún punto falla, se arregla antes de la Parte B.

---

# Parte B — Host macOS nativo

### Tarea B1: esqueleto del host y servidor del renderer

**Archivos:** crear `desktop/macos/Package.swift`, `Sources/VocifyHost/App.swift`, `Sources/VocifyHostKit/RendererServer.swift`, `Sources/VocifyHostChecks/main.swift`.

**Interfaces producidas:** `public final class RendererServer` con `public init(root: URL)`, `public func start() throws -> URL` (devuelve `http://127.0.0.1:<puerto>/`), `public func stop()`, `public static func mime(for path: String) -> String`.

**Comprobaciones sin Xcode:** `swift run VocifyHostChecks` ejecuta todas las comprobaciones y sale con código 1 en el primer fallo. Es el equivalente a `swift test` en este plan.

- [ ] **Paso 1:** `Package.swift`:

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "VocifyHost",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "VocifyHostKit"),
        .executableTarget(name: "VocifyHost", dependencies: ["VocifyHostKit"], resources: [.copy("bridge.js")]),
        .executableTarget(name: "VocifyHostChecks", dependencies: ["VocifyHostKit"]),
    ]
)
```

- [ ] **Paso 2: comprobaciones que fallan**

```swift
// desktop/macos/Sources/VocifyHostChecks/main.swift
import Foundation
import VocifyHostKit

func check(_ ok: Bool, _ name: String) {
    if ok { print("ok  \(name)") } else { fputs("FAIL \(name)\n", stderr); exit(1) }
}

func tempDir() throws -> URL {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir
}

// RendererServer
do {
    let dir = try tempDir()
    try "<p>ok</p>".write(to: dir.appendingPathComponent("index.html"), atomically: true, encoding: .utf8)
    let server = RendererServer(root: dir)
    let base = try server.start()
    let (data, response) = try await URLSession.shared.data(from: base.appendingPathComponent("index.html"))
    let http = response as? HTTPURLResponse
    check(http?.value(forHTTPHeaderField: "Content-Type") == "text/html; charset=utf-8", "server html type")
    check(String(data: data, encoding: .utf8) == "<p>ok</p>", "server html body")
    let (_, escape) = try await URLSession.shared.data(from: URL(string: "\(base.absoluteString)../etc/hosts")!)
    check((escape as? HTTPURLResponse)?.statusCode == 404, "server refuses traversal")
    server.stop()
}
check(RendererServer.mime(for: "a.js") == "text/javascript; charset=utf-8", "mime js")
check(RendererServer.mime(for: "a.css") == "text/css; charset=utf-8", "mime css")
check(RendererServer.mime(for: "a.png") == "image/png", "mime png")

print("all checks passed")
```

- [ ] **Paso 3:** `cd desktop/macos && swift run VocifyHostChecks` → falla al compilar (no existe `RendererServer`).
- [ ] **Paso 4: implementación** `Sources/VocifyHostKit/RendererServer.swift` (tipos y métodos `public`) con `NWListener` en `127.0.0.1`, puerto 0 (el sistema elige), respuesta HTTP/1.1 mínima: lee la primera línea `GET <ruta>`, decodifica `%XX`, resuelve contra `root` con `standardizedFileURL`, rechaza (404) si el resultado no empieza por `root.path`, sirve el archivo con `Content-Type` de `mime(for:)`, `Cache-Control: no-store`, cierra la conexión. `start()` espera al estado `.ready` con un semáforo (máx. 2 s) y devuelve `http://127.0.0.1:\(port)/`. Tipos: `.html` `text/html; charset=utf-8`, `.js`/`.mjs` `text/javascript; charset=utf-8`, `.css` `text/css; charset=utf-8`, `.json` `application/json; charset=utf-8`, `.png` `image/png`, `.svg` `image/svg+xml`, resto `application/octet-stream` (misma tabla que `desktop/lib/launch.js` → `mimeFor`). Crear también `Sources/VocifyHost/App.swift` mínimo (ventana vacía) para que el target compile.
- [ ] **Paso 5:** `swift run VocifyHostChecks` → `all checks passed`. Commit `feat(desktop-mac): serve the renderer from a loopback server`.

Nota: el backend ya acepta `http://127.0.0.1:<puerto>` en CORS (`backend/app/main.py`, `allow_origin_regex`). No tocar el backend.

### Tarea B2: ventana con `WKWebView` y puente `window.vocifyDesktop`

**Archivos:** crear `Sources/VocifyHost/WebShell.swift`, `Sources/VocifyHost/Bridge.swift`, `Sources/VocifyHost/bridge.js`, `Sources/VocifyHostKit/SaasProxy.swift`; modificar `App.swift` y `Sources/VocifyHostChecks/main.swift`.

**Interfaces producidas:**
- `bridge.js` define `window.vocifyDesktop` con la forma de §5. Llamadas con respuesta: `window.webkit.messageHandlers.vocify.postMessage({ op, args })` → `Promise` (handler con reply). Eventos del host: `window.__vocifyEmit(channel, payload)`.
- `public enum SaasProxy` (en `VocifyHostKit`) con `public static func isAllowedApiBase(_ base: String) -> Bool` y `public static func request(_ payload: [String: Any]) async -> [String: Any]`.
- `final class Bridge: NSObject, WKScriptMessageHandlerWithReply` (en `VocifyHost`) con `func handle(op: String, args: [String: Any]) async -> Any?` y `func emit(_ channel: String, _ payload: Any, in webView: WKWebView)`. `saas:request` delega en `SaasProxy.request`.

- [ ] **Paso 1: `bridge.js` completo**

```js
(() => {
  const call = (op, args = {}) => window.webkit.messageHandlers.vocify.postMessage({ op, args });
  const listeners = { 'system-audio:pcm': new Set(), 'shell:command': new Set(), 'overlay:state': new Set() };
  const on = (channel) => (cb) => { listeners[channel].add(cb); return () => listeners[channel].delete(cb); };
  window.__vocifyEmit = (channel, payload) => {
    const set = listeners[channel];
    if (!set) return;
    const value = channel === 'system-audio:pcm'
      ? Uint8Array.from(atob(payload), (c) => c.charCodeAt(0)).buffer
      : payload;
    set.forEach((cb) => cb(value));
  };
  window.vocifyDesktop = {
    platform: 'darwin',
    systemAudio: { start: () => call('system-audio:start'), stop: () => call('system-audio:stop'), onPcm: on('system-audio:pcm') },
    permissions: { status: () => call('permissions:status'), request: (type) => call('permissions:request', { type }), open: (type) => call('permissions:open', { type }) },
    shell: {
      setState: (state) => { call('shell:state', { state }); },
      resize: (size) => call('shell:resize', { size }),
      showOverlay: () => call('overlay:show'),
      hideOverlay: () => call('overlay:hide'),
      openExternal: (url) => call('shell:open-external', { url }),
      command: (name) => { call('shell:command', { name }); },
      onCommand: on('shell:command'),
      onOverlayState: on('overlay:state'),
    },
    saas: { request: (payload) => call('saas:request', { payload }) },
    capture: {
      begin: (payload) => call('capture:begin', { payload }),
      append: (payload) => call('capture:append', { payload }),
      channelAbsent: (payload) => call('capture:channel-absent', { payload }),
      pending: () => call('capture:pending'),
      confirm: (id) => call('capture:confirm', { id }),
      discard: (id) => call('capture:discard', { id }),
    },
  };
})();
```

Se inyecta como `WKUserScript` con `injectionTime: .atDocumentStart`, `forMainFrameOnly: true`, antes de cargar la página.

- [ ] **Paso 2: `SaasProxy.request`** en `VocifyHostKit/SaasProxy.swift`: validar `base` con las mismas reglas que `desktop/lib/saas.js` → `isAllowedApiBase` (solo `https://api.getvocify.com` o `http(s)://localhost|127.0.0.1`); si no, devolver `["ok": false, "status": 0, "data": [:], "error": "API base is not a Vocify host"]`. Si vale, `URLSession` con `method`, `headers`, `body` JSON; devolver `["ok": 2xx, "status": code, "data": json ?? [:]]`.
- [ ] **Paso 3: comprobaciones** — añadir en `VocifyHostChecks/main.swift`, antes de `print("all checks passed")`:

```swift
// SaasProxy
check(SaasProxy.isAllowedApiBase("https://api.getvocify.com/api/v1"), "api host allowed")
check(SaasProxy.isAllowedApiBase("http://localhost:8888/api/v1"), "localhost allowed")
check(!SaasProxy.isAllowedApiBase("http://api.getvocify.com/api/v1"), "plain http prod refused")
check(!SaasProxy.isAllowedApiBase("https://evil.example"), "foreign host refused")
do {
    let result = await SaasProxy.request(["base": "https://evil.example", "path": "/auth/me", "method": "GET"])
    check(result["ok"] as? Bool == false, "foreign request not sent")
    check(result["error"] as? String == "API base is not a Vocify host", "foreign request error text")
}
```

Ejecutar `swift run VocifyHostChecks` → falla (no existe `SaasProxy`). Implementar y repetir → pasa.

- [ ] **Paso 4:** `WebShell.swift`: `WKWebViewConfiguration` con `userContentController.addScriptMessageHandler(bridge, contentWorld: .page, name: "vocify")`, el `WKUserScript` de `bridge.js`, `preferences.isElementFullscreenEnabled = false`, `webView.uiDelegate` que en `webView(_:requestMediaCapturePermissionFor:initiatedByFrame:type:decisionHandler:)` responde `.grant` solo si `origin.host == "127.0.0.1"`. Cargar `serverBase.appendingPathComponent("renderer/index.html")` sirviendo como raíz la carpeta `desktop/` del bundle (ver B7). Fondo de ventana `#f7f4ee` mientras carga, sin destello blanco (`webView.setValue(false, forKey: "drawsBackground")`).
- [ ] **Paso 5:** `App.swift`: `@main` SwiftUI `App` con `WindowGroup` de 900×720 (mínimo 720×600), `.windowStyle(.hiddenTitleBar)`, contenido = `WebShell` envuelto en `NSViewRepresentable`. `NSApp.setActivationPolicy(.regular)`. Menú: «Vocify» (Acerca de, Salir), «Nota» (Nueva nota ⌘N → `emit("shell:command", "show")`, Grabar/Parar ⌘R → `emit("shell:command", "listen"|"stop")`).
- [ ] **Paso 6:** `swift run VocifyHostChecks` pasa; `swift run VocifyHost` con `VOCIFY_RENDERER_ROOT=$(pwd)/..` (en desarrollo, raíz = `desktop/`). Criterio: se ve el login del renderer y entrar funciona. Captura en el informe.
- [ ] **Paso 7:** Commit `feat(desktop-mac): host the renderer and expose vocifyDesktop`.

### Tarea B3: micrófono dentro del `WKWebView` (comprobación obligatoria)

El renderer captura el micrófono con `getUserMedia` + `AudioContext({ sampleRate: 16000 })` + `ScriptProcessor` (`startListen`/`hookPcm` en `app.js`). Hay que confirmar que funciona en WebKit.

- [ ] **Paso 1:** Con el host de B2, pulsar grabar y hablar 20 s con solo el micrófono.
- [ ] **Paso 2: criterio de aceptación.** Aparece texto en la nota y `AudioContext.sampleRate === 16000` (comprobar con Web Inspector: `defaults write com.vocify.companion WebKitDeveloperExtras -bool true` y `webView.isInspectable = true`).
- [ ] **Paso 3: si falla** (sin permiso, `sampleRate` ignorado o sin audio): implementar micrófono nativo. Añadir al puente `mic: { start, stop, onPcm }` con el mismo formato que `systemAudio` (Int16 mono 16 kHz, base64 por evento), capturado con `AVAudioEngine` + `AVAudioConverter`. En `app.js`, en `startListen`, si `desktop()?.mic?.start` existe, usarlo en lugar de `getUserMedia` y conectar `desktop().mic.onPcm((pcm) => send('rep')(pcm))`. Test en `desktop/lib/listen-policy.test.js` de la función que elige la fuente (`micSource({ hasNativeMic })` → `'native' | 'web'`).
- [ ] **Paso 4:** Anotar en el informe cuál de los dos caminos quedó y por qué. Commit `feat(desktop-mac): microphone capture in the host`.

### Tarea B4: audio del sistema en proceso

**Archivos:** crear `Sources/VocifyHost/SystemAudio.swift`; modificar `Bridge.swift`.

- [ ] **Paso 1:** Portar `SystemAudioTap` de `desktop/native/macos-tap/main.swift` a una clase del host (sin proceso aparte): ScreenCaptureKit, `capturesAudio = true`, `excludesCurrentProcessAudio = true`, 16 kHz mono, frames 2×2. Cada buffer se convierte a Int16 LE (misma conversión que el tap actual) y se emite con `bridge.emit("system-audio:pcm", base64)`.
- [ ] **Paso 2:** `system-audio:start` devuelve `["ok": true, "backend": "screencapturekit"]`; si falta el permiso o falla, `["ok": false, "reason": "no_system_audio"]` y el renderer muestra `t.desktopNoMeetingAudio` + «Abrir Ajustes» (A3 paso 7), siguiendo con micrófono.
- [ ] **Paso 3: permisos.** `permissions:status`: micrófono con `AVCaptureDevice.authorizationStatus(for: .audio)`, pantalla con `CGPreflightScreenCaptureAccess()`; mapear a `'granted' | 'denied' | 'not-determined'`. `permissions:request`: `AVCaptureDevice.requestAccess` / `CGRequestScreenCaptureAccess()`. `permissions:open`: abrir `x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone` o `?Privacy_ScreenCapture`.
- [ ] **Paso 4: verificación manual** con una llamada de Meet de prueba (otro dispositivo habla): el texto del otro aparece con la etiqueta del cliente. Captura en el informe.
- [ ] **Paso 5:** Commit `feat(desktop-mac): capture meeting audio in process`.

### Tarea B5: pastilla flotante nativa

**Archivos:** crear `Sources/VocifyHost/Overlay.swift`; modificar `Bridge.swift`.

- [ ] **Paso 1:** `NSPanel` sin borde, `.nonactivatingPanel`, `level = .statusBar`, `collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]`, fondo transparente, 340×64, abajo a la derecha (24 px). Contiene un segundo `WKWebView` con el mismo `bridge.js` que carga `renderer/overlay.html` del mismo servidor.
- [ ] **Paso 2:** `shell:state` desde la ventana principal → guardar estado y `emit("overlay:state", state)` en la vista de la pastilla. `shell:command` desde cualquiera de las dos → `emit("shell:command", name)` en la principal; `show` además trae la ventana al frente. `overlay:show` / `overlay:hide` → `orderFrontRegardless()` / `orderOut(nil)`.
- [ ] **Paso 3: verificación manual** con Zoom a pantalla completa: la pastilla se ve encima, Parar funciona y doble clic abre la ventana. Captura en el informe.
- [ ] **Paso 4:** Commit `feat(desktop-mac): native floating pill`.

### Tarea B6: guardado local de capturas

**Archivos:** crear `Sources/VocifyHostKit/CaptureStore.swift`; modificar `Sources/VocifyHostChecks/main.swift`.

**Contrato:** el mismo que `desktop/lib/capture-store.js` (`begin(clientCaptureId, meta)`, `append(clientCaptureId, channel, chunk)`, `pending()`, `confirm(id)`, `discard(id)`, error de disco lleno). Leer ese archivo completo antes de empezar y copiar las mismas claves de respuesta.

- [ ] **Paso 1: comprobaciones** en `VocifyHostChecks/main.swift` que reproduzcan cada `it(...)` de `desktop/lib/capture-store.test.js` («restart recovers», «transcription would disconnect», disco lleno), con los mismos datos de entrada y los mismos valores esperados, sobre `tempDir()`. Una llamada a `check` por aserción del test JS.
- [ ] **Paso 2:** FAIL → implementar en `~/Library/Application Support/Vocify/captures/<id>/` (un `meta.json` y un archivo por canal) → PASS.
- [ ] **Paso 3:** Conectar las seis operaciones `capture:*` del puente.
- [ ] **Paso 4: verificación manual:** grabar 30 s, forzar salida (`kill -9`), abrir: la nota pendiente aparece la primera con «Enviar». Captura en el informe.
- [ ] **Paso 5:** Commit `feat(desktop-mac): persist captures locally`.

### Tarea B7: bundle, icono, permisos declarados

**Archivos:** crear `desktop/macos/Info.plist`, `desktop/macos/VocifyHost.entitlements`, `desktop/macos/scripts/build-app.sh`.

- [ ] **Paso 1:** `Info.plist`: `CFBundleIdentifier com.vocify.companion`, `CFBundleName Vocify`, `CFBundleIconFile AppIcon`, `LSMinimumSystemVersion 14.0`, `NSMicrophoneUsageDescription` («Vocify escucha tu micrófono durante la reunión.»), `NSScreenCaptureUsageDescription` («Vocify oye el audio de Zoom, Meet o Teams. La pantalla no se guarda.»), `NSAudioCaptureUsageDescription` igual que la anterior.
- [ ] **Paso 2:** Entitlements: `com.apple.security.device.audio-input = true`, `com.apple.security.network.client = true`, `com.apple.security.network.server = true` (servidor loopback).
- [ ] **Paso 3: icono.** Desde `desktop/brand/icon-512.png`, generar `AppIcon.icns` con la plantilla de macOS: lienzo 1024×1024, cuadrado redondeado de 824×824 centrado (radio 185, color `#f7f4ee`, sombra suave), la marca dentro a 560×560. Tamaños con `sips` + `iconutil` (16, 32, 128, 256, 512 y @2x). Comprobar en el Dock que tiene el mismo tamaño aparente que Finder y Safari.
- [ ] **Paso 4:** `build-app.sh`: `swift build -c release`, crear `Vocify.app/Contents/{MacOS,Resources}`, copiar binario, `Info.plist`, `AppIcon.icns`, y la carpeta `desktop/renderer` (con `renderer/shared/ui` ya sincronizado) a `Resources/renderer`. El host usa `Bundle.main.resourceURL` como raíz del servidor cuando no hay `VOCIFY_RENDERER_ROOT`. Firma ad hoc: `codesign --force --deep --sign - --entitlements VocifyHost.entitlements Vocify.app`.
- [ ] **Paso 5:** Abrir `Vocify.app` desde Finder: entrar, grabar, parar, aprobar. Captura del Dock y de la ventana en el informe.
- [ ] **Paso 6:** Commit `build(desktop-mac): bundle the app with icon and privacy strings`.

### Tarea B8: DMG con marca

**Archivos:** crear `desktop/macos/scripts/package-dmg.sh`; reutilizar `desktop/build/dmg-background.png` si ya existe (si no, generarlo a 540×380 con el logo, «Arrastra Vocify a Aplicaciones» y las dos zonas de iconos).

- [ ] **Paso 1:** Crear un DMG de lectura/escritura con `Vocify.app`, alias `Applications` y `.background/background.png`; montarlo; con AppleScript de Finder fijar vista de iconos, sin barra de herramientas, ventana 540×380, icono 96 px, `Vocify.app` en (140, 190), `Applications` en (400, 190), fondo; desmontar; convertir a `UDZO` → `desktop/dist/Vocify-<versión>.dmg`. Debe ejecutarse en una sesión con Finder (no en un proceso sin GUI); si `hdiutil attach` da «Operation not permitted», ejecutarlo desde Terminal.app con permiso de Automatización para Finder.
- [ ] **Paso 2:** Abrir el DMG: fondo, logo, dos iconos en su sitio, texto sin tapar iconos. Captura en el informe.
- [ ] **Paso 3:** Commit `build(desktop-mac): branded dmg`.

---

# Parte C — Cierre

### Tarea C1: CI, README y retirada de Electron del instalador

- [ ] **Paso 1:** `.github/workflows/desktop-dmg.yml`: en `macos-latest`, ejecutar `cd desktop && npm ci && npm test`, `node scripts/sync-shared.mjs --check`, `cd desktop/macos && swift run VocifyHostChecks && bash scripts/build-app.sh && bash scripts/package-dmg.sh`; subir `desktop/dist/*.dmg`. Si el paso de Finder no puede ejecutarse en CI, el workflow usa `hdiutil create -srcfolder` (sin posiciones) y el DMG con marca se genera en local para cada versión.
- [ ] **Paso 2:** `desktop/README.md`: cómo arrancar en desarrollo (`cd desktop/macos && VOCIFY_RENDERER_ROOT=.. swift run VocifyHost`), cómo generar la app y el DMG, qué permisos pide y por qué.
- [ ] **Paso 3:** Dejar el código Electron sin tocar (se borra en otra entrega cuando Dani lo confirme). Quitar `dist:mac` de Electron del workflow.
- [ ] **Paso 4:** En `getvocify-desktop` no se toca nada; anotar en el informe que la app SwiftUI de `apps/macos` queda abandonada.
- [ ] **Paso 5:** Commit `ci(desktop): build the native macOS host`.

### Tarea C2: verificación de punta a punta (obligatoria)

Con el DMG instalado en `/Applications`, en una cuenta real:

- [ ] Primera apertura: entrar; la sesión persiste al cerrar y abrir.
- [ ] Grabar con Meet: los dos permisos se piden al pulsar grabar, no antes.
- [ ] Nota: un párrafo por hablante; lo provisional en gris; ninguna fila por palabra.
- [ ] Pastilla visible con Meet en pantalla completa; Parar funciona desde ella.
- [ ] Ayuda activada: solo aparece una línea cuando el backend devuelve evidencia.
- [ ] Parar: la nota sigue; huecos reservados; revisión con resumen, campos CRM, follow-up y checklist; aprobar escribe en HubSpot.
- [ ] La reunión aparece en la lista lateral; abrirla muestra solo lectura y el enlace al dashboard.
- [ ] Wifi apagada a mitad: chip «Sin conexión», el audio sigue, al volver continúa.
- [ ] `kill -9` a mitad: al abrir, la captura pendiente se ofrece para enviar.
- [ ] Sesión caducada (borrar el token a mano): vuelve a entrar sin perder la captura.
- [ ] Hover y cursor de mano en todos los controles; Tab muestra el foco.
- [ ] Checklist §5 de `vocify-ux-coherence` marcado punto por punto con capturas.

Todo con capturas en `docs/superpowers/deliveries/DESKTOP-MAC/report.md`. Si un punto falla, se abre la tarea correspondiente y se arregla antes de dar la entrega por completa.

---

## Fuera de este plan (no hacer)

- Firma con Developer ID y notarización: requieren la cuenta de Apple de Dani.
- Windows.
- Detección automática del inicio de reunión («¿Grabar?»): pendiente de decisión de Dani.
- Feedback y score en el escritorio: se quedan en el dashboard (F09, F11).
- Cambios de backend.
