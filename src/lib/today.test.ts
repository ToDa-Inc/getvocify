import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  todaySurface,
  cardsAfterDismiss,
  crmContactsUrl,
  crmTasksUrl,
  originKey,
  splitTodayItems,
  supportingKeys,
  type TodayView,
  type TodayItem,
} from "./today.ts";

const copy = productCatalog.ES;

const emptyComplete: TodayView = {
  items: [],
  pulse: 0,
  folded_count: 0,
  generated_at: "2026-09-22T08:00:00Z",
  coverage: { intelligence: "complete", crm_tasks: "complete" },
};

const card: TodayView = {
  items: [{
    type: "going_cold",
    dedupe_key: "cold:42",
    contact_id: "42",
    reason: "Mostró mucho interés y lleváis 12 días sin hablar.",
    remote_id: null,
    origins: ["detected"],
    supporting: [],
  }],
  pulse: null,
  folded_count: 0,
  generated_at: "2026-09-22T08:00:00Z",
  coverage: { intelligence: "complete", crm_tasks: "unavailable" },
};

describe("today surface", () => {
  it("does not show an empty day before coverage arrives", () => {
    const surface = todaySurface(
      { data: null, errorStatus: null, isLoading: true, connected: true, role: "member" },
      copy,
    );
    assert.equal(surface.kind, "loading");
  });

  it("keeps a failed refetch from becoming nothing urgent", () => {
    const failed = todaySurface(
      { data: null, errorStatus: 500, isLoading: false, connected: true, role: "member" },
      copy,
    );
    assert.equal(failed.kind, "error");
    const stale = todaySurface(
      { data: card, errorStatus: 500, isLoading: false, connected: true, role: "member" },
      copy,
    );
    assert.equal(stale.kind, "list");
    if (stale.kind === "list") {
      assert.equal(stale.note, copy.today_incomplete);
      assert.equal(stale.pulse, null);
      assert.equal(stale.foldedCount, 0);
      assert.equal(stale.items[0].reason.includes("interés"), true);
    }
  });

  it("uses the clear copy only when every source is complete and nothing is pending", () => {
    const clear = todaySurface(
      { data: emptyComplete, errorStatus: null, isLoading: false, connected: true, role: "owner" },
      copy,
    );
    assert.equal(clear.kind, "clear");
    const partial = todaySurface({
      data: { ...emptyComplete, pulse: null, coverage: { intelligence: "complete", crm_tasks: "partial" } },
      errorStatus: null,
      isLoading: false,
      connected: true,
      role: "owner",
    }, copy);
    assert.equal(partial.kind, "incomplete");
    if (partial.kind === "incomplete") assert.equal(partial.title, copy.today_incomplete);
  });

  it("shows the no-activity onboarding when CRM is connected but Hoy has no payload", () => {
    const surface = todaySurface(
      { data: null, errorStatus: null, isLoading: false, connected: true, role: "owner" },
      copy,
    );
    assert.equal(surface.kind, "no-activity");
    if (surface.kind === "no-activity") {
      assert.equal(surface.title, copy.today_no_activity);
      assert.deepEqual(surface.actions, ["today_record", "open_contacts"]);
    }
  });

  it("keeps the folded remainder on the list and names manual versus detected", () => {
    const folded = todaySurface(
      { data: { ...card, folded_count: 3 }, errorStatus: null, isLoading: false, connected: true, role: "member" },
      copy,
    );
    assert.equal(folded.kind, "list");
    if (folded.kind === "list") assert.equal(folded.foldedCount, 0);
    const split = splitTodayItems([
      card.items[0],
      { type: "manual_task", dedupe_key: null, reason: "Llamar", origins: ["manual"], supporting: [] },
    ]);
    assert.equal(split.calls.length, 1);
    assert.equal(split.tasks.length, 1);
    assert.equal(split.tasks[0].type, "manual_task");
    assert.equal(originKey(["manual"]), "today_origin_manual");
    assert.equal(originKey(["detected"]), "today_origin_detected");
    assert.equal(originKey(["detected", "manual"]), "today_origin_both");
    assert.deepEqual(supportingKeys(["going_cold", "unknown"]), ["today_signal_cold"]);
    assert.equal(crmContactsUrl("hubspot", "99"), "https://app.hubspot.com/contacts/99/objects/0-1");
    assert.equal(crmContactsUrl("hubspot", null), null);
    assert.equal(crmContactsUrl("pipedrive", null), "https://app.pipedrive.com/persons");
    assert.equal(crmTasksUrl("hubspot", "99"), "https://app.hubspot.com/contacts/99/objects/0-27/views/all/list");
    assert.equal(crmTasksUrl("pipedrive", null), "https://app.pipedrive.com/activities");
  });

  it("hides CRM manual tasks until they are useful in Hoy", () => {
    const crmOnly: TodayView = {
      items: [{
        type: "manual_task",
        dedupe_key: null,
        contact_id: "42",
        reason: "Llamar a Marina",
        remote_id: "task-9",
        origins: ["manual"],
        supporting: [],
      }],
      pulse: null,
      folded_count: 0,
      generated_at: "2026-09-22T08:00:00Z",
      coverage: { intelligence: "complete", crm_tasks: "complete" },
    };
    const surface = todaySurface(
      { data: crmOnly, errorStatus: null, isLoading: false, connected: true, role: "member" },
      copy,
    );
    assert.equal(surface.kind, "clear");
  });

  it("tells a member to wait for an admin when the CRM is disconnected", () => {
    const member = todaySurface(
      { data: null, errorStatus: null, isLoading: false, connected: false, role: "member" },
      copy,
    );
    assert.equal(member.kind, "connect");
    if (member.kind === "connect") assert.equal(member.action, null);
    const owner = todaySurface(
      { data: null, errorStatus: null, isLoading: false, connected: false, role: "owner" },
      copy,
    );
    if (owner.kind === "connect") assert.equal(owner.action, copy.connect_crm);
    const fromApi = todaySurface({
      data: { ...emptyComplete, pulse: null, coverage: { intelligence: "unavailable", crm_tasks: "unavailable" } },
      errorStatus: null,
      isLoading: false,
      connected: false,
      role: "member",
    }, copy);
    assert.equal(fromApi.kind, "connect");
  });
});

describe("dismiss stays undoable", () => {
  it("product catalog differs on dismiss and undo between EN and ES", () => {
    assert.notEqual(productCatalog.EN.dismiss, productCatalog.ES.dismiss);
    assert.notEqual(productCatalog.EN.undo, productCatalog.ES.undo);
  });

  it("shows a dismissed card returned by GET after reload", () => {
    const pending: TodayItem = { ...card.items[0], id: "sig-1", version: 4, status: "pending" };
    const dismissed: TodayItem = {
      ...pending,
      version: 5,
      status: "dismissed",
      undo_deadline: "2026-09-22T08:00:05Z",
      last_action_request_id: "act-2",
    };
    const before = Date.parse("2026-09-22T08:00:04Z");
    const listed = cardsAfterDismiss([dismissed], [], before);
    assert.equal(listed.length, 1);
    assert.equal(listed[0].last_action_request_id, "act-2");
  });

  it("keeps a dismissed card until the undo deadline and drops it after", () => {
    const pending: TodayItem = { ...card.items[0], id: "sig-1", version: 4, status: "pending" };
    const dismissed: TodayItem = {
      ...pending,
      version: 5,
      status: "dismissed",
      undo_deadline: "2026-09-22T08:00:05Z",
    };
    const before = Date.parse("2026-09-22T08:00:04Z");
    const after = Date.parse("2026-09-22T08:00:06Z");
    assert.equal(cardsAfterDismiss([pending], [dismissed], before)[0].status, "dismissed");
    assert.equal(cardsAfterDismiss([pending], [dismissed], after)[0].status, "pending");
    assert.equal(cardsAfterDismiss([], [dismissed], before).length, 1);
    assert.equal(cardsAfterDismiss([], [dismissed], after).length, 0);
  });
});
