F12: Chrome live-assist suggest body skips non-meeting `callMode` and sends `contact_id` only on CRM contact records.
Backend: `SYSTEM_PROMPT` de suggest incluye `evidence_refs` y `source_id` en el JSON obligatorio (alineado con `copilot_suggest_v1`).
Live assist y dashboard copilot ya no envían el pitch ficticio de Vocify: sin texto guardado, `product_context` se omite y el textarea queda vacío con placeholder en español.
El párrafo legacy guardado en `vocify_copilot_product_context` se trata como vacío (misma omisión de `product_context`); otro texto de empresa sigue enviándose.
Desktop overlay: checklist de meeting vía `POST /copilot/checklist` y renderer puro `shared/ui/copilot/checklist.js` bajo la tarjeta de ayuda.
Desktop overlay: ayuda live opt-in («Ayuda»), línea vía `pillDecision` (4 s / 10 s / 60 s), sin `/copilot/suggest` hasta activar; checklist sigue en meeting.
Backend: `POST /api/v1/copilot/checklist` devuelve pasos del snapshot publicado y marca `met` solo con `playbook_observations` en la captura y `evidence_refs` no vacíos; modos no-meeting y ambigüedad de playbook sin `capture_id` responden checklist vacío.
Extensión meeting listen: ayuda desactivada al inicio (sin `/copilot/suggest` hasta «Ayuda»), checklist vía `POST /copilot/checklist` y botón Ayuda/Ocultar ayuda junto a la tarjeta.
Extensión popup: la línea «Say this» usa `pillDecision` (4 s / 10 s / 60 s, rep oculta); nuevo listen reinicia el reloj; suggest sigue bloqueado con ayuda off.
Extensión popup live: copy estático en español («Transcribiendo…», «Di esto», «Esperando a que termine de hablar…») en el bloque de transcript/copilot antes del paint JS.
Extensión popup listen: el paint JS ya no pisa el HTML con estados en inglés («Empezando a escuchar…», «Escuchando esta pestaña…», «Ayuda en esta reunión…»); `listenUiModel` en `tab-capture.js` alinea botón y línea de estado.
Desktop companion listen: ventana principal y overlay flotante en español («Parar y revisar», «Escuchando»/«En reposo», «Escuchando la reunión…», «Parar»); `overlaySnippet` y `overlay.js` ya no pisan el HTML en inglés.
Extensión popup listen: `listenUiModel` idle/error en español («Escuchar pestaña», «Grabar», «Sin escucha», «Listo para grabar»); starting/live sin cambios.
App web memo detail: `POST /copilot/checklist` con `capture_id` del memo y checklist de revisión vía `memoMeetingChecklistView` (applicable 0 o error → nada).
Desktop review: `POST /copilot/checklist` con `capture_id` del memo abierto; progreso y pasos vía `desktop/lib/memo-meeting-checklist.js` (applicable 0 o error → nada; met usa `checklistDone` de i18n).
Listen chrome (extensión, desktop, overlay): copy estático en `shared/ui/i18n.js` para `es` y `en`.
Listen deny (`startDeniedMessage`), fallbacks de inicio y prefijos de transcript (`speakerYou`/`speakerThem`) en `shared/ui/i18n.js` para extensión y desktop.
Desktop companion: el split de turnos en vivo usa todos los prefijos `speakerYou`/`speakerThem` del catálogo (es/en), no solo `You:`/`Them:`.
Desktop overlay: `speakerRoleFromLastLine` comparte la misma lista de prefijos del catálogo para ocultar ayuda en turnos rep.
Extensión background: aviso «cuelga antes de grabar nota» vía `memoHangUpFirst` en `shared/ui/i18n.js` (`listenUiLang`).
Extensión background: aviso «deja de escuchar la pestaña antes de grabar nota» vía `memoStopListeningFirst` en `shared/ui/i18n.js` (`listenUiLang`).
Extensión popup y desktop companion: `uiLangInput` + `resolveUiLang`; desktop lee `localStorage.vocify_lang`, la extensión su propia clave `vocify_lang` en `chrome.storage.local` (sin sync con la web).
App web: el idioma de UI y API sigue `localStorage.vocify_lang` (`en`/`es`); el prefijo `/en` solo aplica como fallback en rutas públicas (`/`/`/en`), no en `/dashboard`.
Live suggest (extensión + desktop): `resolveProductContextForSuggest` envía oferta local custom, si no `product_context` de GET `/auth/me`, y omite si ambos están vacíos o el local es el pitch legacy de Vocify.
App web: la primera visita a `/en` sin `vocify_lang` guardado persiste `en`; ajustes del dashboard permite cambiar EN/ES sin salir de la ruta.
