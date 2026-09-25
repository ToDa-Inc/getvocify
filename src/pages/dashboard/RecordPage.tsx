import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { ROUTES } from "@/shared/lib/constants";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { isDesktopHost } from "@/lib/desktop-host";

const RecordPage = () => {
  const inDesktopApp = isDesktopHost();
  const navigate = useNavigate();

  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <Link
        to={ROUTES.DASHBOARD}
        className={`inline-flex items-center gap-2 ${THEME_TOKENS.typography.capsLabel} text-muted-foreground/60 hover:text-beige transition-colors group`}
      >
        <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
        Back to Dashboard
      </Link>

      <div className={V_PATTERNS.dashboardHeader + " text-center"}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          New <span className={THEME_TOKENS.typography.accentTitle}>Memo</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          {inDesktopApp
            ? "Record a meeting with mic and system audio, or import a transcript."
            : "Record a voice memo or import a meeting transcript. For Zoom, Meet, or Teams system audio (Granola-style, no meeting bot), use the Vocify Mac app."}
        </p>
      </div>

      <VoiceRecorderWidget
        onComplete={(memoId) => navigate(ROUTES.MEMO_DETAIL(memoId))}
      />
    </div>
  );
};

export default RecordPage;
