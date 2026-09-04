import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { formatRecordedAtLabel } from "@/lib/memo-dates";
import { Mic } from "lucide-react";
import { useAuth } from "@/features/auth";
import { getUserDisplayName } from "@/features/auth/types";
import { memosApi, memoKeys } from "@/features/memos/api";
import type { MemoStatus, ScreeningOutcome } from "@/features/memos/types";
import { memoListTitle, memoListSubtitle } from "@/lib/copilot-note";
import { RecordingsPanel } from "@/components/dashboard/RecordingsPanel";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";

const getStatusBadge = (status: MemoStatus, screeningOutcome?: ScreeningOutcome | null) => {
  if (status === "pending_review") {
    if (screeningOutcome === "voicemail") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-muted text-muted-foreground">
          Buzón de voz
        </span>
      );
    }
    if (screeningOutcome === "no_response") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-muted text-muted-foreground">
          Sin respuesta
        </span>
      );
    }
  }
  switch (status) {
    case "approved":
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-success/10 text-success">
          Approved
        </span>
      );
    case "pending_review":
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-warning/10 text-warning">
          Pending review
        </span>
      );
    case "pending_transcript":
    case "uploading":
    case "transcribing":
    case "extracting":
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-muted text-muted-foreground">
          Processing
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-destructive/10 text-destructive">
          Failed
        </span>
      );
    case "rejected":
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-muted text-muted-foreground">
          Rejected
        </span>
      );
    default:
      return null;
  }
};

const DashboardHome = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const displayName = user ? getUserDisplayName(user) : "User";

  const { data: recentMemos = [], isLoading: memosLoading } = useQuery({
    queryKey: memoKeys.list({ limit: 5 }),
    queryFn: () => memosApi.list({ limit: 5 }),
  });

  return (
    <div className={`max-w-5xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      {/* Welcome Header */}
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Welcome back, <span className={THEME_TOKENS.typography.accentTitle}>{displayName.split(' ')[0]}</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Ready to update your CRM?</p>
      </div>

      {/* Embedded Live Recorder & Quick Ingest Widget */}
      <VoiceRecorderWidget
        onComplete={(memoId) => navigate(`/dashboard/memos/${memoId}`)}
      />

      <RecordingsPanel />

      {/* Recent Memos */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>Recent Memos</h2>
          <Link
            to="/dashboard/memos"
            className={`${THEME_TOKENS.typography.capsLabel} text-beige hover:underline`}
          >
            View all
          </Link>
        </div>
        <div className="space-y-4">
          {memosLoading ? (
            <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center`}>
              <div className="w-6 h-6 border-2 border-beige border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className={THEME_TOKENS.typography.capsLabel}>Loading memos...</p>
            </div>
          ) : recentMemos.length === 0 ? (
            <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center`}>
              <p className="text-muted-foreground">No memos yet. Record your first one above.</p>
            </div>
          ) : (
            recentMemos.map((memo) => {
              const title = memoListTitle(memo);
              const subtitle = memoListSubtitle(memo);
              const preview =
                subtitle ||
                (memo.extraction?.summary
                  ? String(memo.extraction.summary).replace(/^#+\s+/gm, " ").replace(/\s+/g, " ").trim()
                  : memo.transcript) ||
                "No preview yet.";

              return (
                <Link
                  key={memo.id}
                  to={`/dashboard/memos/${memo.id}`}
                  className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${THEME_TOKENS.cards.hover} ${V_PATTERNS.listItem} group`}
                >
                  <div className="flex items-center gap-6">
                    <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center flex-shrink-0">
                      <Mic className="h-5 w-5 text-beige" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <h3 className="font-normal text-foreground text-[15px] truncate">
                        {title}
                      </h3>
                      <p className="text-sm text-muted-foreground line-clamp-1 truncate mt-1 leading-relaxed">
                        {preview}
                      </p>
                    </div>

                    <div className="flex flex-col items-end gap-3 flex-shrink-0">
                      {getStatusBadge(memo.status, memo.screeningOutcome)}
                      <span className={`${THEME_TOKENS.typography.capsLabel} text-right max-w-[11rem] leading-snug`}>
                        {formatRecordedAtLabel(memo.createdAt)}
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};

export default DashboardHome;
