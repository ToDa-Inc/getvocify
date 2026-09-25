export type ApiRequestLanguage = 'en' | 'es';

let requestLanguage: ApiRequestLanguage | null = null;

export function setApiRequestLanguage(lang: ApiRequestLanguage | null): void {
  requestLanguage = lang;
}

/** For tests only. */
export function resetApiRequestLanguage(): void {
  requestLanguage = null;
}

export function acceptLanguageRequestHeader(): Record<string, string> {
  if (requestLanguage === 'en' || requestLanguage === 'es') {
    return { 'Accept-Language': requestLanguage };
  }
  return {};
}
