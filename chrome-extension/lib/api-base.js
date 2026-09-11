/**
 * Where the extension sends API traffic.
 *
 * Unpacked (Load unpacked) → local backend.
 * Chrome Web Store / packed → production.
 * chrome.storage.local.api_base always wins when set.
 */

export const PROD_API_BASE = 'https://api.getvocify.com/api/v1';
export const LOCAL_API_BASE = 'http://localhost:8888/api/v1';
export const PROD_APP_URL = 'https://app.getvocify.com';
export const LOCAL_APP_URL = 'http://localhost:8080';

export function isUnpackedExtension(manifest) {
  if (!manifest || typeof manifest !== 'object') return false;
  return !Object.prototype.hasOwnProperty.call(manifest, 'update_url');
}

export function resolveApiBase({ unpacked = false, override = '' } = {}) {
  const explicit = String(override || '').trim().replace(/\/+$/, '');
  if (explicit) return explicit;
  return unpacked ? LOCAL_API_BASE : PROD_API_BASE;
}

export function apiBaseToWsOrigin(apiBase) {
  const http = String(apiBase || PROD_API_BASE).replace(/\/+$/, '');
  const ws = http.replace(/^https:/i, 'wss:').replace(/^http:/i, 'ws:');
  return ws.replace(/\/api\/v1$/i, '');
}

export function appUrlFromApiBase(apiBase) {
  const base = String(apiBase || PROD_API_BASE);
  if (/localhost|127\.0\.0\.1/i.test(base)) return LOCAL_APP_URL;
  return PROD_APP_URL;
}
