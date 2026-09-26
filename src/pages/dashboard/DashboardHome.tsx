import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { useAuth } from "@/features/auth";
import { RepHome } from "@/features/today/components/RepHome";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { usesRepHome } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const DashboardHome = () => {
  const { user } = useAuth();
  if (usesRepHome(user?.company)) return <RepHome />;
  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <TodayPanel />
      <ActivityPanel />
    </div>
  );
};

export default DashboardHome;
