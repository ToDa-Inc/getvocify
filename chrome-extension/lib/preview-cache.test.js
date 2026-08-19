import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  clearInflightPreview,
  clearPreviewCache,
  getCachedPreview,
  getInflightPreview,
  previewCacheKey,
  setCachedPreview,
  setInflightPreview,
} from './preview-cache.js';

describe('previewCacheKey', () => {
  it('treats deal/contact/create as distinct preview identities', () => {
    const a = previewCacheKey({ memoId: 'm1', contactId: 'C1' });
    const b = previewCacheKey({ memoId: 'm1', dealId: 'D1', contactId: 'C1' });
    const c = previewCacheKey({ memoId: 'm1', contactId: 'C1', createNewDeal: true });
    assert.notEqual(a, b);
    assert.notEqual(a, c);
  });
});

describe('preview cache', () => {
  it('returns a stored preview until cleared', () => {
    clearPreviewCache();
    const key = previewCacheKey({ memoId: 'm1', contactId: 'C1' });
    setCachedPreview(key, { selected_deal: null });
    assert.deepEqual(getCachedPreview(key), { selected_deal: null });
    clearPreviewCache('m1');
    assert.equal(getCachedPreview(key), null);
  });

  it('dedupes in-flight fetches', () => {
    clearPreviewCache();
    const key = previewCacheKey({ memoId: 'm2' });
    const p = Promise.resolve({ ok: true });
    setInflightPreview(key, p);
    assert.equal(getInflightPreview(key), p);
    clearInflightPreview(key);
    assert.equal(getInflightPreview(key), null);
  });
});
