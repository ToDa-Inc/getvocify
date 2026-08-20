import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  clearCachedPreview,
  getCachedPreview,
  previewCacheKey,
  setCachedPreview,
} from "./preview-cache.ts";

describe("previewCacheKey", () => {
  it("treats deal/contact/create as distinct preview identities", () => {
    const a = previewCacheKey({ memoId: "m1", contactId: "C1" });
    const b = previewCacheKey({ memoId: "m1", dealId: "D1", contactId: "C1" });
    const c = previewCacheKey({ memoId: "m1", contactId: "C1", createNewDeal: true });
    const d = previewCacheKey({ memoId: "m2", contactId: "C1" });
    assert.notEqual(a, b);
    assert.notEqual(a, c);
    assert.notEqual(a, d);
  });
});

describe("preview cache", () => {
  it("does not return another call’s preview", () => {
    clearCachedPreview();
    const esteban = previewCacheKey({ memoId: "m-esteban", contactId: "C-esteban" });
    const david = previewCacheKey({ memoId: "m-david", contactId: "C-david" });
    setCachedPreview(esteban, { selected_contact: { name: "Esteban" } });
    assert.equal(getCachedPreview(david), null);
    assert.deepEqual(getCachedPreview(esteban), { selected_contact: { name: "Esteban" } });
    clearCachedPreview("m-esteban");
    assert.equal(getCachedPreview(esteban), null);
  });
});
