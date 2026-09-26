import { BriefHighlightSettings } from "@/components/dashboard/settings/BriefHighlightSettings";
import { ReportPreferencesSettings } from "@/components/dashboard/settings/ReportPreferencesSettings";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const BriefHighlightSection = () => (
  <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8 space-y-6`}>
    <BriefHighlightSettings />
    <ReportPreferencesSettings />
  </div>
);

export default BriefHighlightSection;
