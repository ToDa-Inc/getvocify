import { useNavigate } from "react-router-dom";
import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const DashboardHome = () => {
  const navigate = useNavigate();

  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div id="hoy-capture">
        <VoiceRecorderWidget
          onComplete={(memoId) => navigate(`/dashboard/memos/${memoId}`)}
        />
      </div>
      <TodayPanel />
      <ActivityPanel />
    </div>
  );
};

export default DashboardHome;
