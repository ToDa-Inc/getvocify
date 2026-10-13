import { TranscriptionLanguageSettings } from "@/components/dashboard/settings/TranscriptionLanguageSettings";
import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`;

/** How Vocify hears calls and meetings: the rep's own languages, then the company glossary. */
const TranscriptionSection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  return (
    <div className="space-y-6">
      <div className={card}>
        <TranscriptionLanguageSettings />
      </div>
      <div className={card}>
        <UserGlossary readOnly={!canManage} />
      </div>
    </div>
  );
};

export default TranscriptionSection;
