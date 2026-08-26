import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { memoKeys } from "@/features/memos/api";
import { recordingKeys, recordingsApi } from "@/features/recordings/api";
import type { CrmCallRecording, RecordingStatusPill } from "@/features/recordings/types";
import { callDurationSeconds, formatCallDuration } from "@/lib/call-duration";
import { formatRecordedAt } from "@/lib/memo-dates";
import {
  getMemoStatusPill,
  getRecordingAction,
  recordingTimestamp,
  recordingsNeedPoll,
} from "@/lib/recordings";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const POLL_MS = 3000;

function statusPillClasses(variant: RecordingStatusPill["variant"]): string {
  switch (variant) {
    case "approved":
      return "bg-success/10 text-success";
    case "failed":
      return "bg-destructive/10 text-destructive";
    case "pending":
      return "bg-warning/10 text-warning";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function RecordingRow({
  recording,
  onAction,
  busyCallId,
}: {
  recording: CrmCallRecording;
  onAction: (recording: CrmCallRecording) => void;
  busyCallId: string | null;
}) {
  const action = getRecordingAction(recording);
  const pill = getMemoStatusPill(recording);
  const dateStr = formatRecordedAt(recordingTimestamp(recording));
  const durStr = formatCallDuration(callDurationSeconds(recording));
  const meta = [dateStr, durStr].filter(Boolean).join(" · ");
  const isBusy = busyCallId === recording.call_id;

  return (
    <div
      className={cn(
        THEME_TOKENS.cards.base,
        THEME_TOKENS.radius.card,
        V_PATTERNS.listItem,
        "flex items-center gap-6",
      )}
    >
      <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center flex-shrink-0">
        <Phone className="h-5 w-5 text-beige" />
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="font-normal text-foreground text-[15px] truncate">
          {recording.title || "Call"}
        </h3>
        {meta ? (
          <p className="text-sm text-muted-foreground mt-1">{meta}</p>
        ) : null}
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        {pill ? (
          pill.busy ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {pill.text}
            </span>
          ) : (
            <span
              className={cn(
                "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium",
                statusPillClasses(pill.variant),
              )}
            >
              {pill.text}
            </span>
          )
        ) : null}

        {action ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isBusy}
            onClick={() => onAction(recording)}
          >
            {isBusy ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                Starting…
              </>
            ) : (
              action.label
            )}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function RecordingsPanel() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [busyCallId, setBusyCallId] = useState<string | null>(null);

  const { data: connections = [], isLoading: connectionsLoading } = useIntegrations();
  const hasRecordingsCrm = connections.some(
    (c) => c.provider === "hubspot" && c.status === "connected",
  );

  const {
    data: recordings = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: recordingKeys.list(20),
    queryFn: () => recordingsApi.list(20),
    enabled: hasRecordingsCrm,
    refetchInterval: (query) =>
      recordingsNeedPoll(query.state.data ?? []) ? POLL_MS : false,
  });

  const visibleRecordings = useMemo(
    () => recordings.filter((r) => r.has_recording),
    [recordings],
  );

  const processMutation = useMutation({
    mutationFn: (callId: string) => recordingsApi.process(callId),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: recordingKeys.all });
      void queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      navigate(`/dashboard/memos/${result.memo_id}`);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Could not start transcription");
    },
    onSettled: () => {
      setBusyCallId(null);
    },
  });

  if (connectionsLoading || !hasRecordingsCrm) {
    return null;
  }

  const handleAction = (recording: CrmCallRecording) => {
    const action = getRecordingAction(recording);
    if (!action) return;

    if (action.action === "transcribe") {
      setBusyCallId(recording.call_id);
      processMutation.mutate(recording.call_id);
      return;
    }

    if (action.memoId) {
      navigate(`/dashboard/memos/${action.memoId}`);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className={THEME_TOKENS.typography.sectionTitle}>Recordings</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Call recordings from your CRM
        </p>
      </div>

      <div className="space-y-4">
        {isLoading ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center`}>
            <div className="w-6 h-6 border-2 border-beige border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            <p className={THEME_TOKENS.typography.capsLabel}>Loading recordings…</p>
          </div>
        ) : isError ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center space-y-3`}>
            <p className="text-muted-foreground">
              Could not load recordings. Your CRM connection may need attention.
            </p>
            <Link
              to="/dashboard/integrations"
              className={`${THEME_TOKENS.typography.capsLabel} text-beige hover:underline`}
            >
              Check integrations
            </Link>
            {error instanceof Error && error.message ? (
              <p className="text-xs text-muted-foreground">{error.message}</p>
            ) : null}
          </div>
        ) : visibleRecordings.length === 0 ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center`}>
            <p className="text-muted-foreground">No call recordings found yet.</p>
          </div>
        ) : (
          visibleRecordings.map((recording) => (
            <RecordingRow
              key={recording.call_id}
              recording={recording}
              onAction={handleAction}
              busyCallId={busyCallId}
            />
          ))
        )}
      </div>
    </div>
  );
}
