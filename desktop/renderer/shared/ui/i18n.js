// Chrome strings for shared components only. Content strings (reasons, due
// labels, the draft itself) arrive already written from the server.
const STRINGS = {
  es: {
    followupFor: (name) => `Seguimiento para ${name}`,
    followupFallback: 'Seguimiento',
    writing: 'Escribiendo el seguimiento…',
    send: 'Enviar',
    whatsapp: 'WhatsApp',
    copy: 'Copiar',
    addEmail: 'Sin email del contacto: cópialo o envíalo por WhatsApp.',
    openedMail: 'Abierto en el correo',
    openedWhatsapp: 'Abierto en WhatsApp.',
  },
  en: {
    followupFor: (name) => `Follow-up for ${name}`,
    followupFallback: 'Follow-up',
    writing: 'Writing the follow-up…',
    send: 'Send',
    whatsapp: 'WhatsApp',
    copy: 'Copy',
    addEmail: 'No email for this contact: copy it or send it on WhatsApp.',
    openedMail: 'Opened in your mail app.',
    openedWhatsapp: 'Opened in WhatsApp.',
  },
};

export function strings(lang) {
  return STRINGS[String(lang || '').slice(0, 2).toLowerCase()] || STRINGS.es;
}
