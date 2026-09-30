import { html, renderToString } from '../html.js';

/**
 * Icons that move only when something happens: a retry runs, a copy lands, a call
 * rings, a report arrives. Motion ported from itshover.com (refresh-icon, copy-icon,
 * phone-volume, filled-bell-icon) as plain SVG + CSS (vocify-ui.css `.v-ai`), so the
 * dashboard, extension and desktop play the same thing with no animation library.
 * Bell and phone keep the outline glyphs the product already draws; only the motion is theirs.
 *
 * Held states (host sets and clears them):   refresh `busy` · copy `done` · phone `ringing`
 * One-shot (playAnimIcon, replays on call):  bell `ring`
 * Hover plays a short preview inside any button or link; prefers-reduced-motion stills all of it.
 */
const GLYPHS = {
  refresh: html`<path d="M20 11a8.1 8.1 0 0 0-15.5-2m-.5-4v4h4"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4"/>`,
  copy: html`<g class="v-ai__sheets"><path d="M4.012 16.737A2.005 2.005 0 0 1 3 15V5c0-1.1.9-2 2-2h10c.75 0 1.158.385 1.5 1"/><path class="v-ai__front" d="M7 9.667A2.667 2.667 0 0 1 9.667 7h8.666A2.667 2.667 0 0 1 21 9.667v8.666A2.667 2.667 0 0 1 18.333 21H9.667A2.667 2.667 0 0 1 7 18.333z"/></g><path class="v-ai__check" pathLength="1" d="M5 12.5 10 17.5 19.5 7"/>`,
  phone: html`<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/><path class="v-ai__wave v-ai__wave--in" d="M14.05 6A5 5 0 0 1 18 10"/><path class="v-ai__wave v-ai__wave--out" d="M14.05 2a9 9 0 0 1 8 7.94"/>`,
  bell: html`<path class="v-ai__bell" d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path class="v-ai__clapper" d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>`,
};

export const ANIM_ICONS = Object.keys(GLYPHS);

const STATES = { refresh: ['busy'], copy: ['done'], phone: ['ringing'], bell: [] };

/** Just the <svg>, for hosts that own the wrapper element (the React AnimIcon). */
export function animIconSvg(name) {
  const glyph = GLYPHS[name];
  if (!glyph) return html``;
  return html`<svg class="v-ai__svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${glyph}</svg>`;
}

/** Wrapper classes and inline vars; shared by renderAnimIcon and the React wrapper. */
export function animIconAttrs(name, { size = 16, stroke, state = '' } = {}) {
  const px = Math.max(10, Math.round(Number(size) || 16));
  const held = (STATES[name] || []).includes(state) ? state : '';
  const width = Number(stroke);
  return {
    className: ['v-ai', `v-ai--${name}`, held ? `is-${held}` : ''].filter(Boolean).join(' '),
    style: `--v-ai-size:${px}px${width > 0 ? `;--v-ai-stroke:${width}` : ''}`,
  };
}

/**
 * @param {'refresh'|'copy'|'phone'|'bell'} name
 * @param {{ size?: number, stroke?: number, state?: string, label?: string }} [opts]
 */
export function renderAnimIcon(name, opts = {}) {
  if (!GLYPHS[name]) return html``;
  const { className, style } = animIconAttrs(name, opts);
  const a11y = opts.label ? html`role="img" aria-label="${opts.label}"` : html`aria-hidden="true"`;
  return html`<span class="${className}" style="${style}" ${a11y}>${animIconSvg(name)}</span>`;
}

/** Plays a one-shot (the bell's ring) and clears itself, so the next call replays it. */
export function playAnimIcon(el, play = 'ring') {
  if (!el) return;
  el.removeAttribute('data-v-play');
  void el.getBoundingClientRect(); // restart the keyframes when a ring is already playing
  el.setAttribute('data-v-play', play);
  el.addEventListener('animationend', () => el.removeAttribute('data-v-play'), { once: true });
}

/**
 * Copy landed: the icon inside `button` becomes a check and its label reads `copiedLabel`
 * for `ms`, then both return. The label is the button's `[data-v-label]` child when it
 * has one, else its own text. Replaces a toast for a moment the rep is already looking at.
 */
export function flashCopied(button, copiedLabel, ms = 1500) {
  if (!button) return;
  const icon = button.querySelector('.v-ai--copy');
  const labelEl = button.querySelector('[data-v-label]');
  clearTimeout(button._vCopiedTimer);
  if (button.dataset.vCopyLabel == null) button.dataset.vCopyLabel = labelEl ? labelEl.textContent : '';
  icon?.classList.add('is-done');
  if (labelEl && copiedLabel) labelEl.textContent = copiedLabel;
  button._vCopiedTimer = setTimeout(() => {
    icon?.classList.remove('is-done');
    if (labelEl) labelEl.textContent = button.dataset.vCopyLabel;
    delete button.dataset.vCopyLabel;
  }, ms);
}

/**
 * Static markup (extension popup, desktop) declares `<span data-v-icon="refresh" data-v-size="14"
 * data-v-stroke="1.5">` and this fills it with the shared glyph, so no surface copies an SVG by hand.
 */
export function hydrateAnimIcons(root = document) {
  root.querySelectorAll('[data-v-icon]').forEach((slot) => {
    const name = slot.getAttribute('data-v-icon');
    if (!GLYPHS[name] || slot.classList.contains('v-ai')) return;
    const size = Number(slot.getAttribute('data-v-size')) || undefined;
    const stroke = Number(slot.getAttribute('data-v-stroke')) || undefined;
    const { className, style } = animIconAttrs(name, { size, stroke });
    slot.classList.add(...className.split(' '));
    slot.setAttribute('style', style);
    slot.setAttribute('aria-hidden', 'true');
    slot.innerHTML = renderToString(animIconSvg(name));
  });
}
