import { Navigate } from "react-router-dom";
import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { useAuth } from "@/features/auth";
import { RepHome } from "@/features/today/components/RepHome";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { isManagerRole, usesRepHome } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import HeadOfSalesSummaryPage from "./HeadOfSalesSummaryPage";

const DashboardHome = () => {
  const { user } = useAuth();
  // T9: send an owner/admin who hasn't finished onboarding to the wizard first.
  if (user?.company?.needsOnboarding) return <Navigate to="/dashboard/onboarding" replace />;
  // Head of Sales (HEAD_OF_SALES_DASHBOARD_PLAN §3.1): /dashboard is Resumen, never a
  // to-do list. A manager who also sells reaches their own Today from a link there.
  if (isManagerRole(user?.company?.role)) return <HeadOfSalesSummaryPage />;
  if (usesRepHome(user?.company)) return <RepHome />;
  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <TodayPanel />
      <ActivityPanel />
    </div>
  );
};

export default DashboardHome;
