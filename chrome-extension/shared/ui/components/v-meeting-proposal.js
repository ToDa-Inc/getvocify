import { VElement, define } from "../v-element.js";
import { meetingProposalView, renderMeetingProposal } from "../meeting-proposal.js";

class VMeetingProposal extends VElement {
  static render(proposal, element) {
    const surface = element?.surface || "review";
    return renderMeetingProposal(meetingProposalView(proposal, { surface, extractionPending: Boolean(element?.extractionPending) }));
  }
}

define("v-meeting-proposal", VMeetingProposal);
