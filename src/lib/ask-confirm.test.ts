import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  cancelConfirm,
  confirmErrorDetail,
  confirmResult,
  pendingConfirmFromTurn,
} from "./ask-confirm.ts";

describe("confirmResult", () => {
  it("clears pending and shows follow-up text after a succeeded confirm", () => {
    assert.deepEqual(confirmResult({ status: "succeeded", applied: true, text: "Nota creada" }), {
      clearPending: true,
      text: "Nota creada",
    });
  });

  it("clears pending without changing text when the confirm body has no text", () => {
    assert.deepEqual(confirmResult({ status: "succeeded", applied: true }), {
      clearPending: true,
      text: null,
    });
  });

  it("clears pending on a replayed confirm", () => {
    assert.deepEqual(
      confirmResult({ replayed: true, applied: true, operation_id: "op-1" }),
      { clearPending: true, text: null },
    );
  });

  it("keeps pending when the response is not a success", () => {
    assert.deepEqual(confirmResult({ status: "proposed" }), {
      clearPending: false,
      text: null,
    });
  });
});

describe("pendingConfirmFromTurn", () => {
  it("returns null when confirmation.cancelled is true on a reopened turn", () => {
    assert.equal(
      pendingConfirmFromTurn({
        confirmation: {
          operation_id: "op-1",
          revision: 2,
          contact_id: "contact-a",
          cancelled: true,
        },
      }),
      null,
    );
  });

  it("still returns pending when confirmation is not cancelled", () => {
    assert.deepEqual(
      pendingConfirmFromTurn({
        confirmation: {
          operation_id: "op-1",
          revision: 2,
          contact_id: "contact-a",
        },
      }),
      { operationId: "op-1", revision: 2, contactId: "contact-a" },
    );
  });
});

describe("cancelConfirm", () => {
  it("drops pending without replacing the answer text", () => {
    assert.deepEqual(cancelConfirm(), { clearPending: true, text: null });
  });
});

describe("confirmErrorDetail", () => {
  it("reads a string detail from an error body", () => {
    assert.equal(confirmErrorDetail({ detail: "el contacto cambió" }), "el contacto cambió");
  });

  it("returns null when detail is missing", () => {
    assert.equal(confirmErrorDetail({}), null);
  });
});
