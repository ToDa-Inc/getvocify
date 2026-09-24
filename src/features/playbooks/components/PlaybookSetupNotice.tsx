import { useLanguage } from "@/lib/i18n";
import { playbookNotice, type MotionStatus, type PlaybookRole } from "@/lib/playbook-setup";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export function PlaybookSetupNotice({
  role,
  motions,
}: {
  role: PlaybookRole;
  motions: Record<string, MotionStatus>;
}) {
  const { t } = useLanguage();
  const notice = playbookNotice(role, motions);
  if (!notice.showNotice) return null;
  const steps = [
    t.product.playbookStepChoose,
    t.product.playbookStepProvide,
    t.product.playbookStepReview,
    t.product.playbookStepPublish,
  ];
  return (
    <section className="rounded-lg bg-secondary/40 p-4" role="status">
      <p className={THEME_TOKENS.typography.body}>{productText(notice.message, t.product)}</p>
      {notice.canEdit ? (
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-foreground">
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
