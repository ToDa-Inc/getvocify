import { useState } from "react";
import { CoachingExamples } from "@/features/coaching/rep/CoachingExamples";
import { CoachingInteractions } from "@/features/coaching/rep/CoachingInteractions";
import { CoachingProcess } from "@/features/coaching/rep/CoachingProcess";
import { CoachingSummary } from "@/features/coaching/rep/CoachingSummary";
import { useCoachSummary } from "@/features/coaching/rep/useRepCoaching";
import { useLanguage } from "@/lib/i18n";
import { interactionsTabKey } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";

type Tab = "summary" | "interactions" | "process" | "examples";

// The rep's own coaching page (docs/features/COACHING_V1_IMPLEMENTATION.md §5). It only composes.
export default function CoachPage() {
  const { t } = useLanguage();
  const p = t.product;
  const [tab, setTab] = useState<Tab>("summary");
  const summary = useCoachSummary();
  const tabs: { id: Tab; label: string }[] = [
    { id: "summary", label: p.coachTabSummary },
    { id: "interactions", label: String(p[interactionsTabKey(summary.data?.flow)]) },
    { id: "process", label: p.coachTabProcess },
    { id: "examples", label: p.coachTabExamples },
  ];
  return (
    <main className={`max-w-3xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.navCoach}</h1>
        <p className={THEME_TOKENS.typography.body}>{p.coachSubtitle}</p>
      </div>
      <div role="group" className="inline-flex flex-wrap rounded-full border border-border bg-card p-1">
        {tabs.map((option) => (
          <button
            key={option.id}
            type="button"
            data-testid={`coach-tab-${option.id}`}
            aria-pressed={tab === option.id}
            onClick={() => setTab(option.id)}
            className={`rounded-full px-3.5 py-1 text-xs transition-colors ${
              tab === option.id ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {tab === "summary" ? <CoachingSummary onOpenProcess={() => setTab("process")} /> : null}
      {tab === "interactions" ? <CoachingInteractions /> : null}
      {tab === "process" ? <CoachingProcess /> : null}
      {tab === "examples" ? <CoachingExamples /> : null}
    </main>
  );
}
