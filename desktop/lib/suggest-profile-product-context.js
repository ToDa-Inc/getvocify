import { normalizeStoredProductContext } from '../../shared/ui/copilot/product-context.js';

let cachedSuggestProfileProductContext = undefined;

export function resetSuggestProfileProductContextCache() {
  cachedSuggestProfileProductContext = undefined;
}

export function profileProductContextFromAuthMeBody(user) {
  return String(user?.product_context ?? '').trim();
}

/** GET /auth/me once per listen session when local offer text is blank or legacy. */
export async function ensureSuggestProfileProductContext(
  localProductContext,
  { fetchImpl, apiBase, token },
) {
  if (normalizeStoredProductContext(localProductContext)) {
    return '';
  }
  if (cachedSuggestProfileProductContext !== undefined) {
    return cachedSuggestProfileProductContext;
  }
  const base = String(apiBase || '').replace(/\/+$/, '');
  if (!token || !base) {
    cachedSuggestProfileProductContext = '';
    return cachedSuggestProfileProductContext;
  }
  try {
    const res = await fetchImpl(`${base}/auth/me`, {
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
    });
    if (!res.ok) {
      cachedSuggestProfileProductContext = '';
      return cachedSuggestProfileProductContext;
    }
    const user = await res.json();
    cachedSuggestProfileProductContext = profileProductContextFromAuthMeBody(user);
  } catch {
    cachedSuggestProfileProductContext = '';
  }
  return cachedSuggestProfileProductContext;
}
