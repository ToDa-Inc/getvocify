import { html } from '../html.js';
import { strings } from '../i18n.js';

/**
 * The coaching after a call, one model for dashboard, extension and desktop: one thing
 * done well, one thing to do next time with the playbook's own phrase, and the trend.
 * The server decides what to say (`coach` in GET /memos/{id}/brief); this only lays it out.
 *
 * @typedef {Object} BriefBody   GET /api/v1/memos/{id}/brief
 * @property {'pending'|'partial'|'ready'|'skipped'|'unavailable'|'failed'} status
 * @property {string|null} [reason]
 * @property {boolean} [waiting]
 * @property {{ kept?: {label:string, quote?:string|null}|null, fix?: {kind:string, label:string, category?:string, criterion?:string|null, say?:string|null, focus?:boolean}|null, adherence?: number|null }|null} [coach]
 * @property {(number|null)[]} [progress]   previous calls of this type, most recent first
 * @property {'sdr'|'ae'|null} [flow]
 * @property {boolean|null} [meeting_booked]
 * @property {boolean|null} [next_step_agreed]
 * @property {{id:string, kind:string|null, label:string|null}[]} [missed]
 * @property {string[]} [highlights]
 */

const TREND_MAX = 5;
const MEASURED = new Set(['ready', 'partial']);

/** Whether this call has coaching to read: the rule every surface uses to show the tab. */
export function hasCoaching(brief) {
  const coach = brief?.coach;
  return Boolean(MEASURED.has(brief?.status) && coach && (coach.kept || coach.fix));
}

/** Keep asking while the server is still writing it. */
export function debriefNeedsPoll(brief) {
  return !brief || brief.status === 'pending' || brief.waiting === true;
}

const COPY_KEYS = [
  'debriefPreparing', 'debriefNoPlaybook', 'debriefEmpty', 'debriefKept', 'debriefFix', 'debriefFocus',
  'debriefTry', 'debriefTrend', 'debriefYes', 'debriefNo', 'debriefDetail', 'debriefMissed', 'debriefMoments',
];

/** The card's own words, for hosts that lay it out themselves (the React dashboard). */
export function debriefCopy(lang) {
  const t = strings(lang);
  return Object.fromEntries(COPY_KEYS.map((key) => [key, t[key]]));
}

function objectionLabel(category, t) {
  return t.debriefObjections[category] ?? t.debriefObjections.other;
}

/**
 * Pure: brief in, what to show out.
 * state: 'hidden' (nothing for this surface), 'pending', 'no_playbook', 'empty', 'ready'.
 */
export function debriefView(brief, lang) {
  const t = strings(lang);
  const status = brief?.status;
  if (!brief || status === 'skipped' || status === 'failed') return { state: 'hidden' };
  if (debriefNeedsPoll(brief)) return { state: 'pending' };
  if (status === 'unavailable') {
    return { state: brief.reason === 'missing_playbook' ? 'no_playbook' : 'hidden' };
  }
  const coach = brief.coach ?? null;
  if (!hasCoaching(brief)) return { state: 'empty' };

  const kept = coach.kept?.label ? { label: coach.kept.label, quote: coach.kept.quote || null } : null;
  const rawFix = coach.fix;
  const fix = rawFix?.label
    ? {
        label: rawFix.kind === 'objection' ? objectionLabel(rawFix.category ?? rawFix.label, t) : rawFix.label,
        criterion: rawFix.criterion || null,
        say: rawFix.say || null,
        focus: rawFix.focus === true,
      }
    : null;

  const previous = (brief.progress ?? []).slice(0, TREND_MAX).reverse();
  const current = typeof coach.adherence === 'number' ? coach.adherence : null;
  const bars = [
    ...previous.map((value) => ({ value: typeof value === 'number' ? value : null, current: false })),
    ...(current != null ? [{ value: current, current: true }] : []),
  ];

  let outcome = null;
  if (brief.flow === 'sdr' && typeof brief.meeting_booked === 'boolean') {
    outcome = { label: t.debriefMeeting, value: brief.meeting_booked };
  } else if (brief.flow === 'ae' && typeof brief.next_step_agreed === 'boolean') {
    outcome = { label: t.debriefNextStep, value: brief.next_step_agreed };
  }

  const missed = (brief.missed ?? [])
    .filter((item) => item?.label)
    .map((item) => ({
      id: String(item.id ?? item.label),
      label: item.kind === 'objection' ? objectionLabel(item.label, t) : item.label,
    }));
  const moments = (brief.highlights ?? []).filter(Boolean);

  return { state: 'ready', kept, fix, bars: bars.length > 1 ? bars : [], outcome, missed, moments };
}

const percent = (value) => `${Math.round(value * 100)} %`;

/** Pure: brief in, markup out. Node-testable, no DOM. */
export function renderDebrief(brief, lang) {
  const t = strings(lang);
  const view = debriefView(brief, lang);
  if (view.state === 'hidden') return html``;
  if (view.state === 'pending') {
    return html`<section class="v-debrief" aria-busy="true"><p class="v-debrief__muted" role="status">${t.debriefPreparing}</p></section>`;
  }
  if (view.state === 'no_playbook' || view.state === 'empty') {
    return html`<section class="v-debrief"><p class="v-debrief__muted">${view.state === 'no_playbook' ? t.debriefNoPlaybook : t.debriefEmpty}</p></section>`;
  }

  const { kept, fix, bars, outcome, missed, moments } = view;
  const trend = bars.length
    ? html`<span class="v-debrief__trend" role="img" aria-label="${t.debriefTrend}">${bars.map(
        (bar) => html`<span class="v-debrief__bar${bar.current ? ' is-current' : ''}${bar.value == null ? ' is-empty' : ''}" style="--v-bar:${bar.value == null ? 0.12 : Math.max(0.12, bar.value)}" title="${bar.value == null ? '—' : percent(bar.value)}"></span>`,
      )}</span>`
    : '';

  return html`<section class="v-debrief">
  ${kept ? html`<div class="v-debrief__row">
    <p class="v-debrief__caps">${t.debriefKept}</p>
    <p class="v-debrief__kept">${kept.label}${kept.quote ? html` <q>${kept.quote}</q>` : ''}</p>
  </div>` : ''}
  ${fix ? html`<div class="v-debrief__row">
    <p class="v-debrief__caps">${t.debriefFix}${fix.focus ? html`<span class="v-debrief__focus">${t.debriefFocus}</span>` : ''}</p>
    <p class="v-debrief__fix">${fix.label}</p>
    ${fix.criterion ? html`<p class="v-debrief__muted">${fix.criterion}</p>` : ''}
    ${fix.say ? html`<p class="v-debrief__say">${t.debriefTry} <q>${fix.say}</q></p>` : ''}
  </div>` : ''}
  ${trend || outcome ? html`<footer class="v-debrief__foot">
    ${outcome ? html`<span class="v-debrief__caps">${outcome.label} · ${outcome.value ? t.debriefYes : t.debriefNo}</span>` : html`<span></span>`}
    ${trend}
  </footer>` : ''}
  ${missed.length || moments.length ? html`<details class="v-debrief__detail">
    <summary>${t.debriefDetail}</summary>
    ${missed.length ? html`<p class="v-debrief__caps">${t.debriefMissed}</p><ul>${missed.map((item) => html`<li>${item.label}</li>`)}</ul>` : ''}
    ${moments.length ? html`<p class="v-debrief__caps">${t.debriefMoments}</p><ul>${moments.map((line) => html`<li>${line}</li>`)}</ul>` : ''}
  </details>` : ''}
</section>`;
}

export function debriefNeedsRepaint(prev, next) {
  return JSON.stringify(prev ?? null) !== JSON.stringify(next ?? null);
}
