import { useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { getUserDisplayName } from "@/features/auth/types";
import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { ContactPriorities } from "@/features/today/components/ContactPriorities";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";

const DashboardHome = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const displayName = user ? getUserDisplayName(user) : "User";

  return (
    <div className={`max-w-5xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Welcome back, <span className={THEME_TOKENS.typography.accentTitle}>{displayName.split(" ")[0]}</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Ready to update your CRM?</p>
      </div>

      <TodayPanel />

      <VoiceRecorderWidget
        onComplete={(memoId) => navigate(`/dashboard/memos/${memoId}`)}
      />

      <ContactPriorities hideEmpty />
      <ActivityPanel />
    </div>
  );
};

export default DashboardHome;
