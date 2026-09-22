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
  },
};

const FALLBACK = 'es';

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
