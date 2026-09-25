import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const DashboardHome = () => {
  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <TodayPanel />
      <ActivityPanel />
    </div>
  );
};

export default DashboardHome;
