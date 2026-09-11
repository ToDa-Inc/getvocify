import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const GlossarySection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
      <UserGlossary readOnly={!canManage} />
    </div>
  );
};

export default GlossarySection;
