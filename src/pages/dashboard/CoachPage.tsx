import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CoachingExamples } from "@/features/coaching/rep/CoachingExamples";
import { CoachingInteractions } from "@/features/coaching/rep/CoachingInteractions";
import { CoachingPlaybook } from "@/features/coaching/rep/CoachingPlaybook";
import { CoachingProcess } from "@/features/coaching/rep/CoachingProcess";
import { CoachingSummary } from "@/features/coaching/rep/CoachingSummary";
import { useCoachSummary } from "@/features/coaching/rep/useRepCoaching";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { canPickFlow, interactionsTabKey, viewingFlowKey, type CoachFlow } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { parseTab } from "@/lib/url-tab";

const TABS = ["summary", "interactions", "process", "playbook", "examples"] as const;
type Tab = (typeof TABS)[number];

// The rep's own coaching page (docs/features/COACHING_V1_IMPLEMENTATION.md §5). It only composes.
export default function CoachPage() {
  const { t } = useLanguage();
  const p = t.product;
  // The selected tab lives in the URL (?tab=), so /dashboard/playbook and Ask can link to one.
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"), TABS, "summary");
  const setTab = (next: string) =>
    setParams(
      (previous) => {
        const search = new URLSearchParams(previous);
        search.set("tab", next);
        return search;
      },
      { replace: true },
    );
  const { user } = useAuth();
  const salesRole = user?.company?.salesRole;
  // null = let the backend resolve the default; only a general rep ever sets it.
  const [picked, setPicked] = useState<CoachFlow | null>(null);
  const summary = useCoachSummary(picked);
  const flow: CoachFlow | null = summary.data?.flow ?? picked;
  const showToggle = canPickFlow(salesRole, summary.data?.available_flows);
  const viewingKey = viewingFlowKey(salesRole, summary.data?.available_flows, summary.data?.flow);
  const tabs: { id: Tab; label: string }[] = [
    { id: "summary", label: p.coachTabSummary },
    { id: "interactions", label: String(p[interactionsTabKey(flow)]) },
    { id: "process", label: p.coachTabProcess },
    { id: "playbook", label: p.coachTabPlaybook },
    { id: "examples", label: p.coachTabExamples },
  ];
  return (
    <main className={`max-w-3xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.navCoach}</h1>
        <p className={THEME_TOKENS.typography.body}>{p.coachSubtitle}</p>
      </div>
      <Tabs value={tab} onValueChange={setTab} className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <TabsList aria-label={p.navCoach} className={THEME_TOKENS.interaction.segmentList}>
            {tabs.map((option) => (
              <TabsTrigger key={option.id} value={option.id} data-testid={`coach-tab-${option.id}`} className={THEME_TOKENS.interaction.segmentTab}>
                {option.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {/* The playbook has its own type picker: the SDR/AE flow says nothing there. */}
          {tab === "playbook" ? null : showToggle ? (
            <div role="group" aria-label={p.coachFlowLabel} className="inline-flex rounded-full border border-border bg-card p-1" data-testid="coach-flow-toggle">
              {(["sdr", "ae"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  data-testid={`coach-flow-${option}`}
                  aria-pressed={flow === option}
                  onClick={() => setPicked(option)}
                  className={`rounded-full px-3.5 py-1 text-xs transition-colors ${
                    flow === option ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {option === "ae" ? p.coachFlowMeetings : p.coachFlowCalls}
                </button>
              ))}
            </div>
          ) : viewingKey ? (
            <p className="text-xs text-muted-foreground" data-testid="coach-viewing-flow">
              {p[viewingKey]}
            </p>
          ) : null}
        </div>
        <TabsContent value="summary" className="mt-0">
          <CoachingSummary flow={picked} onOpenProcess={() => setTab("process")} />
        </TabsContent>
        <TabsContent value="interactions" className="mt-0">
          <CoachingInteractions flow={picked} />
        </TabsContent>
        <TabsContent value="process" className="mt-0">
          <CoachingProcess flow={picked} />
        </TabsContent>
        <TabsContent value="playbook" className="mt-0">
          <CoachingPlaybook />
        </TabsContent>
        <TabsContent value="examples" className="mt-0">
          <CoachingExamples flow={picked} />
        </TabsContent>
      </Tabs>
    </main>
  );
}
