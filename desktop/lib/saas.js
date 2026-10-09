export function joinApiUrl(base, path) {
  const root = String(base || '').trim().replace(/\/+$/, '');
  const suffix = String(path || '').trim();
  if (!root) return suffix.startsWith('/') ? suffix : `/${suffix}`;
  const normalized = suffix.startsWith('/') ? suffix : `/${suffix}`;
  return `${root}${normalized}`;
}

export function isAllowedApiBase(base) {
  try {
    const url = new URL(String(base || '').trim());
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return false;
    if (url.hostname === 'api.getvocify.com') return url.protocol === 'https:';
    if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') return true;
    return false;
  } catch {
    return false;
  }
}

export function humanizeSaasError(err, { status, detail } = {}) {
  const msg = err?.message || String(err || '');
  const blob = `${msg} ${detail || ''}`;
  if (/failed to fetch|disallowed cors origin|networkerror|load failed/i.test(blob)) {
    return 'Could not reach the Vocify API (CORS/network). The companion should send this from Electron, not the window.';
  }
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (status) return msg || `HTTP ${status}`;
  return msg || 'Request failed';
}

export async function proxyJsonRequest(fetchImpl, { base, path, method = 'GET', headers = {}, body } = {}) {
  if (!isAllowedApiBase(base)) {
    return { ok: false, status: 0, data: {}, error: 'API base is not a Vocify host' };
  }
  const url = joinApiUrl(base, path);
  const res = await fetchImpl(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  const detail = typeof data.detail === 'string' ? data.detail : undefined;
  if (!res.ok) {
    return {
      ok: false,
      status: res.status,
      data,
      error: humanizeSaasError(null, { status: res.status, detail }),
    };
  }
  return { ok: true, status: res.status, data };
}
