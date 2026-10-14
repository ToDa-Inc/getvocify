import { useQuery } from "@tanstack/react-query";
import { playbooksApi } from "@/features/playbooks/api";
import { COMPANY_KEY, PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { isEmptyKnowledge } from "@/lib/playbook-knowledge";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { templateSteps } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Playbooks v2 (plan §4.4): the rep reads only the playbook of their own process, the interaction
 * type Coaching is showing them; never the other types of the company. `coached` undefined means
 * Coaching is still loading; null, that it has no type for them yet. */
function YourProcess({ coached }: { coached?: string | null }) {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  // Only for the type's own name (a company's custom type); the document reads its own playbook.
  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const name = (key: string) =>
    list.data?.details?.[key]?.label || copy.typeLabels[key] || motionLabel(key, t.product.motions);

  return (
    <section aria-labelledby="your-process" className="space-y-4">
      <div className="space-y-0.5">
        <h2 id="your-process" className={THEME_TOKENS.typography.sectionTitle}>{copy.repHeading}</h2>
        {coached ? <p className="text-[13px] text-muted-foreground">{name(coached)}</p> : null}
      </div>
      {coached === undefined ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorLoading}</p> : null}
      {coached === null ? <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorReadOnlyEmpty}</p> : null}
      {coached ? (
        <PlaybookDocument key={coached} motionKey={coached} canEdit={false} template={() => templateSteps(coached, lang)} />
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
