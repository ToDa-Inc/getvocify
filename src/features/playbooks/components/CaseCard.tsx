import type { ReactNode } from "react";
import { BookOpenText, FileText, Phone, Quote, Sparkles } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SayBubble, TurnBubble } from "@/features/playbooks/components/Bubbles";
import type { TrialRun, TrialSource } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const SOURCE_ICON = { real: Phone, document: FileText, typical: Quote } as const;

/**
 * What live help would show for a case: the line the rep would read, or why there is none. `run` null means it is
 * still being written. Under it, where the line comes from: the team's own playbook or Vocify's general help, which is
 * the thing the Head of Sales most needs to tell apart. `label` names the bubble for screen readers only.
 */
export function RunBubble({ run, label }: { run: TrialRun | null; label?: string }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const title = label ?? c.cardLabel;
  if (!run) {
    return (
      <SayBubble label={title} muted>
        <span className="ask-shimmer" role="status">
          {c.cardRunning}
        </span>
      </SayBubble>
    );
  }
  if (run.detected === "none") return <SayBubble label={title} muted>{c.cardNothing}</SayBubble>;
  if (!run.card) return <SayBubble label={title} muted>{c.cardNoAnswer}</SayBubble>;
  const own = run.grounded && Boolean(run.card.source_id);
  return (
    <div className="space-y-1">
      <SayBubble label={title}>{run.card.say_this}</SayBubble>
      <div className="flex justify-end px-1">
        {own ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <BookOpenText aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />
            {c.cardFromPlaybook}
          </span>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="inline-flex items-center gap-1 rounded-full text-xs text-warning focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Sparkles aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />
                {c.cardGeneral}
                <span className="sr-only">: {c.cardGeneralHint}</span>
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom">{c.cardGeneralHint}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

/** One case of the trial: where it comes from, what the customer says and what live help would answer. */
export function CaseCard({
  source,
  clientText,
  run,
  cardLabel,
  children,
  className,
}: {
  source: TrialSource;
  clientText: string;
  run: TrialRun | null;
  cardLabel?: string;
  /** Under the card: the actions, or the box to write in. */
  children?: ReactNode;
  className?: string;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const caption = source === "real" ? c.caseReal : source === "document" ? c.caseDocument : c.caseTypical;
  const Icon = SOURCE_ICON[source] ?? Quote;
  return (
    <section className={cn(card, "space-y-3 p-5 md:p-6", THEME_TOKENS.motion.fadeIn, className)}>
      <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
        <Icon aria-hidden className="h-3 w-3" strokeWidth={1.5} />
        {caption}
      </span>
      <TurnBubble who="client" label={c.customerSays}>
        {clientText}
      </TurnBubble>
      <RunBubble run={run} label={cardLabel} />
      {children}
    </section>
  );
}
