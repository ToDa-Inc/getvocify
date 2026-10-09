import { VElement, define } from '../v-element.js';
import { debriefNeedsRepaint, renderDebrief } from './debrief.js';

/** `.data` = the GET /memos/{id}/brief body as-is. Renders nothing when there is nothing to read. */
class VDebrief extends VElement {
  static render(brief, element) {
    return renderDebrief(brief, element.lang || document.documentElement.lang);
  }

  // A poll that returns the same brief must not close the rep's open "Details".
  shouldRepaint(prev, next) {
    return debriefNeedsRepaint(prev, next);
  }
}

define('v-debrief', VDebrief);
