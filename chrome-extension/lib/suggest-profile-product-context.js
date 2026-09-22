import { normalizeStoredProductContext } from '../shared/ui/copilot/product-context.js';

let cachedSuggestProfileProductContext = undefined;

export function resetSuggestProfileProductContextCache() {
  cachedSuggestProfileProductContext = undefined;
}

export function profileProductContextFromUser(user) {
  return String(user?.product_context ?? '').trim();
}

export function primeSuggestProfileProductContext(user) {
  if (!user) return;
  cachedSuggestProfileProductContext = profileProductContextFromUser(user);
}

/** Fetch /auth/me once per listen session when local offer text is blank or legacy. */
export async function ensureSuggestProfileProductContext(localProductContext, getCurrentUser) {
  if (normalizeStoredProductContext(localProductContext)) {
    return '';
  }
  if (cachedSuggestProfileProductContext !== undefined) {
    return cachedSuggestProfileProductContext;
  }
  const user = await getCurrentUser().catch(() => null);
  cachedSuggestProfileProductContext = user ? profileProductContextFromUser(user) : '';
  return cachedSuggestProfileProductContext;
}
