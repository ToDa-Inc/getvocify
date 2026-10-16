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

/** The sentence and the main button for where the guided questions stand. */
export function hubTexts(session: GapSession | null | undefined, notActivated: boolean, c: ReturnType<typeof useHubCopy>) {
  if (notActivated) return { line: c.notActivated, primary: c.hubStartAssistant };
  const left = session ? Math.max(session.total - session.answered - session.skipped, 0) : 0;
  if (session && left > 0) {
    return { line: left === 1 ? c.hubOpenOne : c.hubOpen.replace("{count}", String(left)), primary: c.hubContinueAssistant };
  }
  return { line: c.hubFresh, primary: c.hubStartAssistant };
}

function useHubCopy() {
  return useLanguage().t.product.pb2.improve;
}

/** The hub wired to the company's open session of guided questions. */
export function ImproveHub({ view, views, onView }: { view: ImproveView | null; views: readonly ImproveView[]; onView: (view: ImproveView | null) => void }) {
  const c = useHubCopy();
  const current = useQuery({ queryKey: ASSISTANT_QUERY, queryFn: assistantApi.currentGaps, retry: false, staleTime: 60_000 });
  const { line, primary } = hubTexts(current.data?.session, isNotActivated(current.error), c);
  return <ImproveHubView view={view} views={views} line={line} primaryLabel={primary} onView={onView} onPrimary={() => onView("assistant")} />;
}
