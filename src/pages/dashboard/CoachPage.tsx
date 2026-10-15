import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { BarChart3, BookOpen, Building2 } from "lucide-react";
import { Segmented } from "@/components/ui/segmented";
import { CoachingCalls } from "@/features/coaching/rep/CoachingCalls";
import { CoachingCompany, CoachingPlaybook } from "@/features/coaching/rep/CoachingPlaybook";
import { CoachEmpty, CoachError, CoachLoading } from "@/features/coaching/rep/CoachingState";
import { TypePicker } from "@/features/coaching/rep/TypePicker";
import { useCoachCalls } from "@/features/coaching/rep/useRepCoaching";
import { playbooksApi } from "@/features/playbooks/api";
import { COMPANY_KEY, PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { useLanguage } from "@/lib/i18n";
import { isEmptyKnowledge } from "@/lib/playbook-knowledge";
import { THEME_TOKENS } from "@/lib/theme/tokens";

type View = "progress" | "playbook" | "company";

// The rep's own coaching (docs/superpowers/plans/2026-10-13-coaching-v2-comercial-y-conclusiones.md §2).
// One page, two questions: which interaction type (a dropdown, always visible) and what to look at
// (how I am doing, or the playbook I am coached against). Both live in the URL, so the playbook of
// the type on screen is one click away and any of it can be linked to.
export default function CoachPage() {
  const { t } = useLanguage();
  const p = t.product;
  const [params, setParams] = useSearchParams();
  const change = (key: "tab" | "type", value: string | null, replace = false) =>
    setParams(
      (previous) => {
        const search = new URLSearchParams(previous);
        if (value) search.set(key, value);
        else search.delete(key);
        return search;
      },
      { replace },
    );

  // null = the backend picks the type the rep had most conversations of.
  const type = params.get("type");
  const calls = useCoachCalls(type);
  const playbooks = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const company = useQuery({ queryKey: COMPANY_KEY, queryFn: playbooksApi.company, retry: false });
  const hasCompany = Boolean(company.data) && !isEmptyKnowledge(company.data?.knowledge);

  const asked = params.get("tab");
  const view: View = asked === "playbook" ? "playbook" : asked === "company" && hasCompany ? "company" : "progress";
  const data = calls.data;
  // What was asked for shows at once; the backend's pick (the type with most conversations) only when nothing valid was asked.
  const active = (type && data?.types.some((option) => option.key === type) ? type : data?.type) ?? null;

  const views = [
    { value: "progress" as const, label: <><BarChart3 aria-hidden size={14} strokeWidth={1.5} />{p.coachViewProgress}</> },
    { value: "playbook" as const, label: <><BookOpen aria-hidden size={14} strokeWidth={1.5} />{p.coachTabPlaybook}</> },
    ...(hasCompany ? [{ value: "company" as const, label: <><Building2 aria-hidden size={14} strokeWidth={1.5} />{p.coachViewCompany}</> }] : []),
  ];

  const body = () => {
    if (view === "company") return <CoachingCompany />;
    if (calls.isError) return <CoachError onRetry={() => void calls.refetch()} />;
    if (!data) return <CoachLoading />;
    if (!active) return <CoachEmpty text={p.coachNoPlaybook} />;
    if (view === "playbook") return <CoachingPlaybook type={active} playbooks={playbooks.data} />;
    // The previous type's numbers stay, dimmed, until the new ones arrive: no blank page between types.
    return (
      <div className={calls.isPlaceholderData ? "pointer-events-none opacity-50 transition-opacity" : "transition-opacity"}>
        <CoachingCalls data={data} />
      </div>
    );
  };

  return (
    <main className={`w-full space-y-10 ${THEME_TOKENS.motion.fadeIn}`}>
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-3">
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.navCoach}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {view !== "company" && data && active ? (
            <TypePicker types={data.types} value={active} onChange={(key) => change("type", key, true)} playbooks={playbooks.data} />
          ) : null}
          <Segmented<View> value={view} onValueChange={(next) => change("tab", next === "progress" ? null : next)} options={views} aria-label={p.coachViewLabel} />
        </div>
      </header>
      {body()}
    </main>
  );
}
