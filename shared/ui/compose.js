// Where "Enviar" goes. Pure: the host surface performs the navigation.
const MAILTO_MAX = 1800; // conservative: some mail clients truncate longer mailto URLs
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function query(params) {
  return Object.entries(params)
    .filter(([, value]) => value != null && value !== '')
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join('&');
}

/**
 * @param {{channel:'email'|'whatsapp', to?:string, phone?:string, subject?:string,
 *          body?:string, mailClient?:'default'|'gmail'|'outlook'}} draft
 * @returns {{ok:true, url:string} | {ok:false, reason:'no_email'|'no_phone'|'too_long', fallback?:string}}
 */
export function composeTarget({ channel, to = '', phone = '', subject = '', body = '', mailClient = 'default' }) {
  if (channel === 'whatsapp') {
    const digits = String(phone).replace(/\D/g, '');
    if (digits.length < 8) return { ok: false, reason: 'no_phone' };
    return { ok: true, url: `https://wa.me/${digits}?${query({ text: body })}` };
  }

  const address = String(to).trim();
  if (!EMAIL.test(address)) return { ok: false, reason: 'no_email' };

  if (mailClient === 'gmail') {
    return { ok: true, url: `https://mail.google.com/mail/?${query({ view: 'cm', fs: '1', to: address, su: subject, body })}` };
  }
  if (mailClient === 'outlook') {
    return { ok: true, url: `https://outlook.office.com/mail/deeplink/compose?${query({ to: address, subject, body })}` };
  }

  const url = `mailto:${address}?${query({ subject, body })}`;
  if (url.length > MAILTO_MAX) {
    return { ok: false, reason: 'too_long', fallback: `mailto:${address}?${query({ subject })}` };
  }
  return { ok: true, url };
}
