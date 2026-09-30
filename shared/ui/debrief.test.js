import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { renderToString } from './html.js';
import { debriefCopy, debriefNeedsPoll, debriefView, hasCoaching, renderDebrief } from './components/debrief.js';

const READY = {
  status: 'ready',
  flow: 'sdr',
  meeting_booked: false,
  progress: [0.6, null, 0.4],
  missed: [
    { id: 'meeting', kind: 'step', label: 'Reunión con día y hora' },
    { id: 'obj-1', kind: 'objection', label: 'price' },
  ],
  highlights: ['min 00:12 · ¿Tienes 30 segundos?'],
  coach: {
    kept: { step_id: 'opening', label: 'Apertura con permiso', quote: '¿Tienes 30 segundos?' },
    fix: {
      kind: 'step',
      id: 'meeting',
      label: 'Reunión con día y hora',
      criterion: 'Propone un día y una hora concretos.',
      say: '¿Te va bien el jueves a las 10?',
      focus: true,
    },
    adherence: 0.5,
  },
};

const render = (brief, lang = 'es') => renderToString(renderDebrief(brief, lang));

describe('debrief', () => {
  it('shows the tab only for a measured call with something kept or to fix', () => {
    assert.equal(hasCoaching(READY), true);
    assert.equal(hasCoaching({ ...READY, status: 'skipped' }), false);
    assert.equal(hasCoaching({ ...READY, coach: { kept: null, fix: null } }), false);
    assert.equal(hasCoaching({ status: 'ready' }), false);
    assert.equal(hasCoaching(null), false);
  });

  it('keeps polling while the server is still writing it', () => {
    assert.equal(debriefNeedsPoll(null), true);
    assert.equal(debriefNeedsPoll({ status: 'pending' }), true);
    assert.equal(debriefNeedsPoll({ status: 'partial', waiting: true }), true);
    assert.equal(debriefNeedsPoll(READY), false);
  });

  it('lays out one kept, one next time with the playbook phrase, the focus and the outcome', () => {
    const out = render(READY);
    assert.match(out, /Bien hecho/);
    assert.match(out, /Apertura con permiso <q>¿Tienes 30 segundos\?<\/q>/);
    assert.match(out, /La próxima vez<span class="v-debrief__focus">Foco de la semana<\/span>/);
    assert.match(out, /Prueba con <q>¿Te va bien el jueves a las 10\?<\/q>/);
    assert.match(out, /Reunión agendada · No/);
    // No score number anywhere: the card teaches the step, not the mark.
    assert.doesNotMatch(out, /\/10/);
  });

  it('ends the trend with this call, oldest first, with the percentage on hover', () => {
    const view = debriefView(READY, 'es');
    assert.deepEqual(view.bars, [
      { value: 0.4, current: false },
      { value: null, current: false },
      { value: 0.6, current: false },
      { value: 0.5, current: true },
    ]);
    assert.match(render(READY), /title="50 %"/);
  });

  it('names objections in words, never the raw category', () => {
    const brief = {
      ...READY,
      coach: { kept: null, fix: { kind: 'objection', label: 'status_quo', category: 'status_quo', say: 'Lo entiendo.' } },
    };
    const out = render(brief, 'en');
    assert.match(out, /Happy with how they do it/);
    assert.doesNotMatch(out, /status_quo/);
    assert.match(render(READY, 'en'), /<li>Price<\/li>/);
  });

  it('puts what was missed and the moments behind Details', () => {
    const out = render(READY);
    assert.match(out, /<details class="v-debrief__detail">\s*<summary>Detalle<\/summary>/);
    assert.match(out, /min 00:12 · ¿Tienes 30 segundos\?/);
  });

  it('designs every other state and never prints nothing-but-undefined', () => {
    assert.equal(render({ status: 'skipped', reason: 'no_conversation' }), '');
    assert.equal(render({ status: 'failed' }), '');
    assert.match(render({ status: 'pending' }), /Preparando tu feedback…/);
    assert.match(render({ status: 'unavailable', reason: 'missing_playbook' }), /Sin playbook para este tipo de llamada/);
    assert.match(render({ status: 'ready', coach: null }), /Sin datos suficientes/);
    const bare = render({ status: 'ready', coach: { kept: { label: 'Apertura', quote: null }, fix: null } });
    assert.doesNotMatch(bare, /undefined|null|<q>/);
    assert.doesNotMatch(bare, /v-debrief__trend|<details/);
  });

  it('gives hosts that lay it out themselves the same words, in both languages', () => {
    for (const lang of ['es', 'en']) {
      const copy = debriefCopy(lang);
      for (const [key, value] of Object.entries(copy)) assert.ok(typeof value === 'string' && value, `${lang}.${key}`);
    }
    assert.equal(debriefCopy('en').debriefFix, 'Next time');
  });

  it('escapes what came from the call', () => {
    const out = render({ ...READY, coach: { ...READY.coach, kept: { label: 'Apertura', quote: '<img src=x>' } } });
    assert.match(out, /&lt;img src=x&gt;/);
  });
});
