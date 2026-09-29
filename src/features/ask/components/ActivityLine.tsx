import { useEffect, useState } from "react";
import { CaretRight, Check, X } from "@phosphor-icons/react";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { askActivitySummary, askToolLabel } from "@/lib/product-catalog";
import { useLanguage } from "@/lib/i18n";
import type { AskStep } from "@/lib/ask-thread";
import { visibleSteps } from "@/lib/ask-activity";

/**
 * While the assistant works: one row for the step in progress. Once the answer starts: one quiet line that
 * opens to every step. The reader sees where an answer came from without a spinner standing in for it.
 */
export default function ActivityLine({ steps: allSteps, thinking, settled }: { steps: AskStep[]; thinking: boolean; settled: boolean }) {
  const { t } = useLanguage();
  const steps = visibleSteps(allSteps);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (settled) setOpen(false);
  }, [settled]);

  if (steps.length === 0) {
    return thinking || (!settled && allSteps.length > 0) ? (
      <p className="inline-flex items-center gap-2 text-[13px] text-muted-foreground" role="status">
        <VocifySpinner size={12} />
        {t.product.askThinking}
      </p>
    ) : null;
  }

  const shown = settled ? steps : steps.slice(-1); // working: only the step in progress; the full list is one click away afterwards
  const rows = (
    <ul className="space-y-1.5">
      {shown.map((step) => (
        <li key={step.id} className="flex items-center gap-2 text-[13px] text-muted-foreground">
          {step.status === "running" ? (
            <VocifySpinner size={12} />
          ) : step.status === "ok" ? (
            <Check size={12} weight="light" className="text-primary" aria-hidden="true" />
          ) : (
            <X size={12} weight="light" className="text-destructive" aria-hidden="true" />
          )}
          <span>{askToolLabel(step.tool, t.product)}</span>
        </li>
      ))}
    </ul>
  );

  if (!settled) return <div role="status" aria-live="polite">{rows}</div>;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-md text-[13px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <CaretRight size={12} weight="light" className={`transition-transform motion-reduce:transition-none ${open ? "rotate-90" : ""}`} aria-hidden="true" />
        {askActivitySummary(steps.length, t.product)}
      </button>
      {open ? <div className="mt-2 animate-fade-in">{rows}</div> : null}
    </div>
  );
}
