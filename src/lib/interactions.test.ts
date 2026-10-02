import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  CHANNELS,
  callOutcome,
  channelOf,
  feedBusy,
  feedQuery,
  groupByDay,
  initialsOf,
  interactionsAuthor,
  memoTypeLine,
  memoTypeName,
  pageOf,
  retagOptions,
  scrolledToEnd,
  summaryParts,
  rowHeadline,
  rowStatus,
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

describe("interactionsAuthor", () => {
  it("opens a manager on everyone, not on their own list", () => {
    assert.equal(interactionsAuthor(true, null), null);
    assert.equal(interactionsAuthor(true, ""), null);
  });

  it("keeps a ?author= deep link for a manager", () => {
    assert.equal(interactionsAuthor(true, "rep-2"), "rep-2");
  });

  it("never filters by author for a member, whose list is already their own", () => {
    assert.equal(interactionsAuthor(false, "rep-2"), null);
    assert.equal(interactionsAuthor(false, null), null);
  });
});

describe("memo detail type line", () => {
  for (const [lang, catalog] of [["ES", productCatalog.ES], ["EN", productCatalog.EN]] as const) {
    const copy = { ...catalog.pb2, motions: catalog.motions, internal: catalog.interactions.internal };

    it(`names internal from the catalog, never the raw key (${lang})`, () => {
      assert.equal(memoTypeName("internal", null, copy), catalog.interactions.internal);
      assert.notEqual(memoTypeName("internal", null, copy), "internal");
    });

    it(`says an internal memo is not scored instead of "scored as" (${lang})`, () => {
      assert.equal(memoTypeLine("internal", "x", copy), catalog.pb2.memoPlaybookInternal);
      assert.equal(memoTypeLine("discovery", "Demo", copy), catalog.pb2.memoPlaybook.replace("{name}", "Demo"));
    });

    it(`keeps a stored label, then the catalog label, then the key (${lang})`, () => {
      assert.equal(memoTypeName("renewal", "Renovación", copy), "Renovación");
      assert.equal(memoTypeName("discovery", null, copy), catalog.pb2.typeLabels.discovery || catalog.motions.discovery);
      assert.equal(memoTypeName("enterprise", null, copy), "enterprise");
    });
  }

  it("uses the Interna copy", () => {
    assert.equal(productCatalog.ES.pb2.memoPlaybookInternal, "Interna · no se puntúa");
    assert.equal(productCatalog.EN.pb2.memoPlaybookInternal, "Internal · not scored");
  });
});

describe("summaryParts", () => {
  it("takes the first heading as the topic and the first bullet as the line", () => {
    const md = "### Situación actual del CRM\n* El cliente usa un **CRM propio** y complejo.\n* Otra cosa";
    assert.deepEqual(summaryParts(md), { heading: "Situación actual del CRM", line: "El cliente usa un CRM propio y complejo." });
  });
  it("handles numbered lists, dashes and a summary with no heading", () => {
    assert.deepEqual(summaryParts("1. Primer punto\n2. Segundo"), { heading: null, line: "Primer punto" });
    assert.deepEqual(summaryParts("## Tema\n- punto"), { heading: "Tema", line: "punto" });
  });
  it("is empty for nothing", () => {
    assert.deepEqual(summaryParts(""), { heading: null, line: null });
    assert.deepEqual(summaryParts(null), { heading: null, line: null });
    assert.deepEqual(summaryParts("###   \n-  "), { heading: null, line: null });
  });
});

describe("rowHeadline", () => {
  const summary = "### Prueba de audio\n- Se comprueba que el audio se escucha bien.";
  it("names the person and company, and previews the summary", () => {
    const memo = { extraction: { contactName: "Juan Poblet", companyName: "Dextail", summary } };
    assert.deepEqual(rowHeadline(memo, "Llamada de 12 min"), {
      title: "Juan Poblet · Dextail",
      preview: "Se comprueba que el audio se escucha bien.",
    });
  });
  it("uses the summary's topic when nobody is named", () => {
    assert.deepEqual(rowHeadline({ extraction: { summary } }, "Llamada de 12 min"), {
      title: "Prueba de audio",
      preview: "Se comprueba que el audio se escucha bien.",
    });
  });
  it("does not repeat a company equal to the contact", () => {
    const memo = { extraction: { contactName: "Raffo", companyName: "raffo", summary: "" } };
    assert.deepEqual(rowHeadline(memo, "x"), { title: "Raffo", preview: null });
  });
  it("falls back when there is nothing to say", () => {
    assert.deepEqual(rowHeadline({ extraction: null }, "Llamada de 12 min"), { title: "Llamada de 12 min", preview: null });
  });
});

describe("groupByDay", () => {
  const now = new Date(2026, 8, 30, 18, 0);
  const at = (d: number, h: number) => ({ createdAt: new Date(2026, 8, d, h, 0).toISOString() });
  it("groups in order under Hoy, Ayer and a short date", () => {
    const groups = groupByDay([at(30, 17), at(30, 9), at(29, 22), at(28, 10)], now, "es-ES");
    assert.deepEqual(groups.map((group) => [group.label, group.items.length]), [["Hoy", 2], ["Ayer", 1], ["Lun, 28 sept", 1]]);
  });
  it("speaks English too, and puts bad dates last", () => {
    const groups = groupByDay([at(30, 9), { createdAt: "nope" }], now, "en-GB");
    assert.deepEqual(groups.map((group) => group.label), ["Today", ""]);
  });
  it("adds the year only for another year", () => {
    const groups = groupByDay([{ createdAt: new Date(2025, 11, 31, 10).toISOString() }], now, "es-ES");
    assert.match(groups[0].label, /2025/);
  });
  it("is empty for no items", () => {
    assert.deepEqual(groupByDay([], now, "es-ES"), []);
  });
});

describe("initialsOf", () => {
  it("extracts initials from a two-part name", () => {
    assert.equal(initialsOf({ name: "Juan Poblet", email: "juan@example.com" }), "JP");
  });

  it("extracts initials from a single-name person", () => {
    assert.equal(initialsOf({ name: "Madonna", email: "madonna@example.com" }), "M");
  });

  it("falls back to email local-part when name is missing or null", () => {
    assert.equal(initialsOf({ name: null, email: "john.doe@example.com" }), "JD");
    assert.equal(initialsOf({ name: "", email: "alice@example.com" }), "A");
  });

  it("trims whitespace and handles multi-part names", () => {
    assert.equal(initialsOf({ name: "  Ana María García  ", email: "ana@example.com" }), "AG");
  });

  it("returns empty string when both name and email are empty", () => {
    assert.equal(initialsOf({ name: null, email: "" }), "");
  });
});

describe("callOutcome", () => {
  it("returns voicemail when screeningOutcome is voicemail", () => {
    assert.equal(callOutcome({ screeningOutcome: "voicemail", audioDuration: 30 }), "voicemail");
  });

  it("returns no_response when screeningOutcome is no_response", () => {
    assert.equal(callOutcome({ screeningOutcome: "no_response", audioDuration: 0 }), "no_response");
  });

  it("returns connected when audioDuration > 0 and no special screeningOutcome", () => {
    assert.equal(callOutcome({ screeningOutcome: "connected", audioDuration: 120 }), "connected");
    assert.equal(callOutcome({ audioDuration: 45 }), "connected");
  });

  it("returns connected when screeningOutcome is missing", () => {
    assert.equal(callOutcome({ audioDuration: 10 }), "connected");
  });

  it("prioritizes screeningOutcome over audioDuration", () => {
    assert.equal(callOutcome({ screeningOutcome: "voicemail", audioDuration: 0 }), "voicemail");
    assert.equal(callOutcome({ screeningOutcome: "no_response", audioDuration: 100 }), "no_response");
  });
});

describe("scrolledToEnd", () => {
  it("is false while there is more below, true at the bottom (with a little slack)", () => {
    assert.equal(scrolledToEnd({ scrollTop: 0, clientHeight: 400, scrollHeight: 1000 }), false);
    assert.equal(scrolledToEnd({ scrollTop: 592, clientHeight: 400, scrollHeight: 1000 }), true);
    assert.equal(scrolledToEnd({ scrollTop: 560, clientHeight: 400, scrollHeight: 1000 }), false);
  });

  it("counts a list that does not overflow as read", () => {
    assert.equal(scrolledToEnd({ scrollTop: 0, clientHeight: 400, scrollHeight: 380 }), true);
  });
});
