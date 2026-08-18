/**
 * Page + caller names for live STT biasing.
 * Emails and phone numbers are not spoken the way they are stored.
 */

function looksLikeEmailOrPhone(value) {
  const text = String(value || '').trim();
  if (!text) return true;
  if (text.includes('@')) return true;
  if (/^[\d\s+\-().]{6,}$/.test(text)) return true;
  return false;
}

export function mergeSessionVocab(pageVocab, user) {
  const out = [];
  const seen = new Set();
  const extras = [user?.full_name, user?.fullName, user?.company_name, user?.companyName];
  for (const item of [...(pageVocab || []), ...extras]) {
    const text = String(item || '').trim();
    if (!text || looksLikeEmailOrPhone(text)) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(text);
  }
  return out;
}
