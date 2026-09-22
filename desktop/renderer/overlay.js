import { overlayChecklistMarkup } from './shared/ui/copilot/checklist.js';
import { overlayAssist } from './shared/ui/copilot/suggestion-state.js';
import { renderToString } from './shared/ui/html.js';

const lineEl = document.getElementById('overlay-line');
const labelEl = document.getElementById('overlay-label');
const checklistEl = document.getElementById('overlay-checklist');

function desktop() {
  return window.vocifyDesktop;
}

function paintChecklist(state) {
  if (!checklistEl) return;
  const markup = overlayChecklistMarkup(state?.checklist, { kind: state?.kind });
  if (!markup) {
    checklistEl.hidden = true;
    checklistEl.innerHTML = '';
    return;
  }
  checklistEl.hidden = false;
  checklistEl.innerHTML = renderToString(markup);
}

desktop()?.shell?.onOverlayState((state) => {
  const assist = overlayAssist(state);
  if (assist) {
    lineEl.textContent = assist;
    labelEl.textContent = 'Ayuda';
    paintChecklist(state);
    return;
  }
  if (state?.lastLine) lineEl.textContent = state.lastLine;
  labelEl.textContent = state?.listening ? 'Live' : 'Idle';
  paintChecklist(state);
});

document.getElementById('overlay-stop').addEventListener('click', () => {
  desktop()?.shell?.command('stop');
});

document.querySelector('.overlay-pill')?.addEventListener('dblclick', () => {
  desktop()?.shell?.command('show');
});
