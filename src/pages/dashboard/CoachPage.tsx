import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CoachingCalls } from "@/features/coaching/rep/CoachingCalls";
import { CoachingPlaybook } from "@/features/coaching/rep/CoachingPlaybook";
import { useCoachCalls } from "@/features/coaching/rep/useRepCoaching";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

// The rep's own coaching (docs/superpowers/plans/2026-10-13-coaching-v2-comercial-y-conclusiones.md §2):
// one plane with what to improve and the record of their calls; the playbook one click away.
export default function CoachPage() {
  const { t } = useLanguage();
  const p = t.product;
  // ?tab=playbook opens the playbook, so /dashboard/playbook and Ask can link to it; anything else is coaching.
  const [params, setParams] = useSearchParams();
  const playbook = params.get("tab") === "playbook";
  const show = (next: "playbook" | null) =>
    setParams((previous) => {
      const search = new URLSearchParams(previous);
      if (next) search.set("tab", next);
      else search.delete("tab");
      return search;
    });
  // null = the backend picks the type the rep had most conversations of.
  const [type, setType] = useState<string | null>(null);
  const calls = useCoachCalls(type);
  // Edge to edge within the page's margins and 12px in, like Inicio.
  return (
    <main className={`w-full space-y-10 ${THEME_TOKENS.motion.fadeIn}`}>
      <header className="flex items-center justify-between gap-4 px-3">
        <h1 className={THEME_TOKENS.typography.pageTitle}>{playbook ? p.coachTabPlaybook : p.navCoach}</h1>
        {playbook ? (
          <Button type="button" variant="outline" size="sm" onClick={() => show(null)} data-testid="coach-back">
            <ArrowLeft aria-hidden strokeWidth={1.5} />
            {p.navCoach}
          </Button>
        ) : (
          <Button type="button" variant="outline" size="sm" onClick={() => show("playbook")} data-testid="coach-open-playbook">
            <BookOpen aria-hidden strokeWidth={1.5} />
            {p.coachTabPlaybook}
          </Button>
        )}
      </header>
      {playbook ? <CoachingPlaybook coachedMotion={calls.data?.type} /> : <CoachingCalls type={type} onType={setType} />}
    </main>
  );
}
