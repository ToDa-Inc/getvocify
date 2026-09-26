import { briefRows } from '../shared/ui/brief.js';

/** Paints the contact brief box. Returns true when the box shows something. */
export function paintBriefBox({ box, screen, brief, flatLines, captureActive, doc = document }) {
  box.replaceChildren();
  if (brief && !captureActive) {
    const view = briefRows(brief);
    for (const row of view.rows) {
      const line = doc.createElement('p');
      line.textContent = row.text;
      if (row.playbook) line.classList.add('brief-playbook');
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
