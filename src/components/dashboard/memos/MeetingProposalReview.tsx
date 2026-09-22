import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { meetingProposalView, renderMeetingProposal } from "@shared/ui/meeting-proposal.js";
import { renderToString } from "@shared/ui/html.js";
import { api } from "@/shared/lib/api-client";

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
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["meeting-proposal", memoId],
    queryFn: () => api.get<{ proposal: MeetingProposal | null }>(`/memos/${memoId}/meeting-proposal`),
    enabled: !extractionPending,
  });

  const mutation = useMutation({
    mutationFn: (payload: { decision: "accept" | "omit" | "corrected"; proposal_id: string; starts_at?: string }) =>
      api.post<AcceptResponse>(`/memos/${memoId}/meeting-proposal/accept`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(["meeting-proposal", memoId], { proposal: data.proposal });
    },
  });

  const proposal = mutation.data?.proposal ?? query.data?.proposal ?? null;
  const view = meetingProposalView(proposal, { surface: "review", extractionPending });

  const markup = useMemo(() => {
    if (!view.visible) return "";
    return renderToString(renderMeetingProposal(view));
  }, [view]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const action = (event.target as HTMLElement).closest("[data-action]")?.getAttribute("data-action");
      const proposalId = proposal?.proposal_id;
      if (!action || !proposalId || mutation.isPending) return;
      if (action === "accept") {
        mutation.mutate({ decision: "accept", proposal_id: String(proposalId) });
        return;
      }
      if (action === "omit") {
        mutation.mutate({ decision: "omit", proposal_id: String(proposalId) });
      }
    },
    [mutation, proposal?.proposal_id],
  );

  if (!view.visible) return null;
  return <div onClick={handleClick} dangerouslySetInnerHTML={{ __html: markup }} />;
}
