import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { prioritySurface, type PriorityView } from "./contact-priorities.ts";

const previous: PriorityView = {
  items: [{ id: "crm-A:42:deal-7", connection_id: "crm-A", contact_id: "42", deal_id: "deal-7", reason: "Confirmó el problema", coverage: "complete" }],
  coverage: "complete",
  title: null,
  action: null,
  observed_at: "2026-09-22T09:00:00Z",
};

describe("priority surface", () => {
  it("does not turn a forbidden response into an empty list", () => {
    const surface = prioritySurface({ data: null, errorStatus: 403, isLoading: false });
    assert.equal(surface.kind, "error");
    assert.equal("items" in surface, false);
  });

  it("keeps the previous candidates when a refetch fails", () => {
    const surface = prioritySurface({ data: previous, errorStatus: 500, isLoading: false });
    assert.equal(surface.kind, "list");
    if (surface.kind === "list") {
      assert.equal(surface.items[0].contact_id, "42");
      assert.equal(surface.stale, true);
      assert.equal(surface.observedAt, "2026-09-22T09:00:00Z");
    }
  });

  it("uses the server empty copy instead of inventing one", () => {
    const surface = prioritySurface({
      data: { items: [], coverage: "partial", title: "Falta parte del historial", action: "Reintentar", observed_at: null },
      errorStatus: null,
      isLoading: false,
    });
    assert.equal(surface.kind, "empty");
    if (surface.kind === "empty") assert.equal(surface.title, "Falta parte del historial");
  });
});
