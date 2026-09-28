import { briefRows } from '../shared/ui/brief.js';

/** Paints the contact brief box. Returns true when the box shows something. */
export function paintBriefBox({ box, screen, brief, flatLines, captureActive, doc = document }) {
  box.replaceChildren();
  // Only BRIEF_V2_ENABLED answers carry `label`; F03 answers keep the flat lines they always had.
  const isV2 = Boolean(brief) && Object.prototype.hasOwnProperty.call(brief, 'label');
  const view = isV2 && !captureActive ? briefRows(brief) : null;
  if (view && (view.rows.length || view.label || view.notice)) {
    for (const row of view.rows) {
      const line = doc.createElement('p');
      line.textContent = row.text;
      if (row.playbook) line.classList.add('brief-playbook');
      if (row.company) line.classList.add('brief-company');
      box.appendChild(line);
    }
    if (view.label) {
      const chip = doc.createElement('span');
      chip.className = 'v-chip';
      chip.textContent = view.label;
      box.appendChild(chip);
    }
    if (view.notice) {
      const notice = doc.createElement('p');
      notice.textContent = view.notice;
      box.prepend(notice);
    }
  } else {
    for (const line of flatLines) {
      const row = doc.createElement('p');
      row.textContent = line;
      box.appendChild(row);
    }
  }
  box.hidden = box.childElementCount === 0;
  screen?.classList.toggle('has-brief', !box.hidden && !captureActive);
  return !box.hidden;
}
