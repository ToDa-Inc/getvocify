import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { assistantApi, isNotActivated, type GapSession } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";
import type { ImproveView } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
export const ASSISTANT_QUERY = ["playbook-assistant", "current"] as const;
export const STATS_QUERY = ["playbook-assistant", "improve-stats"] as const;

export type ImproveHubViewProps = {
  view: ImproveView | null;
  /** The views that exist today; with a single one there is nothing to switch. */
  views: readonly ImproveView[];
  /** One sentence about where the Head of Sales stands; the screen never shows more than this. */
  line: string;
  primaryLabel: string;
  onView: (view: ImproveView | null) => void;
  onPrimary: () => void;
};

/**
 * The door to improving the playbook, first thing on the Playbook page for an owner or admin: where they stand in one
 * sentence, ONE main button for the next step, and (once there is more than one) the views as a pill row. Inside a view
 * the main button becomes the way back, so there is never a dead end.
 */
export function ImproveHubView({ view, views, line, primaryLabel, onView, onPrimary }: ImproveHubViewProps) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const label: Record<ImproveView, string> = { assistant: c.viewAssistant, trial: c.viewTrial, improve: c.viewImprove };
  return (
    <section aria-labelledby="improve-hub" className={cn(card, "flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between md:p-5", THEME_TOKENS.motion.fadeIn)}>
      <div className="min-w-0 space-y-1">
        <h2 id="improve-hub" className={THEME_TOKENS.typography.sectionTitle}>
          {c.hubTitle}
        </h2>
        <p className="max-w-xl text-[13px] leading-snug text-muted-foreground">{line}</p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {views.length > 1 ? (
          <Segmented<ImproveView | "none">
            aria-label={c.viewsLabel}
            value={view ?? "none"}
            onValueChange={(next) => next !== "none" && onView(next)}
            options={views.map((value) => ({ value, label: label[value] }))}
          />
        ) : null}
        {view ? (
          <Button type="button" variant="outline" size="sm" onClick={() => onView(null)}>
            <ArrowLeft aria-hidden strokeWidth={1.5} />
            {c.back}
          </Button>
        ) : (
          <Button type="button" size="sm" onClick={onPrimary}>
            {primaryLabel}
          </Button>
        )}
      </div>
    </section>
  );
}

/**
 * The sentence and the main button for where the Head of Sales stands: questions still open come first, then the answers
 * the queue is waiting on, and otherwise the guided questions start from the top.
 */
export function hubTexts(session: GapSession | null | undefined, notActivated: boolean, c: ReturnType<typeof useHubCopy>, queueAnswers = 0) {
  if (notActivated) return { line: c.notActivated, primary: c.hubStartAssistant, view: "assistant" as const };
  const left = session ? Math.max(session.total - session.answered - session.skipped, 0) : 0;
  if (session && left > 0) {
    return { line: left === 1 ? c.hubOpenOne : c.hubOpen.replace("{count}", String(left)), primary: c.hubContinueAssistant, view: "assistant" as const };
  }
  if (queueAnswers > 0) {
    return { line: queueAnswers === 1 ? c.hubQueueOne : c.hubQueue.replace("{count}", String(queueAnswers)), primary: c.hubImprove, view: "improve" as const };
  }
  return { line: c.hubFresh, primary: c.hubStartAssistant, view: "assistant" as const };
}

function useHubCopy() {
  return useLanguage().t.product.pb2.improve;
}

/** The hub wired to the company's open session of guided questions. */
export function ImproveHub({ view, views, onView }: { view: ImproveView | null; views: readonly ImproveView[]; onView: (view: ImproveView | null) => void }) {
  const c = useHubCopy();
  const current = useQuery({ queryKey: ASSISTANT_QUERY, queryFn: assistantApi.currentGaps, retry: false, staleTime: 60_000 });
  // The queue of answers that keep failing, when the success rate is on: a quiet reminder, never an error.
  const stats = useQuery({ queryKey: STATS_QUERY, queryFn: assistantApi.improveStats, retry: false, staleTime: 60_000, enabled: views.includes("improve") });
  const { line, primary, view: next } = hubTexts(current.data?.session, isNotActivated(current.error), c, stats.data?.queue?.answers ?? 0);
  return <ImproveHubView view={view} views={views} line={line} primaryLabel={primary} onView={onView} onPrimary={() => onView(next)} />;
}
