import { Link, Navigate } from "react-router-dom";
import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { useAuth } from "@/features/auth";
import { RepHome } from "@/features/today/components/RepHome";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { useLanguage } from "@/lib/i18n";
import { isManagerRole, usesRepHome } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import TeamInsightsPage from "./TeamInsightsPage";

const DashboardHome = () => {
  const { user } = useAuth();
  const { t } = useLanguage();
  // T9: send an owner/admin who hasn't finished onboarding to the wizard first.
  if (user?.company?.needsOnboarding) return <Navigate to="/dashboard/onboarding" replace />;
  // T13: MANAGER_HOME_ENABLED makes /dashboard the Head of Sales' team home. A manager
  // who also sells (repWorkspace) keeps a link to their own Today rather than losing it.
  const managerHomeEnabled = Boolean(user?.company?.features?.includes("MANAGER_HOME_ENABLED"));
  if (managerHomeEnabled && isManagerRole(user?.company?.role)) {
    return (
      <div className={`max-w-5xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
        {usesRepHome(user?.company) ? (
          <div className="flex justify-end px-1 pb-2">
            <Link className="text-sm underline text-foreground" to="/dashboard/today">
              {t.product.managerHomeGoToToday}
            </Link>
          </div>
        ) : null}
        <TeamInsightsPage />
      </div>
    );
  }
  if (usesRepHome(user?.company)) return <RepHome />;
  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <TodayPanel />
      <ActivityPanel />
    </div>
  );
};

export default DashboardHome;
