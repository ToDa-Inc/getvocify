import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CoachingCalls } from "@/features/coaching/rep/CoachingCalls";
import { CoachingPlaybook } from "@/features/coaching/rep/CoachingPlaybook";
import { useCoachCalls } from "@/features/coaching/rep/useRepCoaching";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { parseTab } from "@/lib/url-tab";

const TABS = ["calls", "playbook"] as const;

// The rep's own coaching (docs/superpowers/plans/2026-10-13-coaching-v2-comercial-y-conclusiones.md §2):
// what to improve and the calls behind it, and the playbook to read. It only composes.
export default function CoachPage() {
  const { t } = useLanguage();
  const p = t.product;
  // The selected tab lives in the URL (?tab=), so /dashboard/playbook and Ask can link to one; an old
  // link (?tab=summary, process, examples…) lands on the calls.
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"), TABS, "calls");
  const setTab = (next: string) =>
    setParams(
      (previous) => {
        const search = new URLSearchParams(previous);
        search.set("tab", next);
        return search;
      },
      { replace: true },
    );
  // null = the backend picks the type the rep had most conversations of.
  const [type, setType] = useState<string | null>(null);
  const calls = useCoachCalls(type);
  return (
    <main className={`max-w-3xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.navCoach}</h1>
        <p className={THEME_TOKENS.typography.body}>{p.coachSubtitle}</p>
      </div>
      <Tabs value={tab} onValueChange={setTab} className="space-y-6">
        <TabsList aria-label={p.navCoach} className={THEME_TOKENS.interaction.segmentList}>
          <TabsTrigger value="calls" data-testid="coach-tab-calls" className={THEME_TOKENS.interaction.segmentTab}>
            {p.coachTabCalls}
          </TabsTrigger>
          <TabsTrigger value="playbook" data-testid="coach-tab-playbook" className={THEME_TOKENS.interaction.segmentTab}>
            {p.coachTabPlaybook}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="calls" className="mt-0">
          <CoachingCalls type={type} onType={setType} />
        </TabsContent>
        <TabsContent value="playbook" className="mt-0">
          <CoachingPlaybook coachedMotion={calls.data?.type} />
        </TabsContent>
      </Tabs>
    </main>
  );
}
