import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { todaySurface, type TodayView } from "./today.ts";

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
    const surface = todaySurface({ data: null, errorStatus: null, isLoading: true, connected: true, role: "member" });
    assert.equal(surface.kind, "loading");
  });

  it("keeps a failed refetch from becoming nothing urgent", () => {
    const failed = todaySurface({ data: null, errorStatus: 500, isLoading: false, connected: true, role: "member" });
    assert.equal(failed.kind, "error");
    const stale = todaySurface({ data: card, errorStatus: 500, isLoading: false, connected: true, role: "member" });
    assert.equal(stale.kind, "list");
    if (stale.kind === "list") {
      assert.equal(stale.note, "Información incompleta");
      assert.equal(stale.pulse, null);
      assert.equal(stale.items[0].reason.includes("interés"), true);
    }
  });

  it("uses the clear copy only when every source is complete and nothing is pending", () => {
    const clear = todaySurface({ data: emptyComplete, errorStatus: null, isLoading: false, connected: true, role: "owner" });
    assert.equal(clear.kind, "clear");
    const partial = todaySurface({
      data: { ...emptyComplete, pulse: null, coverage: { intelligence: "complete", crm_tasks: "partial" } },
      errorStatus: null,
      isLoading: false,
      connected: true,
      role: "owner",
    });
    assert.equal(partial.kind, "incomplete");
    if (partial.kind === "incomplete") assert.equal(partial.title.includes("Nada urgente"), false);
  });

  it("tells a member to wait for an admin when the CRM is disconnected", () => {
    const member = todaySurface({ data: null, errorStatus: null, isLoading: false, connected: false, role: "member" });
    assert.equal(member.kind, "connect");
    if (member.kind === "connect") assert.equal(member.action, null);
    const owner = todaySurface({ data: null, errorStatus: null, isLoading: false, connected: false, role: "owner" });
    if (owner.kind === "connect") assert.equal(owner.action, "Conectar CRM");
    const fromApi = todaySurface({
      data: { ...emptyComplete, pulse: null, coverage: { intelligence: "unavailable", crm_tasks: "unavailable" } },
      errorStatus: null,
      isLoading: false,
      connected: false,
      role: "member",
    });
    assert.equal(fromApi.kind, "connect");
  });
});
