import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const GlossarySection = () => {
  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
      <UserGlossary />
    </div>
  );
};

export default GlossarySection;
