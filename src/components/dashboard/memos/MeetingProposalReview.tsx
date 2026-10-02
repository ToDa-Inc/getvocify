import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { CalendarClock } from "lucide-react";
import { meetingProposalView, type MeetingProposalView } from "@shared/ui/meeting-proposal.js";
import { Button } from "@/components/ui/button";
import { api } from "@/shared/lib/api-client";
import { useLanguage } from "@/lib/i18n";
import {
  meetingProposalReadErrorView,
  meetingProposalReviewSurface,
  meetingWhen,
} from "@/lib/meeting-proposal-review";

type MeetingProposal = Record<string, unknown> & {
  proposal_id?: string;
};

type AcceptResponse = {
  proposal: MeetingProposal | null;
  crm_status: string;
  remote_id?: string | null;
  replayed?: boolean;
};

export function MeetingProposalReview({
  memoId,
  extractionPending = false,
}: {
  memoId: string;
  extractionPending?: boolean;
}) {
  const { t, language } = useLanguage();
  const uiLang = language === "EN" ? "en" : "es";
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["meeting-proposal", memoId],
    queryFn: () => api.get<{ proposal: MeetingProposal | null }>(`/memos/${memoId}/meeting-proposal`),
    enabled: !extractionPending,
  });

  const applyProposal = useCallback(
    (data: AcceptResponse) => {
      queryClient.setQueryData(["meeting-proposal", memoId], { proposal: data.proposal });
    },
    [memoId, queryClient],
  );

  const mutation = useMutation({
    mutationFn: (payload: { decision: "accept" | "omit" | "corrected"; proposal_id: string; starts_at?: string }) =>
      api.post<AcceptResponse>(`/memos/${memoId}/meeting-proposal/accept`, payload),
    onSuccess: applyProposal,
  });

  const reconcileMutation = useMutation({
    mutationFn: (proposal_id: string) =>
      api.post<AcceptResponse>(`/memos/${memoId}/meeting-proposal/reconcile`, { proposal_id }),
    onSuccess: applyProposal,
  });

  const proposal =
    reconcileMutation.data?.proposal ?? mutation.data?.proposal ?? query.data?.proposal ?? null;
  const surface = meetingProposalReviewSurface({
    extractionPending,
    queryFetchStatus: query.fetchStatus,
    queryIsPending: query.isPending,
    queryIsError: query.isError,
    proposal,
  });
  const reviewPhrases = meetingProposalView(null, {
    surface: "review",
    extractionPending: true,
    lang: uiLang,
  }).phrases;
  const view: MeetingProposalView =
    surface.kind === "pending"
      ? meetingProposalView(null, { surface: "review", extractionPending: true, lang: uiLang })
      : surface.kind === "read-error"
        ? meetingProposalReadErrorView(t.product.meetingReadFailed, reviewPhrases)
        : surface.kind === "hidden"
          ? { visible: false as const }
          : meetingProposalView(proposal, { surface: "review", extractionPending: false, lang: uiLang });

  const busy = mutation.isPending || reconcileMutation.isPending;
  const act = useCallback(
    (action: "accept" | "omit" | "reconcile") => {
      const proposalId = proposal?.proposal_id;
      if (!proposalId || busy) return;
      if (action === "reconcile") reconcileMutation.mutate(String(proposalId));
      else mutation.mutate({ decision: action, proposal_id: String(proposalId) });
    },
    [busy, mutation, reconcileMutation, proposal?.proposal_id],
  );

  if (!view.visible) return null;
  const phrases = view.phrases;
  const when = meetingWhen(view.startsAt, view.timezone, t.product.hourLocale);
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/50 bg-card px-3.5 py-3 shadow-xs">
      <CalendarClock aria-hidden="true" strokeWidth={1.5} className="mt-0.5 h-4 w-4 shrink-0 text-beige" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-[11.5px] font-medium text-muted-foreground" role={surface.kind === "pending" ? "status" : undefined}>
          {view.title}
        </p>
        {when ? <p className="text-[13px] leading-relaxed text-foreground first-letter:uppercase">{when}</p> : null}
      </div>
      {phrases && (view.save || view.omit || view.reconcile) ? (
        <div className="flex shrink-0 items-center gap-1">
          {view.omit ? (
            <Button type="button" variant="quiet" size="text" disabled={busy} onClick={() => act("omit")}>
              {phrases.omit}
            </Button>
          ) : null}
          {view.reconcile ? (
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => act("reconcile")}>
              {phrases.reconcile}
            </Button>
          ) : null}
          {view.save ? (
            <Button type="button" size="sm" disabled={busy} onClick={() => act("accept")}>
              {phrases.save}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
