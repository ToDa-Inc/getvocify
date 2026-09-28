import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { Button } from "@/components/ui/button";
import { AuthorFilter } from "@/components/dashboard/AuthorFilter";
import { AuthorLabel } from "@/components/dashboard/AuthorLabel";
import { useAuth } from "@/features/auth";
import { companyApi, companyKeys } from "@/features/company/api";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { memosApi, memoKeys } from "@/features/memos/api";
import type { Memo } from "@/features/memos/types";
import { recordingKeys, recordingsApi } from "@/features/recordings/api";
import type { CrmCallRecording, RecordingStatusPill } from "@/features/recordings/types";
import {
  authorChipLabel,
  authorDisplayName,
  canViewCompanyActivity,
  defaultActivityAuthorId,
} from "@/lib/activity-authors";
import {
  ACTIVITY_PAGE_SIZE,
  activityEmptyMessage,
  mergeActivityItems,
  nextVisibleCount,
  shouldPeekNextActivity,
  type ActivityItem,
} from "@/lib/activity-feed";
import { callDurationSeconds, formatCallDuration } from "@/lib/call-duration";
import { memoListTitle, recordingListTitle } from "@/lib/copilot-note";
import { formatRecordedAt } from "@/lib/memo-dates";
import {
  getMemoStatusPill,
  getRecordingAction,
  recordingTimestamp,
  recordingsNeedPoll,
} from "@/lib/recordings";
import { formatCallerIdDisplay } from "@/lib/dial-target";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
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

function StatusPill({ pill }: { pill: RecordingStatusPill }) {
  if (pill.busy) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <VocifySpinner size={12} />
        {pill.text}
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium",
        statusPillClasses(pill.variant),
      )}
    >
      {pill.text}
    </span>
  );
}

function ActivityRow({
  item,
  peek,
  currentUserId,
  showAuthors,
  busyCallId,
  onRecordingAction,
  linkedMemo,
}: {
  item: ActivityItem;
  peek?: boolean;
  currentUserId?: string | null;
  showAuthors: boolean;
  busyCallId: string | null;
  onRecordingAction: (recording: CrmCallRecording) => void;
  linkedMemo?: Memo | null;
}) {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const isRecording = item.kind === "recording";
  const recording = isRecording ? item.recording : null;
  const memo = isRecording ? null : item.memo;
  const action = recording ? getRecordingAction(recording) : null;
  const pill = recording
    ? getMemoStatusPill(recording)
    : memo
      ? getMemoStatusPill(
          {
            call_id: memo.id,
            title: "",
            has_recording: true,
            memo_id: memo.id,
            memo_status: memo.status,
          },
          memo.screeningOutcome,
        )
      : null;
  const author = isRecording
    ? authorChipLabel(recording?.author_name, recording?.author_user_id, currentUserId)
    : authorChipLabel(memo?.authorName, memo?.userId, currentUserId);
  const title = isRecording
    ? recordingListTitle(recording!, linkedMemo, formatCallerIdDisplay)
    : memoListTitle(memo);
  const dateStr = isRecording
    ? formatRecordedAt(recordingTimestamp(recording!))
    : formatRecordedAt(memo?.createdAt);
  const durStr = isRecording ? formatCallDuration(callDurationSeconds(recording)) : "";
  const meta = [dateStr, durStr].filter(Boolean).join(" · ");
  const isBusy = Boolean(recording && busyCallId === recording.call_id);
  const canOpenMemo = Boolean(memo) || action?.action === "continue" || action?.action === "view";
  const interactive = !peek && canOpenMemo;

  const open = () => {
    if (peek) return;
    if (memo) {
      navigate(`/dashboard/memos/${memo.id}`);
      return;
    }
    if (!recording || !action) return;
    if (action.action === "transcribe") return;
    if (action.memoId) navigate(`/dashboard/memos/${action.memoId}`);
  };

  return (
    <div
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-hidden={peek || undefined}
      onClick={interactive ? open : undefined}
      onKeyDown={
        interactive
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                open();
              }
            }
          : undefined
      }
      className={cn(
        "relative flex items-center justify-between gap-3 border-b border-border/40 py-2.5 last:border-b-0",
        interactive &&
          "cursor-pointer hover:rounded-lg hover:border-transparent hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        peek && "max-h-9 overflow-hidden pointer-events-none border-b-0",
      )}
    >
      <div className="min-w-0 flex flex-col gap-0.5">
        <span className="text-[11px] text-muted-foreground">
          {isRecording ? t.product.activityKindRecording : t.product.activityKindMemo}
        </span>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[13px] text-foreground truncate">{title}</span>
          {showAuthors ? (
            <AuthorLabel name={author} className="px-1.5 py-0 text-[11px]" />
          ) : null}
        </div>
        {meta ? <span className="text-[12px] text-muted-foreground truncate">{meta}</span> : null}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {pill ? <StatusPill pill={pill} /> : null}
        {action && !peek && action.action === "transcribe" ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isBusy}
            className="h-8 px-3 text-xs"
            onClick={(event) => {
              event.stopPropagation();
              onRecordingAction(recording!);
            }}
          >
            {isBusy ? (
              <>
                <VocifySpinner size={12} />
                Starting…
              </>
            ) : (
              action.label
            )}
          </Button>
        ) : null}
      </div>
      {peek ? (
        <span
          aria-hidden
          className="absolute inset-0 bg-gradient-to-b from-background/20 to-background"
        />
      ) : null}
    </div>
  );
}

export function ActivityPanel() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [busyCallId, setBusyCallId] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(ACTIVITY_PAGE_SIZE);
  const [authorOverride, setAuthorOverride] = useState<string | null | undefined>(undefined);

  const canViewCompany = canViewCompanyActivity(user?.company?.role);
  const { data: membersData } = useQuery({
    queryKey: companyKeys.members(),
    queryFn: companyApi.listMembers,
    enabled: canViewCompany,
  });
  const authors = (membersData?.members ?? [])
    .filter((member) => member.status === "active")
    .map((member) => ({
      userId: member.userId,
      label: authorDisplayName(member.fullName, member.email),
      email: member.email,
    }));
  const authorUserId =
    authorOverride !== undefined
      ? authorOverride
      : defaultActivityAuthorId(canViewCompany, user?.id, authors.length);
  const viewingTeammate = Boolean(authorUserId && authorUserId !== user?.id);

  useEffect(() => {
    setVisibleCount(ACTIVITY_PAGE_SIZE);
  }, [authorUserId]);

  const { data: connections = [], isLoading: connectionsLoading } = useIntegrations();
  const hasRecordingsCrm = connections.some(
    (c) => c.provider === "hubspot" && c.status === "connected",
  );

  const {
    data: recordings = [],
    isLoading: recordingsLoading,
    isError,
    error,
  } = useQuery({
    queryKey: recordingKeys.list(20, authorUserId),
    queryFn: () => recordingsApi.list(20, authorUserId),
    enabled: hasRecordingsCrm,
    refetchInterval: (query) =>
      recordingsNeedPoll(query.state.data ?? []) ? POLL_MS : false,
  });

  const memoFilters = {
    limit: 20,
    scope: canViewCompany ? ("company" as const) : ("me" as const),
    authorUserId: authorUserId ?? undefined,
  };
  const { data: memos = [], isLoading: memosLoading } = useQuery({
    queryKey: memoKeys.list(memoFilters),
    queryFn: () => memosApi.list(memoFilters),
  });

  const items = useMemo(
    () => mergeActivityItems({ recordings, memos: memos as Memo[] }),
    [recordings, memos],
  );
  const memosById = useMemo(() => {
    const map = new Map<string, Memo>();
    for (const memo of memos) map.set(memo.id, memo);
    return map;
  }, [memos]);
  const shown = items.slice(0, visibleCount);
  const peek = shouldPeekNextActivity(visibleCount, items.length)
    ? items[visibleCount]
    : null;

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

  const handleRecordingAction = (recording: CrmCallRecording) => {
    const action = getRecordingAction(recording);
    if (!action) return;
    if (action.action === "transcribe") {
      setBusyCallId(recording.call_id);
      processMutation.mutate(recording.call_id);
      return;
    }
    if (action.memoId) navigate(`/dashboard/memos/${action.memoId}`);
  };

  const waiting =
    items.length === 0 &&
    (memosLoading || connectionsLoading || (hasRecordingsCrm && recordingsLoading));

  return (
    <section className="space-y-3" aria-labelledby="activity-heading">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 id="activity-heading" className={THEME_TOKENS.typography.sectionTitle}>
          {t.product.recentTitle}
        </h2>
        <div className="flex items-center gap-3">
          <AuthorFilter
            authors={authors}
            value={authorUserId}
            onChange={setAuthorOverride}
            currentUserId={user?.id}
            canViewCompany={canViewCompany}
            compact
          />
          <Link
            to="/dashboard/memos"
            className={`${THEME_TOKENS.typography.capsLabel} text-beige hover:underline`}
          >
            {t.product.activityViewAll}
          </Link>
        </div>
      </div>

      {isError && hasRecordingsCrm ? (
        <p className="text-sm text-muted-foreground">
          {t.product.activityRecordingsFailed}{" "}
          <Link to="/dashboard/settings" className="text-beige hover:underline">
            {t.product.activityCheckCrm}
          </Link>
          {error instanceof Error && error.message ? (
            <span className="block text-xs mt-1">{error.message}</span>
          ) : null}
        </p>
      ) : null}

      {waiting ? (
        <VocifyLoader size="sm" label={t.product.activityLoading} className="py-6" />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground pt-1">
          {activityEmptyMessage({
            viewingTeammate,
            mine: Boolean(authorUserId && authorUserId === user?.id),
            canViewCompany,
          })}
        </p>
      ) : (
        <>
          <div className={cn(peek && "relative")}>
            {shown.map((item) => (
              <ActivityRow
                key={`${item.kind}-${item.id}`}
                item={item}
                currentUserId={user?.id}
                showAuthors={canViewCompany}
                busyCallId={busyCallId}
                onRecordingAction={handleRecordingAction}
                linkedMemo={
                  item.kind === "recording"
                    ? memosById.get(item.recording.memo_id || "")
                    : null
                }
              />
            ))}
            {peek ? (
              <ActivityRow
                item={peek}
                peek
                currentUserId={user?.id}
                showAuthors={canViewCompany}
                busyCallId={null}
                onRecordingAction={handleRecordingAction}
                linkedMemo={
                  peek.kind === "recording"
                    ? memosById.get(peek.recording.memo_id || "")
                    : null
                }
              />
            ) : null}
          </div>
          {items.length > visibleCount ? (
            <button
              type="button"
              onClick={() => setVisibleCount((count) => nextVisibleCount(count, items.length))}
              className="mt-1 flex h-8 w-full items-center justify-center rounded-full border border-border/40 bg-card text-[12px] text-beige transition-colors duration-150 hover:border-beige/40 hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              See more
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}
