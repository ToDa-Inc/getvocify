import { html } from '../html.js';
import { strings } from '../i18n.js';

/**
 * The post-call review in tabs, one model for dashboard, extension and desktop.
 * Note, fields and tasks always show: each has its own add, so an empty tab is
 * still a place to act. Email shows once a draft exists, is being written, or
 * failed to load (so the retry is reachable).
 * Coaching shows once there is something to read. Who/deal and Confirm live
 * outside the tabs, so no tab ever hides the primary action.
 */
export const REVIEW_TAB_IDS = ['note', 'fields', 'tasks', 'email', 'coaching'];

// 'failed' is a host's own fetch error: the tab stays so its retry is reachable.
const EMAIL_VISIBLE = new Set(['generating', 'ready', 'sent', 'failed']);

/**
 * @param {{ fieldCount?: number, taskCount?: number, followupStatus?: string | null, coaching?: boolean }} input
 * @returns {{ id: string, count: number | null, dot: boolean }[]}
 */
export function reviewTabs({ fieldCount = 0, taskCount = 0, followupStatus = null, coaching = false } = {}) {
  const count = (n) => (Number.isFinite(n) && n > 0 ? Math.round(n) : null);
  const tabs = [
    { id: 'note', count: null, dot: false },
    { id: 'fields', count: count(fieldCount), dot: false },
    { id: 'tasks', count: count(taskCount), dot: false },
  ];
  if (EMAIL_VISIBLE.has(followupStatus)) {
    tabs.push({ id: 'email', count: null, dot: followupStatus === 'ready' });
  }
  if (coaching) tabs.push({ id: 'coaching', count: null, dot: false });
  return tabs;
}

/** Keep the rep where they are; fall back to the note only when their tab went away. */
export function activeReviewTab(tabs, current) {
  return tabs.some((tab) => tab.id === current) ? current : 'note';
}

/** Arrow keys walk the tabs and wrap; Home/End jump. Anything else stays put. */
export function stepReviewTab(tabs, current, key) {
  const ids = tabs.map((tab) => tab.id);
  const at = Math.max(0, ids.indexOf(current));
  if (key === 'ArrowRight') return ids[(at + 1) % ids.length];
  if (key === 'ArrowLeft') return ids[(at - 1 + ids.length) % ids.length];
  if (key === 'Home') return ids[0];
  if (key === 'End') return ids[ids.length - 1];
  return current;
}

export function reviewTabLabel(id, lang) {
  const t = strings(lang);
  return {
    note: t.reviewTabNote,
    fields: t.reviewTabFields,
    tasks: t.reviewTabTasks,
    email: t.reviewTabEmail,
    coaching: t.reviewTabCoaching,
  }[id] ?? '';
}

/** Pure: view in, markup out. Panels carry id `review-panel-<tab>` on every surface. */
export function renderReviewTabs(view, lang) {
  const t = strings(lang);
  const tabs = view?.tabs ?? [];
  const active = activeReviewTab(tabs, view?.active);
  return html`<div class="v-tabs" role="tablist" aria-label="${t.reviewTabsLabel}">${tabs.map(
    (tab) => html`<button type="button" role="tab" class="v-tab" id="review-tab-${tab.id}" aria-controls="review-panel-${tab.id}" aria-selected="${tab.id === active ? 'true' : 'false'}" tabindex="${tab.id === active ? '0' : '-1'}" data-action="tab" data-value="${tab.id}"${tab.dot ? html` title="${t.reviewTabEmailReady}"` : ''}>${reviewTabLabel(tab.id, lang)}${tab.count ? html`<span class="v-tab__count">${tab.count}</span>` : ''}${tab.dot ? html`<span class="v-tab__dot" aria-hidden="true"></span><span class="v-sr">${t.reviewTabEmailReady}</span>` : ''}</button>`,
  )}</div>`;
}

export function reviewTabsNeedRepaint(prev, next) {
  if (prev?.active !== next?.active) return true;
  return JSON.stringify(prev?.tabs ?? []) !== JSON.stringify(next?.tabs ?? []);
}

/** Vanilla hosts: show the active panel, hide the rest. Hidden panels keep their state. */
export function showReviewPanel(root, active) {
  if (!root?.querySelectorAll) return;
  root.querySelectorAll('[data-review-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.reviewPanel !== active;
  });
}
