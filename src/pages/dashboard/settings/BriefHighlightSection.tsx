import { BriefHighlightSettings } from "@/components/dashboard/settings/BriefHighlightSettings";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const BriefHighlightSection = () => (
  <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
    <BriefHighlightSettings />
  </div>
);

export default BriefHighlightSection;
