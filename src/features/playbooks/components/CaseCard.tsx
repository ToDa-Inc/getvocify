import type { ReactNode } from "react";
import { CardBubble, QuoteBubble } from "@/features/playbooks/components/Bubbles";
import type { TrialRun, TrialSource } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

/**
 * What live help would show for a case: the card the rep would read, or why there is none. `run` null means it is still
 * being written. Below the card, where it comes from: the team's own playbook or Vocify's general help, which is the
 * thing the Head of Sales most needs to tell apart.
 */
export function RunBubble({ run, label }: { run: TrialRun | null; label?: string }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const title = label ?? c.cardLabel;
  if (!run) {
    return (
      <CardBubble label={title}>
        <span className="ask-shimmer" role="status">
          {c.cardRunning}
        </span>
      </CardBubble>
    );
  }
  if (run.detected === "none") return <CardBubble label={title}><span className="text-muted-foreground">{c.cardNothing}</span></CardBubble>;
  if (!run.card) return <CardBubble label={title}><span className="text-muted-foreground">{c.cardNoAnswer}</span></CardBubble>;
  const own = run.grounded && Boolean(run.card.source_id);
  return (
    <div className="space-y-1.5">
      <CardBubble label={title}>{run.card.say_this}</CardBubble>
      <p className={cn("px-1 text-xs", own ? "text-muted-foreground" : "text-warning")}>{own ? c.cardFromPlaybook : c.cardGeneral}</p>
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
  return (
    <section className={cn(card, "space-y-4 p-5 md:p-6", THEME_TOKENS.motion.fadeIn, className)}>
      <p className={THEME_TOKENS.typography.capsLabel}>{caption}</p>
      <QuoteBubble label={c.customerSays}>{clientText}</QuoteBubble>
      <RunBubble run={run} label={cardLabel} />
      {children}
    </section>
  );
}
