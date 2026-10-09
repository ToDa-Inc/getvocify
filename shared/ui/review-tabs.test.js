import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { renderToString } from './html.js';
import {
  activeReviewTab,
  renderReviewTabs,
  reviewTabs,
  reviewTabsNeedRepaint,
  showReviewPanel,
  stepReviewTab,
} from './components/review-tabs.js';

const ids = (tabs) => tabs.map((tab) => tab.id);

describe('review tabs', () => {
  it('always shows note, fields and tasks; counts only when there is something', () => {
    const tabs = reviewTabs();
    assert.deepEqual(ids(tabs), ['note', 'fields', 'tasks']);
    assert.equal(tabs[1].count, null);
    assert.equal(reviewTabs({ fieldCount: 4, taskCount: 2 })[1].count, 4);
    assert.equal(reviewTabs({ fieldCount: 4, taskCount: 2 })[2].count, 2);
    assert.equal(reviewTabs({ fieldCount: Number.NaN })[1].count, null);
  });

  it('adds email while a draft is written, ready or sent; the dot means ready to send', () => {
    assert.deepEqual(ids(reviewTabs({ followupStatus: 'unavailable' })), ['note', 'fields', 'tasks']);
    assert.deepEqual(ids(reviewTabs({ followupStatus: null })), ['note', 'fields', 'tasks']);
    const writing = reviewTabs({ followupStatus: 'generating' }).at(-1);
    assert.deepEqual(writing, { id: 'email', count: null, dot: false });
    assert.equal(reviewTabs({ followupStatus: 'ready' }).at(-1).dot, true);
    assert.equal(reviewTabs({ followupStatus: 'sent' }).at(-1).dot, false);
    assert.deepEqual(reviewTabs({ followupStatus: 'failed' }).at(-1), { id: 'email', count: null, dot: false });
  });

  it('adds coaching last, only when there is something to read', () => {
    assert.deepEqual(ids(reviewTabs({ followupStatus: 'ready', coaching: true })), [
      'note', 'fields', 'tasks', 'email', 'coaching',
    ]);
  });

  it('keeps the rep on their tab; falls back to note when it disappears', () => {
    const tabs = reviewTabs({ followupStatus: 'ready' });
    assert.equal(activeReviewTab(tabs, 'email'), 'email');
    assert.equal(activeReviewTab(reviewTabs(), 'email'), 'note');
    assert.equal(activeReviewTab(tabs, undefined), 'note');
  });

  it('walks tabs with arrows, wrapping, and jumps with Home/End', () => {
    const tabs = reviewTabs({ coaching: true });
    assert.equal(stepReviewTab(tabs, 'note', 'ArrowRight'), 'fields');
    assert.equal(stepReviewTab(tabs, 'note', 'ArrowLeft'), 'coaching');
    assert.equal(stepReviewTab(tabs, 'coaching', 'ArrowRight'), 'note');
    assert.equal(stepReviewTab(tabs, 'tasks', 'Home'), 'note');
    assert.equal(stepReviewTab(tabs, 'note', 'End'), 'coaching');
    assert.equal(stepReviewTab(tabs, 'tasks', 'Enter'), 'tasks');
  });

  it('renders an accessible tablist in the rep language', () => {
    const out = renderToString(renderReviewTabs({ tabs: reviewTabs({ fieldCount: 3, followupStatus: 'ready' }), active: 'fields' }, 'es'));
    assert.match(out, /role="tablist" aria-label="Revisión de la llamada"/);
    assert.match(out, /id="review-tab-fields" aria-controls="review-panel-fields" aria-selected="true" tabindex="0"/);
    assert.match(out, /aria-selected="false" tabindex="-1" data-action="tab" data-value="note"/);
    assert.match(out, />Campos<span class="v-tab__count">3<\/span>/);
    assert.match(out, /title="Borrador listo para enviar"/);
    assert.doesNotMatch(out, /v-tab__count">0/);
    const en = renderToString(renderReviewTabs({ tabs: reviewTabs(), active: 'note' }, 'en'));
    assert.match(en, />Note<\/button>/);
  });

  it('repaints only when the tabs or the selection change', () => {
    const tabs = reviewTabs({ fieldCount: 2 });
    assert.equal(reviewTabsNeedRepaint({ tabs, active: 'note' }, { tabs: reviewTabs({ fieldCount: 2 }), active: 'note' }), false);
    assert.equal(reviewTabsNeedRepaint({ tabs, active: 'note' }, { tabs, active: 'fields' }), true);
    assert.equal(reviewTabsNeedRepaint({ tabs, active: 'note' }, { tabs: reviewTabs({ fieldCount: 3 }), active: 'note' }), true);
  });

  it('shows only the active panel', () => {
    const panels = ['note', 'fields'].map((id) => ({ dataset: { reviewPanel: id }, hidden: false }));
    showReviewPanel({ querySelectorAll: () => panels }, 'fields');
    assert.deepEqual(panels.map((p) => p.hidden), [true, false]);
  });
});
