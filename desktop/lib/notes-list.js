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
