import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { playbooksApi } from "@/features/playbooks/api";
import { COMPANY_KEY, PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { Segmented } from "@/components/ui/segmented";
import { isEmptyKnowledge } from "@/lib/playbook-knowledge";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { templateSteps } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Playbooks v2 (plan §4.4): the rep reads the process they are scored against, read-only.
 * `coached` is the type coaching reads for them: it opens first, not the alphabetically first one. */
function YourProcess({ coached }: { coached?: string | null }) {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const live = Object.entries(list.data?.motions ?? {})
    .filter(([, status]) => status === "published")
    .map(([key]) => key);
  const [picked, setPicked] = useState<string | null>(null);
  const fallback = coached && live.includes(coached) ? coached : live[0] ?? null;
  const active = picked && live.includes(picked) ? picked : fallback;
  const name = (key: string) =>
    list.data?.details?.[key]?.label || copy.typeLabels[key] || motionLabel(key, t.product.motions);

  return (
    <section aria-labelledby="your-process" className="space-y-4">
      <h2 id="your-process" className={THEME_TOKENS.typography.sectionTitle}>{copy.repHeading}</h2>
      {list.isLoading ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorLoading}</p> : null}
      {list.isError ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorLoadFailed}</p> : null}
      {list.isSuccess && !active ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorReadOnlyEmpty}</p> : null}
      {live.length > 1 ? (
        <Segmented
          value={active}
          onValueChange={setPicked}
          options={live.map((key) => ({ value: key, label: name(key) }))}
          aria-label={copy.repHeading}
        />
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
    <section aria-labelledby="your-company" className="space-y-4">
      <h2 id="your-company" className={THEME_TOKENS.typography.sectionTitle}>{t.product.pb2.companyReadHeading}</h2>
      <CompanyKnowledge canEdit={false} />
    </section>
  );
}

/** Coaching → Playbook: the process the rep is scored against, the company story, the best calls. */
/** Coaching → Playbook: the process the rep is coached against and the company's story, read-only.
 * Nothing about teammates: coaching is the rep against their own playbook. */
export function CoachingPlaybook({ coachedMotion }: { coachedMotion?: string | null }) {
  return (
    <div className="space-y-10 px-3" data-testid="coach-playbook">
      <YourProcess coached={coachedMotion} />
      <YourCompany />
    </div>
  );
}
