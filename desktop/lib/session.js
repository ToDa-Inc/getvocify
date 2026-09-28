export function isSessionError({ status, detail } = {}) {
  if (status === 401) return true;
  return /session|sign in again|authorization token/i.test(String(detail || ''));
}

export function startScreen({ hasToken, meOk }) {
  return hasToken && meOk ? 'listen' : 'login';
}
