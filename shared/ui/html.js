// Every interpolation is escaped unless it is itself an html`` fragment or raw().
// Transcripts are user-controlled text; this is the only way markup gets built.
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const RAW = Symbol('vocify.raw');

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

export function raw(markup) {
  return { [RAW]: String(markup ?? '') };
}

function serialize(value) {
  if (value == null || value === false || value === true) return '';
  if (Array.isArray(value)) return value.map(serialize).join('');
  if (typeof value === 'object' && RAW in value) return value[RAW];
  return escapeHtml(value);
}

export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i += 1) out += serialize(values[i]) + strings[i + 1];
  return raw(out);
}

export function renderToString(fragment) {
  return serialize(fragment);
}
