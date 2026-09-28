import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

// Lista 4 E5: the rep's own coaching page (their metrics, adherence, objections and call
// feedback). T6 fills it from GET /coach/me; for now it only holds the route.
export default function CoachPage() {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <main className={`max-w-3xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.navCoach}</h1>
        <p className={THEME_TOKENS.typography.body}>{p.coachPageSubtitle}</p>
      </div>
    </main>
  );
}
