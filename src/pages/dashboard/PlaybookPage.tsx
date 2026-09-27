import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { isManagerRole } from "@/lib/nav";
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

export default function PlaybookPage() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const p = t.product;
  const query = useQuery({
    queryKey: ["coaching-best"],
    queryFn: () => api.get<BestByFlow>("/coaching/best"),
    retry: false,
  });
  const manager = isManagerRole(user?.company?.role);
  // T11: opening the memo stays governed by the memo's own visibility, which this page
  // does not reimplement. It only offers the link for the author's own memo, or for a
  // manager, who already has broader read access elsewhere in the product.
  const canOpen = (item: BestItem) => manager || item.user_id === user?.id;
  const empty = query.isSuccess && FLOWS.every(({ flow }) => (query.data?.[flow]?.length ?? 0) === 0);

  return (
    <main className={`max-w-3xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.playbookPageTitle}</h1>
        <p className={THEME_TOKENS.typography.body}>{p.playbookPageSubtitle}</p>
      </div>
      {query.isLoading ? <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p> : null}
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
    </main>
  );
}
