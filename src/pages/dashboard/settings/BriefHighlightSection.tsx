import { BriefHighlightSettings } from "@/components/dashboard/settings/BriefHighlightSettings";
import { ReportPreferencesSettings } from "@/components/dashboard/settings/ReportPreferencesSettings";
import { WritingSamplesSettings } from "@/components/dashboard/settings/WritingSamplesSettings";
import { useAuth } from "@/features/auth";
import { isManagerRole } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** The brief highlight and writing samples are a rep's personal settings: the Head of Sales
 * (the only role that reaches this tab, see settings-nav) sees just the report preferences. */
const BriefHighlightSection = () => {
  const { user } = useAuth();
  const isManager = isManagerRole(user?.company?.role);
  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8 space-y-6`}>
      {!isManager && <BriefHighlightSettings />}
      {!isManager && <WritingSamplesSettings />}
      <ReportPreferencesSettings />
    </div>
  );
};

export default BriefHighlightSection;
