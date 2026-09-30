import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { feedQuery, pageOf, typeChip, typeOptions } from "./interactions.ts";

const payload = {
  motions: { discovery: "published", closing: "draft", demo_zeta: "paused" },
  details: {
    discovery: { label: null },
    closing: { label: null },
    demo_zeta: { label: "Álpha demo" },
  },
};
const fallback = (key: string) => ({ discovery: "Discovery", closing: "Closing" })[key] ?? key;

describe("typeOptions", () => {
  it("orders types alphabetically by label with internal last and unscored", () => {
    const options = typeOptions(payload, "Internal", fallback);
    assert.deepEqual(options, [
      { key: "demo_zeta", label: "Álpha demo", scored: true },
      { key: "closing", label: "Closing", scored: true },
      { key: "discovery", label: "Discovery", scored: true },
      { key: "internal", label: "Internal", scored: false },
    ]);
  });

  it("uses the stored label first and the fallback only when there is none", () => {
    const options = typeOptions({ motions: { closing: "published" }, details: { closing: { label: "Cierre" } } }, "Interno", fallback);
    assert.equal(options[0].label, "Cierre");
  });

  it("falls back to the key without a label lookup", () => {
    assert.equal(typeOptions({ motions: { closing: "published" } }, "Internal")[0].label, "closing");
  });

  it("does not list internal twice and tolerates an empty or malformed payload", () => {
    assert.deepEqual(typeOptions({ motions: { internal: "published" } }, "Internal"), [
      { key: "internal", label: "Internal", scored: false },
    ]);
    assert.deepEqual(typeOptions(null, "Internal"), [{ key: "internal", label: "Internal", scored: false }]);
    assert.deepEqual(typeOptions({}, "Internal"), [{ key: "internal", label: "Internal", scored: false }]);
  });
});

describe("typeChip", () => {
  const options = typeOptions(payload, "Internal", fallback);

  it("is null without a key", () => {
    assert.equal(typeChip({}, options), null);
    assert.equal(typeChip({ salesMotionKey: null }, options), null);
    assert.equal(typeChip({ salesMotionKey: "" }, options), null);
  });

  it("uses the option label for a known key", () => {
    assert.deepEqual(typeChip({ salesMotionKey: "closing" }, options), { key: "closing", label: "Closing" });
    assert.deepEqual(typeChip({ salesMotionKey: "internal" }, options), { key: "internal", label: "Internal" });
  });

  it("shows the raw key for a type that is no longer listed", () => {
    assert.deepEqual(typeChip({ salesMotionKey: "old_type" }, options), { key: "old_type", label: "old_type" });
  });
});

describe("feedQuery", () => {
  it("asks for one row more than the page, from the page offset", () => {
    assert.deepEqual(feedQuery({ channel: "all", typeKey: "all", page: 0 }, 20), { limit: 21, offset: 0 });
    assert.equal(feedQuery({ channel: "all", typeKey: "all", page: 2 }, 20).offset, 40);
  });

  it("omits the filters that are all", () => {
    const query = feedQuery({ channel: "all", typeKey: "all", page: 0 }, 20);
    assert.equal("interactionKind" in query, false);
    assert.equal("salesMotionKey" in query, false);
    assert.equal("authorUserId" in query, false);
  });

  it("maps channel, type and author", () => {
    assert.deepEqual(feedQuery({ channel: "visit", typeKey: "closing", authorUserId: "u1", page: 1 }, 10), {
      limit: 11,
      offset: 10,
      interactionKind: "visit",
      salesMotionKey: "closing",
      authorUserId: "u1",
    });
  });
});

describe("pageOf", () => {
  it("trims the extra row and reports more", () => {
    assert.deepEqual(pageOf([1, 2, 3], 2), { items: [1, 2], hasMore: true });
  });

  it("has no more when the rows fit the page", () => {
    assert.deepEqual(pageOf([1, 2], 2), { items: [1, 2], hasMore: false });
  });

  it("is empty for no rows", () => {
    assert.deepEqual(pageOf([], 20), { items: [], hasMore: false });
  });
});
