import { useLanguage, type Language } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const LANG_OPTIONS: { lang: Language; labelKey: "languageEnglish" | "languageSpanish" }[] = [
  { lang: "EN", labelKey: "languageEnglish" },
  { lang: "ES", labelKey: "languageSpanish" },
];

export const InterfaceLanguageSettings = () => {
  const { language, setLanguage, t } = useLanguage();

  return (
    <div className="mt-6">
      <p className={`${THEME_TOKENS.typography.capsLabel} mb-2`}>{t.product.languageTitle}</p>
      <div
        className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1"
        role="radiogroup"
        aria-label={t.product.languageTitle}
      >
        {LANG_OPTIONS.map(({ lang, labelKey }) => {
          const selected = language === lang;
          return (
            <button
              key={lang}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setLanguage(lang)}
              className={`rounded-full px-4 h-9 text-xs transition-colors ${
                selected ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.product[labelKey]}
            </button>
          );
        })}
      </div>
    </div>
  );
};
