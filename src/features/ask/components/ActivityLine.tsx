import { useEffect, useState } from "react";
import { CaretRight, Check, X } from "@phosphor-icons/react";
import { askActivitySummary, askToolLabel } from "@/lib/product-catalog";
import { useLanguage } from "@/lib/i18n";
import type { AskStep } from "@/lib/ask-thread";
import { visibleSteps } from "@/lib/ask-activity";

function StepMark({ status }: { status: AskStep["status"] }) {
  if (status === "running") {
    return <span className="ask-pulse h-1.5 w-1.5 rounded-full bg-beige" aria-hidden="true" />;
  }
  return status === "ok" ? (
    <Check size={11} weight="bold" className="text-beige" aria-hidden="true" />
  ) : (
    <X size={11} weight="bold" className="text-destructive" aria-hidden="true" />
  );
}

function Steps({ steps }: { steps: AskStep[] }) {
  const { t } = useLanguage();
  return (
    <ol className="relative space-y-2 before:absolute before:bottom-1.5 before:left-[5.5px] before:top-1.5 before:w-px before:bg-[hsl(var(--hairline))]">
      {steps.map((step) => (
        <li key={step.id} className="ask-enter relative flex items-center gap-2.5 text-[13px]">
          <span className="relative z-10 flex h-3 w-3 shrink-0 items-center justify-center rounded-full bg-background">
            <StepMark status={step.status} />
          </span>
          <span className={step.status === "running" ? "ask-shimmer" : "text-muted-foreground"}>{askToolLabel(step.tool, t.product)}</span>
        </li>
      ))}
    </ol>
  );
}

/**
 * While the assistant works: every source it is reading, the current one alive. Once the answer arrives: one quiet
 * chip that opens to the same list. The reader sees where an answer came from without a spinner standing in for it.
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
      <p className="ask-enter inline-flex items-center gap-2.5 text-[13px]" role="status">
        <span className="flex h-3 w-3 items-center justify-center">
          <span className="ask-pulse h-1.5 w-1.5 rounded-full bg-beige" aria-hidden="true" />
        </span>
        <span className="ask-shimmer">{t.product.askThinking}</span>
      </p>
    ) : null;
  }

  if (!settled) {
    return (
      <div role="status" aria-live="polite">
        <Steps steps={steps} />
      </div>
    );
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="-ml-1 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Check size={11} weight="bold" className="text-beige" aria-hidden="true" />
        {askActivitySummary(steps.length, t.product)}
        <CaretRight size={10} weight="bold" className={`transition-transform duration-150 motion-reduce:transition-none ${open ? "rotate-90" : ""}`} aria-hidden="true" />
      </button>
      {open ? (
        <div className="ask-enter mt-2 pl-1">
          <Steps steps={steps} />
        </div>
      ) : null}
    </div>
  );
}
