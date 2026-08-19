import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Mic } from "lucide-react";
import { useAuth } from "@/features/auth";
import { getUserDisplayName } from "@/features/auth/types";
import { Button } from "@/components/ui/button";
import { memosApi, memoKeys } from "@/features/memos/api";
import type { Memo, MemoStatus } from "@/features/memos/types";

const getStatusBadge = (status: MemoStatus) => {
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

import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";

const PREVIEW_MAX_LEN = 80;

const DashboardHome = () => {
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

      {/* Record Card */}
      <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} ${V_PATTERNS.focusBox}`}>
        <div className="w-14 h-14 mx-auto mb-6 rounded-2xl bg-beige text-cream flex items-center justify-center">
          <Mic className="h-6 w-6" />
        </div>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-4`}>Record your meeting notes</h2>
        <Button variant="hero" size="xl" asChild className="px-8">
          <Link to="/dashboard/record">
            <Mic className="h-4 w-4 mr-2" />
            Start Recording
          </Link>
        </Button>
        <p className={`text-sm ${THEME_TOKENS.colors.muted} mt-4`}>
          Speak for 30-120 seconds about your meeting
        </p>
      </div>

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
              const company = memo.extraction?.companyName?.trim() || "Untitled memo";
              const preview =
                memo.extraction?.summary?.trim() ||
                memo.transcript?.trim() ||
                "No preview yet.";
              const previewShort =
                preview.length > PREVIEW_MAX_LEN ? preview.slice(0, PREVIEW_MAX_LEN) + "…" : preview;
              return (
                <Link
                  key={memo.id}
                  to={`/dashboard/memos/${memo.id}`}
                  className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${THEME_TOKENS.cards.hover} ${V_PATTERNS.listItem} group`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-normal text-foreground text-[15px] truncate">
                        {company}
                      </h3>
                      <p className="text-sm text-muted-foreground truncate mt-1 leading-relaxed">
                        {previewShort}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-3">
                      {getStatusBadge(memo.status)}
                      <span className={THEME_TOKENS.typography.capsLabel}>
                        {formatDistanceToNow(new Date(memo.createdAt), { addSuffix: true })}
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
