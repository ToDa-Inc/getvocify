import { useState } from "react";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { askCoverageText } from "@/lib/product-catalog";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { AskCoverageNote } from "@/lib/ask-thread";
import { useBackfill } from "../hooks/useBackfill";

/**
 * One quiet line saying how much was read. For an owner or admin, when the gap is unread conversations,
 * it also offers to read them: the only fix for "based on 3 of 14".
 */
export default function CoverageNote({ note, canAnalyze }: { note: AskCoverageNote; canAnalyze: boolean }) {
  const { t } = useLanguage();
  const { state, start, pending } = useBackfill();
  const [confirming, setConfirming] = useState(false);
  const [count, setCount] = useState<number | null>(null);
  const unread = note.n != null && note.n_analysed != null ? note.n - note.n_analysed : 0;
  const offer = canAnalyze && note.level === "partial" && (!note.unit || note.unit === "conversations") && unread > 0;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <p className={THEME_TOKENS.typography.capsLabel}>{askCoverageText(note, t.product)}</p>
      {offer && state.phase === "idle" ? (
        <button
          type="button"
          onClick={async () => {
            setCount(await pending());
            setConfirming(true);
          }}
          className="rounded-md text-[13px] text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t.product.askAnalyzeRest}
        </button>
      ) : null}
      {state.phase === "running" ? (
        <span className="inline-flex items-center gap-2 text-[13px] text-muted-foreground" role="status">
          <VocifySpinner size={12} />
          {t.product.askAnalyzing.replace("{done}", String(state.done)).replace("{total}", String(state.total || unread))}
        </span>
      ) : null}
      {state.phase === "done" ? <span className="text-[13px] text-muted-foreground" role="status">{t.product.askAnalyzeDone}</span> : null}
      {state.phase === "failed" ? <span className="text-[13px] text-destructive" role="alert">{t.product.askAnalyzeFailed}</span> : null}
      <ConfirmAction
        open={confirming}
        onOpenChange={setConfirming}
        title={t.product.askAnalyzeConfirmTitle}
        description={t.product.askAnalyzeConfirmBody.replace("{count}", String(count ?? unread))}
        confirmLabel={t.product.askAnalyzeRest}
        cancelLabel={t.product.cancelAction}
        tone="default"
        onConfirm={() => {
          setConfirming(false);
          void start();
        }}
      />
    </div>
  );
}
