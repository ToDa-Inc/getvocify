import { useQuery } from "@tanstack/react-query";
import { meetingProposalView, renderMeetingProposal } from "@shared/ui/meeting-proposal.js";
import { renderToString } from "@shared/ui/html.js";
import { api } from "@/shared/lib/api-client";

export function MeetingProposalReview({
  memoId,
  extractionPending = false,
}: {
  memoId: string;
  extractionPending?: boolean;
}) {
  const query = useQuery({
    queryKey: ["meeting-proposal", memoId],
    queryFn: () => api.get<{ proposal: Record<string, unknown> | null }>(`/memos/${memoId}/meeting-proposal`),
    enabled: !extractionPending,
  });
  const view = meetingProposalView(query.data?.proposal ?? null, { surface: "review", extractionPending });
  if (!view.visible) return null;
  return <div dangerouslySetInnerHTML={{ __html: renderToString(renderMeetingProposal(view)) }} />;
}
