import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Bot } from "lucide-react";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth";
import { DesktopPermissionsPanel } from "@/features/desktop/DesktopPermissionsPanel";
import { useDesktopMeeting } from "@/features/desktop/DesktopMeetingProvider";
import { MeetingLiveView } from "@/features/desktop/MeetingLiveView";
import { meetingsApi } from "@/features/meetings/api";
import { ApiError } from "@/shared/lib/api-client";
import { ROUTES } from "@/shared/lib/constants";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { isDesktopHost } from "@/lib/desktop-host";

// T14: RECALL_BOT_ENABLED. A Recall.ai bot joins a Zoom/Meet/Teams meeting and its
// transcript completes a capture the same way a desktop capture does - see
// backend/app/api/webhooks.py's /recall handler.
const RecallBotForm = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [meetingUrl, setMeetingUrl] = useState("");

  const { mutate, isPending } = useMutation({
    mutationFn: (url: string) => meetingsApi.createBot(url),
    onSuccess: (result) => {
      toast.success(t.product.recallBotSuccess);
      setMeetingUrl("");
      navigate(ROUTES.MEMO_DETAIL(result.memoId));
    },
    onError: (error: unknown) => {
      const message =
        error instanceof ApiError && error.status === 503
          ? t.product.recallBotErrorNotConfigured
          : t.product.recallBotErrorGeneric;
      toast.error(message);
    },
  });

  return (
    <form
      className="space-y-3 rounded-xl border border-border/40 bg-card/40 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        const url = meetingUrl.trim();
        if (!url || isPending) return;
        mutate(url);
      }}
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <Bot className="h-4 w-4" />
        {t.product.recallBotLabel}
      </div>
      <p className={THEME_TOKENS.typography.body}>{t.product.recallBotHint}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          type="url"
          value={meetingUrl}
          onChange={(event) => setMeetingUrl(event.target.value)}
          placeholder={t.product.recallBotPlaceholder}
          disabled={isPending}
        />
        <Button type="submit" disabled={isPending || !meetingUrl.trim()}>
          {isPending ? t.product.recallBotSending : t.product.recallBotSubmit}
        </Button>
      </div>
    </form>
  );
};

const RecordPage = () => {
  const inDesktopApp = isDesktopHost();
  const navigate = useNavigate();
  const { user } = useAuth();
  const recallBotEnabled = Boolean(user?.company?.features?.includes("RECALL_BOT_ENABLED"));
  const meeting = useDesktopMeeting();

  if (meeting.available && ["live", "stopping", "uploading"].includes(meeting.phase)) {
    return <MeetingLiveView />;
  }

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

      <DesktopPermissionsPanel />

      <VoiceRecorderWidget
        onComplete={(memoId) => navigate(ROUTES.MEMO_DETAIL(memoId))}
      />

      {recallBotEnabled && <RecallBotForm />}
    </div>
  );
};

export default RecordPage;
