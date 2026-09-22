import { meetingProposalView, renderMeetingProposal } from "@shared/ui/meeting-proposal.js";
import { renderToString } from "@shared/ui/html.js";

export function MeetingProposalReview({
  proposal,
  extractionPending = false,
}: {
  proposal: Record<string, unknown> | null;
  extractionPending?: boolean;
}) {
  const view = meetingProposalView(proposal, { surface: "review", extractionPending });
  if (!view.visible) return null;
  return <div dangerouslySetInnerHTML={{ __html: renderToString(renderMeetingProposal(view)) }} />;
}
