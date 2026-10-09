import { overlayChecklistMarkup } from './shared/ui/copilot/checklist.js';
import { initialPillState, pillDecision } from './shared/ui/copilot/pill.js';
import { applyDataI18n, strings, uiLangInput } from './shared/ui/i18n.js';
import { renderToString } from './shared/ui/html.js';
import { speakerRoleFromLastLine } from '../lib/transcript-turns.js';

const lineEl = document.getElementById('overlay-line');
const checklistEl = document.getElementById('overlay-checklist');
const checklistDetailEl = document.getElementById('overlay-checklist-detail');
const assistBtn = document.getElementById('overlay-assist');
const stopBtn = document.getElementById('overlay-stop');

function uiLang() {
  return uiLangInput(localStorage.getItem('vocify_lang'), navigator.language);
}

applyDataI18n(document, uiLang());
stopBtn?.setAttribute('aria-label', strings(uiLang()).overlayStop);

let pillState = initialPillState();
let tickTimer = null;

function desktop() {
  return window.vocifyDesktop;
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
  const t = strings(uiLang());
  const markup = overlayChecklistMarkup(state?.checklist, {
    kind: state?.kind,
    doneLabel: t.checklistDone,
    progressLabel: t.checklistProgress,
  });
  if (!markup) {
    if (checklistEl) {
      checklistEl.hidden = true;
      checklistEl.textContent = '';
    }
    if (checklistDetailEl) {
      checklistDetailEl.hidden = true;
      checklistDetailEl.innerHTML = '';
    }
    return;
  }

  const checklist = state?.checklist;
  const applicable = Number(checklist?.applicable);
  const observedRaw = Number(checklist?.observed);
  const observed = Number.isFinite(observedRaw) ? observedRaw : 0;

  if (checklistEl) {
    checklistEl.hidden = false;
    checklistEl.textContent = t.checklistProgress(observed, applicable);
  }

  if (checklistDetailEl) {
    const full = renderToString(markup);
    checklistDetailEl.innerHTML = full;
    checklistDetailEl.querySelector('.overlay-checklist-summary')?.remove();
    const hasSteps = checklistDetailEl.querySelector('.overlay-checklist-step');
    checklistDetailEl.hidden = !hasSteps;
  }
}

function paintAssistButton(assistEnabled) {
  if (!assistBtn) return;
  const t = strings(uiLang());
  const on = assistEnabled === true;
  assistBtn.textContent = on ? t.helpOff : t.helpOn;
  assistBtn.hidden = !lastOverlayState?.listening;
}

function paintOverlay(state) {
  lastOverlayState = state;
  const t = strings(uiLang());
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
    return;
  }

  if (state?.lastLine) lineEl.textContent = state.lastLine;
  else lineEl.textContent = t.overlayListening;
}

desktop()?.shell?.onOverlayState((state) => {
  paintOverlay(state);
});

stopBtn?.addEventListener('click', () => {
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
