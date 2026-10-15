import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { useLanguage } from "@/lib/i18n";
import { templateSteps } from "@/lib/playbook-editor";
import type { PlaybookDetail } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Coaching → Playbook: the playbook of the type the page is on, read-only. Its steps, what the
 * call has to find out and the answers to objections are the tabs of the document itself; the type
 * is the page's dropdown, so there is no second selector and no heading repeating it. */
export function CoachingPlaybook({ type, playbooks }: { type: string; playbooks?: { details?: Record<string, PlaybookDetail | undefined> } }) {
  const { language } = useLanguage();
  const lang = language === "EN" ? "en" : "es";
  const recognize = playbooks?.details?.[type]?.recognize;
  return (
    <div className="space-y-4 px-3" data-testid="coach-playbook">
      {recognize ? <p className={`${THEME_TOKENS.typography.body} max-w-3xl`}>{recognize}</p> : null}
      <PlaybookDocument key={type} motionKey={type} canEdit={false} template={() => templateSteps(type, lang)} />
    </div>
  );
}

/** "Empresa", read-only: the value story, customer stories and competitors a rep uses. */
export function CoachingCompany() {
  return (
    <div className="px-3" data-testid="coach-company">
      <CompanyKnowledge canEdit={false} />
    </div>
  );
}
