import { VocifyLoader } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

// Shared loading / error-with-retry / empty states for the four rep coaching views.
export function CoachLoading() {
  const { t } = useLanguage();
  return (
    <div className={THEME_TOKENS.interaction.pageLoad} data-testid="coach-loading">
      <VocifyLoader size="lg" label={t.product.coachLoading} />
    </div>
  );
}

export function CoachError({ onRetry }: { onRetry: () => void }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <div className="flex flex-wrap items-center gap-3" role="alert" data-testid="coach-error">
      <p className={THEME_TOKENS.typography.body}>{p.coachLoadFailed}</p>
      <button type="button" onClick={onRetry} className="rounded-full border border-border bg-card px-3.5 py-1 text-xs text-foreground hover:border-beige/25">
        {p.coachRetry}
      </button>
    </div>
  );
}

export function CoachEmpty({ text }: { text: string }) {
  return (
    <p className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 ${THEME_TOKENS.typography.body}`} data-testid="coach-empty">
      {text}
    </p>
  );
}
