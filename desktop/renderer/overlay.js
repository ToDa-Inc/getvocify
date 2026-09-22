import { overlayAssist } from './shared/ui/copilot/suggestion-state.js';

const lineEl = document.getElementById('overlay-line');
const labelEl = document.getElementById('overlay-label');

function desktop() {
  return window.vocifyDesktop;
}

desktop()?.shell?.onOverlayState((state) => {
  const assist = overlayAssist(state);
  if (assist) {
    lineEl.textContent = assist;
    labelEl.textContent = 'Ayuda';
    return;
  }
  if (state?.lastLine) lineEl.textContent = state.lastLine;
  labelEl.textContent = state?.listening ? 'Live' : 'Idle';
});

document.getElementById('overlay-stop').addEventListener('click', () => {
  desktop()?.shell?.command('stop');
});

document.querySelector('.overlay-pill')?.addEventListener('dblclick', () => {
  desktop()?.shell?.command('show');
});
