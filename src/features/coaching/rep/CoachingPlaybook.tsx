import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { playbooksApi } from "@/features/playbooks/api";
import { COMPANY_KEY, PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { isEmptyKnowledge } from "@/lib/playbook-knowledge";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { templateSteps } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api } from "@/shared/lib/api-client";

type BestItem = {
  memo_id: string;
  user_id: string;
  author: string;
  date: string;
  value: number;
  highlights: string[];
};

type BestByFlow = { sdr: BestItem[]; ae: BestItem[] };

const FLOWS: { flow: keyof BestByFlow; motion: "discovery" | "closing" }[] = [
  { flow: "sdr", motion: "discovery" },
  { flow: "ae", motion: "closing" },
];

/** Playbooks v2 (plan §4.4): the rep reads the process they are scored against, read-only. */
function YourProcess() {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const live = Object.entries(list.data?.motions ?? {})
    .filter(([, status]) => status === "published")
    .map(([key]) => key);
  const [picked, setPicked] = useState<string | null>(null);
  const active = picked && live.includes(picked) ? picked : live[0] ?? null;
  const name = (key: string) =>
    list.data?.details?.[key]?.label || copy.typeLabels[key] || motionLabel(key, t.product.motions);

  return (
    <section aria-labelledby="your-process" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-4 p-5 md:p-6`}>
      <h2 id="your-process" className={THEME_TOKENS.typography.sectionTitle}>{copy.repHeading}</h2>
      {list.isLoading ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorLoading}</p> : null}
      {list.isError ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorLoadFailed}</p> : null}
      {list.isSuccess && !active ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorReadOnlyEmpty}</p> : null}
      {live.length > 1 ? (
        <div className="flex flex-wrap gap-1" role="tablist">
          {live.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === active}
              className={`rounded-full px-3 py-1 text-[13px] transition-colors ${
                key === active ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              }`}
              onClick={() => setPicked(key)}
            >
              {name(key)}
            </button>
          ))}
        </div>
      ) : null}
      {active ? (
        <PlaybookDocument
          key={active}
          motionKey={active}
          canEdit={false}
          template={() => templateSteps(active, lang)}
          meta={live.length === 1 ? <p className={THEME_TOKENS.typography.capsLabel}>{name(active)}</p> : null}
        />
      ) : null}
    </section>
  );
}

/** "Vuestra empresa", read-only: the value story, customer stories and competitors a rep uses. */
function YourCompany() {
  const { t } = useLanguage();
  const company = useQuery({ queryKey: COMPANY_KEY, queryFn: playbooksApi.company, retry: false });
  if (!company.data || isEmptyKnowledge(company.data.knowledge)) return null;
  return (
    <section aria-labelledby="your-company" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-4 p-5 md:p-6`}>
      <h2 id="your-company" className={THEME_TOKENS.typography.sectionTitle}>{t.product.pb2.companyReadHeading}</h2>
      <CompanyKnowledge canEdit={false} />
    </section>
  );
}

/** Coaching → Playbook: the process the rep is scored against, the company story, the best calls. */
export function CoachingPlaybook() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const p = t.product;
  // The best calls are their own flag (GET /coaching/best is gated by it); the process is not.
  const bestEnabled = Boolean(user?.company?.features?.includes("PLAYBOOK_TAB_ENABLED"));
  const query = useQuery({
    queryKey: ["coaching-best"],
    queryFn: () => api.get<BestByFlow>("/coaching/best"),
    retry: false,
    enabled: bestEnabled,
  });
  // T11: opening the memo stays governed by the memo's own visibility, which this tab does
  // not reimplement. Coaching is the rep's page, so it only links the rep's own memos.
  const canOpen = (item: BestItem) => item.user_id === user?.id;
  const empty = query.isSuccess && FLOWS.every(({ flow }) => (query.data?.[flow]?.length ?? 0) === 0);

  return (
    <div className="space-y-6" data-testid="coach-playbook">
      <YourProcess />
      <YourCompany />
      {bestEnabled ? <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.pb2.bestHeading}</h2> : null}
      {query.isLoading && bestEnabled ? <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p> : null}
      {query.isError ? <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p> : null}
      {empty ? <p className={THEME_TOKENS.typography.body}>{p.playbookPageEmpty}</p> : null}
      {FLOWS.map(({ flow, motion }) => {
        const items = query.data?.[flow] ?? [];
        if (items.length === 0) return null;
        return (
          <section
            key={flow}
            aria-labelledby={`playbook-${flow}`}
            className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-4`}
          >
            <h2 id={`playbook-${flow}`} className={THEME_TOKENS.typography.sectionTitle}>
              {p.playbookFlowLabels[motion]}
            </h2>
            <ul className="space-y-4">
              {items.map((item) => (
                <li key={item.memo_id} className="space-y-1 border-t border-border/40 pt-3 first:border-t-0 first:pt-0">
                  <div className="flex justify-between gap-4 text-sm">
                    <span>{item.author}</span>
                    <span>{p.playbookBestScore.replace("{value}", String(item.value))}</span>
                  </div>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {item.highlights.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                  {canOpen(item) ? (
                    <Link className="text-sm text-foreground underline" to={`/dashboard/memos/${item.memo_id}`}>
                      {p.playbookOpenMemo}
                    </Link>
                  ) : (
                    <p className="text-sm text-muted-foreground">{p.playbookNotYours}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
