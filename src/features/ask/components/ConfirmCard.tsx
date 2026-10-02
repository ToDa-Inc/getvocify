import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import type { AskConfirm } from "@/lib/ask-thread";

/** A write waits here until the reader says yes. The result shown is the write's real result. */
export default function ConfirmCard({ card, onConfirm, onCancel }: { card: AskConfirm; onConfirm: () => void; onCancel: () => void }) {
  const { t } = useLanguage();
  const settled = card.status === "succeeded" || card.status === "cancelled";
  return (
    <div
      className="ask-enter space-y-3 rounded-xl border border-beige/25 bg-card px-4 py-3.5 shadow-medium ring-4 ring-beige/5"
      role="group"
      aria-label={card.summary}
    >
      <p className="whitespace-pre-line text-[15px] leading-relaxed text-foreground">{card.summary}</p>
      {card.status === "proposed" || card.status === "failed" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={onConfirm}>{t.product.confirmAction}</Button>
          <Button size="sm" variant="ghost" onClick={onCancel}>{t.product.cancelAction}</Button>
          {card.status === "failed" ? <span className="text-[13px] text-destructive" role="alert">{t.product.askConfirmFailedRetry}</span> : null}
        </div>
      ) : null}
      {card.status === "running" ? (
        <p className="inline-flex items-center gap-2 text-[13px]" role="status">
          <VocifySpinner size={12} />
          <span className="ask-shimmer">{t.product.askConfirmRunning}</span>
        </p>
      ) : null}
      {card.status === "uncertain" ? <p className="text-[13px] text-warning" role="alert">{t.product.askConfirmUncertain}</p> : null}
      {settled ? (
        <p className="flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground" role="status">
          {card.status === "succeeded" ? t.product.askConfirmSucceeded : t.product.askConfirmCancelled}
          {card.status === "succeeded" && card.url ? (
            <a href={card.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
              {t.product.askConfirmOpenCrm}
              <ExternalLink size={12} strokeWidth={1.5} aria-hidden="true" />
            </a>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
