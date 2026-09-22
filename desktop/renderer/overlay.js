import { overlayChecklistMarkup } from './shared/ui/copilot/checklist.js';
import { initialPillState, pillDecision } from './shared/ui/copilot/pill.js';
import { renderToString } from './shared/ui/html.js';

const lineEl = document.getElementById('overlay-line');
const labelEl = document.getElementById('overlay-label');
const checklistEl = document.getElementById('overlay-checklist');
const assistBtn = document.getElementById('overlay-assist');

let pillState = initialPillState();
let tickTimer = null;

function desktop() {
  return window.vocifyDesktop;
}

function speakerRoleFromLastLine(lastLine) {
  const line = String(lastLine ?? '').trim();
  if (line.startsWith('You:')) return 'rep';
  if (line.startsWith('Them:')) return 'prospect';
  return null;
}

function resetPillState() {
  pillState = initialPillState();
  if (tickTimer) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}

function ensurePillTick(active) {
  if (!active) {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
    return;
  }
  if (tickTimer) return;
  tickTimer = setInterval(() => {
    if (lastOverlayState) paintOverlay(lastOverlayState);
  }, 1000);
}

let lastOverlayState = null;

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

function paintAssistButton(assistEnabled) {
  if (!assistBtn) return;
  const on = assistEnabled === true;
  assistBtn.textContent = on ? 'Ocultar ayuda' : 'Ayuda';
  assistBtn.hidden = !lastOverlayState?.listening;
}

function paintOverlay(state) {
  lastOverlayState = state;
  if (!state?.listening) {
    resetPillState();
  }

  paintChecklist(state);
  paintAssistButton(state?.assistEnabled);

  const decision = pillDecision(
    pillState,
    {
      kind: state?.kind,
      enabled: state?.assistEnabled,
      speakerRole: speakerRoleFromLastLine(state?.lastLine),
      text: state?.card?.text ?? '',
      category: state?.card?.category,
      meetingId: state?.meetingId ?? null,
    },
    Date.now(),
  );
  pillState = decision.state;

  ensurePillTick(Boolean(state?.listening && state?.assistEnabled === true));

  if (state?.assistEnabled === true && decision.show && decision.text) {
    lineEl.textContent = decision.text;
    labelEl.textContent = 'Ayuda';
    return;
  }

  if (state?.lastLine) lineEl.textContent = state.lastLine;
  labelEl.textContent = state?.listening ? 'Live' : 'Idle';
}

desktop()?.shell?.onOverlayState((state) => {
  paintOverlay(state);
});

document.getElementById('overlay-stop').addEventListener('click', () => {
  resetPillState();
  desktop()?.shell?.command('stop');
});

assistBtn?.addEventListener('click', () => {
  const on = lastOverlayState?.assistEnabled === true;
  desktop()?.shell?.command(on ? 'assist-off' : 'assist-on');
});

document.querySelector('.overlay-pill')?.addEventListener('dblclick', () => {
  desktop()?.shell?.command('show');
});
