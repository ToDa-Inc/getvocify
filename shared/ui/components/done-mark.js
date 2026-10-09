import { html } from '../html.js';

/**
 * The "it's in your CRM" mark, the same on dashboard, extension and desktop.
 * Plays once when a write lands: the circle draws, the check strokes in, one soft
 * ring fades out. `animate: false` is the settled state, for a call saved earlier.
 * Pure SVG + CSS (vocify-ui.css `.v-done`): it replays whenever the markup is repainted.
 *
 * @param {{ tone?: 'success'|'failed', size?: number, animate?: boolean, label?: string }} [opts]
 */
export function renderDoneMark({ tone = 'success', size = 64, animate = true, label = '' } = {}) {
  const failed = tone === 'failed';
  const px = Math.max(16, Math.round(Number(size) || 64));
  const classes = ['v-done', failed ? 'v-done--failed' : '', animate ? 'is-playing' : ''].filter(Boolean).join(' ');
  // pathLength="1" normalises every stroke, so one keyframe draws any of them.
  const glyph = failed
    ? html`<path class="v-done__glyph" pathLength="1" d="M26 15.5v13"/><path class="v-done__glyph v-done__dot" pathLength="1" d="M26 35.5v.5"/>`
    : html`<path class="v-done__glyph" pathLength="1" d="M16.5 26.5 23 33l12.5-13.5"/>`;
  return html`<span class="${classes}" style="--v-done-size:${px}px" ${label ? html`role="img" aria-label="${label}"` : html`aria-hidden="true"`}><span class="v-done__halo" aria-hidden="true"></span><svg class="v-done__svg" viewBox="0 0 52 52" aria-hidden="true" focusable="false"><circle class="v-done__disc" cx="26" cy="26" r="24"/><circle class="v-done__ring" pathLength="1" cx="26" cy="26" r="24"/>${glyph}</svg></span>`;
}
