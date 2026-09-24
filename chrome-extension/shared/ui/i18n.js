// Chrome strings for shared components only. Content strings (reasons, due
// labels, the draft itself) arrive already written from the server.
const STRINGS = {
  es: {
    followupFor: (name) => `Seguimiento para ${name}`,
    followupFallback: 'Seguimiento',
    writing: 'Escribiendo el seguimiento…',
    openMail: 'Abrir en el correo',
    whatsapp: 'WhatsApp',
    copy: 'Copiar',
    addEmail: 'Sin email del contacto: cópialo o envíalo por WhatsApp.',
    openedMail: 'Abierto en el correo',
    openedWhatsapp: 'Abierto en WhatsApp.',
    listenIdleButton: 'Escuchar pestaña',
    listenStopButton: 'Dejar de escuchar',
    listenStartingButton: 'Empezando…',
    listenStartingHeader: 'Empezando a escuchar…',
    listenStartingLine: 'Capturando audio de esta pestaña…',
    listenLiveStatus: 'Escuchando',
    listenLiveWaiting: 'Escuchando — esperando voz',
    listenIdleStatus: 'Grabar',
    listenNotListening: 'Sin escucha',
    listenReady: 'Listo para grabar',
    listenHeaderTab: (title) => `Escuchando · ${title}`,
    listenHeaderPlain: 'Escuchando esta pestaña',
    listenLineTab: (title) => `Escuchando «${title}»…`,
    listenLinePlain: 'Escuchando esta pestaña…',
    listenLineMic:
      'Escuchando esta pestaña, no tu micrófono. La otra parte de la llamada debería aparecer aquí.',
    sayThis: 'Di esto',
    waitingForThem: 'Esperando a que termine de hablar…',
    transcribing: 'Transcribiendo…',
    helpOn: 'Ayuda',
    helpOff: 'Ocultar ayuda',
    helpActive: 'Ayuda en esta reunión…',
    checklistDone: 'Hecho',
    checklistProgress: (observed, applicable) => `${observed} de ${applicable}`,
    overlayLive: 'En vivo',
    overlayListening: 'Escuchando la reunión…',
    overlayStop: 'Parar',
    desktopStopReview: 'Parar y revisar',
    desktopIdle: 'En reposo',
    desktopHearing:
      'Escuchando la reunión. La ventana flotante sigue encima.',
    desktopStopped: 'Parado.',
    meetingChecking: 'Comprobando próximos pasos',
    meetingOmitted: 'Reunión omitida',
    meetingDetected: 'Reunión detectada',
    meetingNotSaved: 'No se ha guardado en el CRM',
    meetingSaved: 'Guardada en el CRM',
    meetingPending: 'Pendiente de revisar',
    meetingSave: 'Guardar reunión',
    meetingOmit: 'Omitir',
    meetingReconcile: 'Reconciliar',
    speakerYou: 'Tú',
    speakerThem: 'Ellos',
    memoHangUpFirst: 'Cuelga la llamada antes de grabar una nota.',
    memoStopListeningFirst:
      'Deja de escuchar la pestaña antes de grabar una nota.',
    listenDenyCallInProgress:
      'Cuelga la llamada antes de escuchar esta pestaña.',
    listenDenyMicRecording:
      'Detén la nota de voz antes de escuchar esta pestaña.',
    listenDenyAlreadyListeningTab: 'Ya estás escuchando una pestaña.',
    listenDenyLoginRequiredTab: 'Inicia sesión arriba para empezar a escuchar.',
    listenDenyNoTab: 'Enfoca una pestaña de Chrome e inténtalo de nuevo.',
    listenDenyNoStreamId:
      'No se pudo capturar esta pestaña. Enfoca la pestaña de la llamada y pulsa Escuchar otra vez.',
    listenDenyNotHubspotTab:
      'Abre el registro de HubSpot donde está la llamada y pulsa Escuchar.',
    listenDenyUnsupportedMeetingTab:
      'Escuchar captura una pestaña de llamada de HubSpot en Chrome, no Zoom, Meet ni Teams de escritorio.',
    listenDenyNoAudio:
      'Esta pestaña aún no tiene audio. Inicia la llamada y pulsa Escuchar otra vez.',
    listenDenyStreamExpired:
      'La captura expiró antes de empezar. Pulsa Escuchar otra vez.',
    listenDenyCaptureFailed:
      'No se pudo iniciar el audio de la pestaña. Quédate en la pestaña de llamada de HubSpot y pulsa Escuchar otra vez.',
    listenDenyTabCaptureDefault: 'No se pudo iniciar la captura de pestaña.',
    listenDenyAlreadyListening: 'Ya estás escuchando.',
    listenDenyLoginRequired: 'Inicia sesión para empezar a escuchar.',
    listenDenyNoSystemAudioLinux:
      'No se pudo capturar el audio del sistema. Instala PipeWire (pw-record) o PulseAudio (parec), o comparte una ventana con audio.',
    listenDenyNoSystemAudioMac:
      'No se pudo capturar el audio del sistema. En macOS concede Grabación de pantalla e inténtalo de nuevo.',
    listenDenyNoMic:
      'Se necesita permiso de micrófono para tu parte de la llamada.',
    listenDenyDesktopDefault: 'No se pudo empezar a escuchar.',
    listenCouldNotStart: 'No se pudo iniciar',
    listenCouldNotStartTabRetry:
      'No se pudo iniciar el audio de la pestaña. Pulsa Escuchar otra vez.',
    dismiss: 'Descartar',
    undo: 'Deshacer',
    desktopNewNote: 'Nueva nota',
    desktopOpenDashboard: 'Abrir en el dashboard',
    desktopLogout: 'Salir',
    transcriptBackToLive: 'Volver al directo',
    desktopOpenSettings: 'Abrir Ajustes',
    desktopNothingHeard: 'No se oyó nada',
    desktopOffline: 'Sin conexión',
    desktopRetry: 'Reintentar',
    desktopPrepareFailed: 'No se pudo preparar',
    desktopNoMeetingAudio: 'Sin audio de la reunión',
  },
  en: {
    followupFor: (name) => `Follow-up for ${name}`,
    followupFallback: 'Follow-up',
    writing: 'Writing the follow-up…',
    openMail: 'Open in mail',
    whatsapp: 'WhatsApp',
    copy: 'Copy',
    addEmail: 'No email for this contact: copy it or send it on WhatsApp.',
    openedMail: 'Opened in your mail app.',
    openedWhatsapp: 'Opened in WhatsApp.',
    listenIdleButton: 'Listen to tab',
    listenStopButton: 'Stop listening',
    listenStartingButton: 'Starting…',
    listenStartingHeader: 'Starting to listen…',
    listenStartingLine: 'Capturing audio from this tab…',
    listenLiveStatus: 'Listening',
    listenLiveWaiting: 'Listening — waiting for speech',
    listenIdleStatus: 'Record',
    listenNotListening: 'Not listening',
    listenReady: 'Ready to record',
    listenHeaderTab: (title) => `Listening · ${title}`,
    listenHeaderPlain: 'Listening to this tab',
    listenLineTab: (title) => `Listening to “${title}”…`,
    listenLinePlain: 'Listening to this tab…',
    listenLineMic:
      'Listening to this tab, not your microphone. The other side of the call should show up here.',
    sayThis: 'Say this',
    waitingForThem: 'Waiting for the other side to finish speaking…',
    transcribing: 'Transcribing…',
    helpOn: 'Help',
    helpOff: 'Hide help',
    helpActive: 'Help in this meeting…',
    checklistDone: 'Done',
    checklistProgress: (observed, applicable) => `${observed} of ${applicable}`,
    overlayLive: 'Live',
    overlayListening: 'Listening to the meeting…',
    overlayStop: 'Stop',
    desktopStopReview: 'Stop & review',
    desktopIdle: 'Idle',
    desktopHearing:
      'Listening to the meeting. The floating window stays on top.',
    desktopStopped: 'Stopped.',
    meetingChecking: 'Checking next steps',
    meetingOmitted: 'Meeting skipped',
    meetingDetected: 'Meeting detected',
    meetingNotSaved: 'Not saved in the CRM',
    meetingSaved: 'Saved in the CRM',
    meetingPending: 'Pending review',
    meetingSave: 'Save meeting',
    meetingOmit: 'Skip',
    meetingReconcile: 'Reconcile',
    speakerYou: 'You',
    speakerThem: 'Them',
    memoHangUpFirst: 'Hang up the call before recording a memo.',
    memoStopListeningFirst:
      'Stop listening to the tab before recording a memo.',
    listenDenyCallInProgress:
      'Hang up the call before listening to this tab.',
    listenDenyMicRecording:
      'Stop the voice memo before listening to this tab.',
    listenDenyAlreadyListeningTab: 'Already listening to a tab.',
    listenDenyLoginRequiredTab: 'Log in above to start listening.',
    listenDenyNoTab: 'Focus a Chrome tab and try again.',
    listenDenyNoStreamId:
      'Could not capture this tab. Focus the call tab and click Listen again.',
    listenDenyNotHubspotTab:
      'Open the HubSpot record where the call is happening, then click Listen.',
    listenDenyUnsupportedMeetingTab:
      'Listen captures a HubSpot call tab in Chrome — not Zoom, Meet, or Teams desktop.',
    listenDenyNoAudio:
      'This tab has no audio yet. Start the call, then click Listen again.',
    listenDenyStreamExpired:
      'Capture expired before it started. Click Listen again.',
    listenDenyCaptureFailed:
      'Could not start tab audio. Stay on the HubSpot call tab and click Listen again.',
    listenDenyTabCaptureDefault: 'Could not start tab capture.',
    listenDenyAlreadyListening: 'Already listening.',
    listenDenyLoginRequired: 'Log in to start listening.',
    listenDenyNoSystemAudioLinux:
      'Could not capture system audio. Install PipeWire (pw-record) or PulseAudio (parec), or share a window that has audio.',
    listenDenyNoSystemAudioMac:
      'Could not capture system audio. On macOS grant Screen Recording, then try again.',
    listenDenyNoMic:
      'Microphone permission is required for your side of the call.',
    listenDenyDesktopDefault: 'Could not start listening.',
    listenCouldNotStart: 'Could not start',
    listenCouldNotStartTabRetry:
      'Could not start tab audio. Click Listen again.',
    dismiss: 'Dismiss',
    undo: 'Undo',
    desktopNewNote: 'New note',
    desktopOpenDashboard: 'Open in dashboard',
    desktopLogout: 'Log out',
    transcriptBackToLive: 'Back to live',
    desktopOpenSettings: 'Open Settings',
    desktopNothingHeard: 'Nothing was heard',
    desktopOffline: 'Offline',
    desktopRetry: 'Retry',
    desktopPrepareFailed: 'Could not prepare',
    desktopNoMeetingAudio: 'No meeting audio',
  },
};

const FALLBACK = 'es';

/**
 * Build `resolveUiLang` / `strings` input from saved preference and navigator.
 * Forwards `vocify_lang` only when it maps to a supported UI language (es/en).
 *
 * @param {string | null | undefined} saved
 * @param {string | null | undefined} navigatorLanguage
 */
export function uiLangInput(saved, navigatorLanguage) {
  /** @type {{ vocify_lang?: string, navigatorLanguage?: string }} */
  const out = {};
  if (typeof saved === 'string' && saved.trim()) {
    const code = saved.trim().slice(0, 2).toLowerCase();
    if (Object.prototype.hasOwnProperty.call(STRINGS, code)) {
      out.vocify_lang = saved.trim();
    }
  }
  if (typeof navigatorLanguage === 'string' && navigatorLanguage.trim()) {
    out.navigatorLanguage = navigatorLanguage.trim();
  }
  return out;
}

/** @param {string | { vocify_lang?: string | null, navigatorLanguage?: string | null } | null | undefined} input */
export function resolveUiLang(input) {
  const opts =
    input == null || input === ''
      ? {}
      : typeof input === 'string'
        ? { vocify_lang: input }
        : input;
  const explicit = opts.vocify_lang;
  if (typeof explicit === 'string' && explicit.trim()) {
    const code = explicit.trim().slice(0, 2).toLowerCase();
    if (Object.prototype.hasOwnProperty.call(STRINGS, code)) return code;
  }
  const nav = opts.navigatorLanguage;
  if (typeof nav === 'string' && nav.trim()) {
    const code = nav.trim().slice(0, 2).toLowerCase();
    if (Object.prototype.hasOwnProperty.call(STRINGS, code)) return code;
  }
  return FALLBACK;
}

/** @param {Parameters<typeof resolveUiLang>[0]} lang */
export function strings(lang) {
  const code = resolveUiLang(lang);
  return STRINGS[code] || STRINGS[FALLBACK];
}

/** Fill static `data-i18n="key"` nodes (non-function keys only). */
export function applyDataI18n(root, lang) {
  const t = strings(lang);
  if (!root?.querySelectorAll) return;
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (!key || !(key in t)) return;
    const val = t[key];
    if (typeof val === 'function') return;
    el.textContent = val;
  });
}
