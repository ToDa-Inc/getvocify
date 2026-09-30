import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  CHANNELS,
  ageLabel,
  channelOf,
  feedBusy,
  feedQuery,
  pageOf,
  retagOptions,
  rowPeople,
  rowStatus,
  rowTitle,
  typeChip,
  typeOptions,
} from "./interactions.ts";

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
      { key: "demo_zeta", label: "Álpha demo", scored: true, status: "paused" },
      { key: "closing", label: "Closing", scored: true, status: "draft" },
      { key: "discovery", label: "Discovery", scored: true, status: "published" },
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

describe("playbook status and retagOptions", () => {
  const all = typeOptions(
    {
      motions: { discovery: "published", closing: "paused", demo: "draft", onboarding: "missing", odd: "weird", bare: {} },
      details: { demo: { label: "Demo" }, onboarding: { label: "Onboarding" }, odd: { label: "Odd" }, bare: { label: "Bare" } },
    },
    "Interna",
    fallback,
  );
  const statusOf = (key: string) => all.find((option) => option.key === key)?.status;

  it("carries each type's playbook status, and none for an unknown one or for internal", () => {
    assert.equal(statusOf("discovery"), "published");
    assert.equal(statusOf("closing"), "paused");
    assert.equal(statusOf("demo"), "draft");
    assert.equal(statusOf("onboarding"), "missing");
    assert.equal(statusOf("odd"), undefined);
    assert.equal(statusOf("bare"), undefined);
    assert.equal("status" in all[all.length - 1], false);
  });

  it("offers only published types, alphabetically, then internal last", () => {
    const published = typeOptions(
      { motions: { zeta: "published", alpha: "published", mid: "paused" }, details: { zeta: { label: "Zeta" }, alpha: { label: "Alpha" }, mid: { label: "Mid" } } },
      "Interna",
    );
    assert.deepEqual(retagOptions(published).map((option) => option.key), ["alpha", "zeta", "internal"]);
  });

  it("drops paused, draft, missing and status-less types but keeps internal", () => {
    assert.deepEqual(retagOptions(all).map((option) => option.key), ["discovery", "internal"]);
    assert.deepEqual(retagOptions([{ key: "x", label: "X", scored: true }]), []);
    assert.deepEqual(retagOptions(typeOptions(null, "Interna")).map((option) => option.key), ["internal"]);
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

describe("channelOf", () => {
  it("keeps the four channels and drops anything else", () => {
    assert.equal(channelOf("voice_note"), "voice_note");
    assert.equal(channelOf("visit"), "visit");
    assert.equal(channelOf("sms"), null);
    assert.equal(channelOf(null), null);
  });
});

describe("rowStatus", () => {
  it("maps the pipeline status to what the row shows", () => {
    assert.equal(rowStatus({ status: "approved" }), "synced");
    assert.equal(rowStatus({ status: "pending_review" }), "review");
    assert.equal(rowStatus({ status: "extracting" }), "processing");
    assert.equal(rowStatus({ status: "pending_transcript" }), "processing");
    assert.equal(rowStatus({ status: "failed" }), "failed");
    assert.equal(rowStatus({ status: "rejected" }), null);
  });

  it("names a screened call that never connected", () => {
    assert.equal(rowStatus({ status: "pending_review", screeningOutcome: "voicemail" }), "voicemail");
    assert.equal(rowStatus({ status: "pending_review", screeningOutcome: "no_response" }), "no_answer");
    assert.equal(rowStatus({ status: "approved", screeningOutcome: "voicemail" }), "synced");
  });
});

describe("feedBusy", () => {
  it("is true only while a row is still being processed", () => {
    assert.equal(feedBusy([{ status: "approved" }, { status: "transcribing" }]), true);
    assert.equal(feedBusy([{ status: "approved" }, { status: "pending_review" }]), false);
    assert.equal(feedBusy([]), false);
  });
});

describe("rowTitle and rowPeople", () => {
  const memo = { extraction: { contactName: "Ana Ruiz", companyName: "Acme" } };

  it("titles the row with the contact, then the company, then the fallback", () => {
    assert.equal(rowTitle(memo, "Untitled"), "Ana Ruiz");
    assert.equal(rowTitle({ extraction: { companyName: "Acme" } }, "Untitled"), "Acme");
    assert.equal(rowTitle({ extraction: null }, "Untitled"), "Untitled");
  });

  it("joins who spoke and who they spoke to, skipping what is missing", () => {
    assert.equal(rowPeople(memo, "Luis"), "Luis → Acme");
    assert.equal(rowPeople(memo, null), "Acme");
    assert.equal(rowPeople({ extraction: { companyName: "Acme" } }, "Luis"), "Luis");
    assert.equal(rowPeople({ extraction: null }, null), "");
  });
});

describe("ageLabel", () => {
  const now = new Date("2026-09-30T12:00:00Z");

  it("is relative within a week", () => {
    assert.equal(ageLabel("2026-09-30T11:55:00Z", now, "en-GB"), "5 min ago");
    assert.equal(ageLabel("2026-09-30T11:59:50Z", now, "en-GB"), "1 min ago");
    assert.equal(ageLabel("2026-09-30T09:00:00Z", now, "en-GB"), "3 hr ago");
    assert.equal(ageLabel("2026-09-29T11:00:00Z", now, "en-GB"), "yesterday");
    assert.equal(ageLabel("2026-09-30T11:55:00Z", now, "es-ES"), "hace 5 min");
  });

  it("is a date after a week, with the year only when it differs", () => {
    assert.equal(ageLabel("2026-09-01T12:00:00Z", now, "en-GB"), "1 Sept");
    assert.equal(ageLabel("2025-09-01T12:00:00Z", now, "en-GB"), "1 Sept 2025");
  });

  it("is empty for a bad date", () => {
    assert.equal(ageLabel("nope", now, "en-GB"), "");
  });
});

describe("interactions copy", () => {
  const shape = (value: unknown): unknown =>
    value && typeof value === "object"
      ? Object.fromEntries(Object.entries(value).map(([key, inner]) => [key, shape(inner)]))
      : typeof value;

  it("has the same keys in Spanish and English, with a label for every channel and status", () => {
    const es = productCatalog.ES.interactions;
    const en = productCatalog.EN.interactions;
    assert.deepEqual(shape(es), shape(en));
    for (const channel of CHANNELS) assert.ok(es.channel[channel] && es.channels[channel]);
    for (const status of ["synced", "review", "processing", "failed", "voicemail", "no_answer"] as const) {
      assert.ok(es.status[status] && en.status[status]);
    }
  });
});
