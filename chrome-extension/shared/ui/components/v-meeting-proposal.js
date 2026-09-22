import { VElement, define } from "../v-element.js";
import { meetingProposalView, renderMeetingProposal } from "../meeting-proposal.js";

class VMeetingProposal extends VElement {
  static render(proposal, element) {
    const surface = element?.surface || "review";
    const lang = element.lang || document.documentElement.lang;
    return renderMeetingProposal(
      meetingProposalView(proposal, { surface, extractionPending: Boolean(element?.extractionPending), lang }),
    );
  }
}

define("v-meeting-proposal", VMeetingProposal);
