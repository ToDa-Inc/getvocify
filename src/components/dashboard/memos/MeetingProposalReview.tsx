import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { meetingProposalView, renderMeetingProposal } from "@shared/ui/meeting-proposal.js";
import { renderToString } from "@shared/ui/html.js";
import { api } from "@/shared/lib/api-client";
import { useLanguage } from "@/lib/i18n";
import {
  meetingProposalReadErrorView,
  meetingProposalReviewSurface,
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
  const view =
    surface.kind === "pending"
      ? meetingProposalView(null, { surface: "review", extractionPending: true, lang: uiLang })
      : surface.kind === "read-error"
        ? meetingProposalReadErrorView(t.product.meetingReadFailed, reviewPhrases)
        : surface.kind === "hidden"
          ? { visible: false as const }
          : meetingProposalView(proposal, { surface: "review", extractionPending: false, lang: uiLang });

  const markup = useMemo(() => {
    if (!view.visible) return "";
    return renderToString(renderMeetingProposal(view));
  }, [view]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const action = (event.target as HTMLElement).closest("[data-action]")?.getAttribute("data-action");
      const proposalId = proposal?.proposal_id;
      if (!action || !proposalId || mutation.isPending || reconcileMutation.isPending) return;
      if (action === "accept") {
        mutation.mutate({ decision: "accept", proposal_id: String(proposalId) });
        return;
      }
      if (action === "omit") {
        mutation.mutate({ decision: "omit", proposal_id: String(proposalId) });
        return;
      }
      if (action === "reconcile") {
        reconcileMutation.mutate(String(proposalId));
      }
    },
    [mutation, reconcileMutation, proposal?.proposal_id],
  );

  if (!view.visible) return null;
  return <div onClick={handleClick} dangerouslySetInnerHTML={{ __html: markup }} />;
}
