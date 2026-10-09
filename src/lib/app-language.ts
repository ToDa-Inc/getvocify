export type AppLanguage = 'EN' | 'ES';

export type StoredAppLanguage = 'en' | 'es';

export type HtmlLang = StoredAppLanguage;

export function htmlLang(lang: AppLanguage): HtmlLang {
  return lang === 'EN' ? 'en' : 'es';
}

const VOCIFY_LANG_KEY = 'vocify_lang';

export function readStoredAppLanguage(): StoredAppLanguage | null {
  if (typeof localStorage === 'undefined') {
    return null;
  }
  const raw = localStorage.getItem(VOCIFY_LANG_KEY);
  if (raw === 'en' || raw === 'es') {
    return raw;
  }
  return null;
}

export function writeStoredAppLanguage(lang: AppLanguage): void {
  localStorage.setItem(VOCIFY_LANG_KEY, lang === 'EN' ? 'en' : 'es');
}

/** When nothing is stored yet, infer persistence from the visit path (not the default locale). */
export function appLanguageToPersistFromVisit(input: {
  stored: StoredAppLanguage | null;
  path: string;
}): AppLanguage | null {
  if (input.stored !== null) {
    return null;
  }
  if (input.path.startsWith('/en')) {
    return 'EN';
  }
  return null;
}

export function resolveAppLanguage(input: {
  stored: StoredAppLanguage | null;
  path: string;
}): AppLanguage {
  if (input.stored === 'en') {
    return 'EN';
  }
  if (input.stored === 'es') {
    return 'ES';
  }
  if (input.path.startsWith('/en')) {
    return 'EN';
  }
  return 'ES';
}

export function shouldRewritePathForLanguage(path: string): boolean {
  return path === '/' || path.startsWith('/en');
}

export function publicPathForLanguage(lang: AppLanguage): '/' | '/en' {
  return lang === 'EN' ? '/en' : '/';
}
