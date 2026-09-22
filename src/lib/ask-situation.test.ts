import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { askConfirmation, askSituation } from "./ask-situation.ts";

describe("ask situation", () => {
  it("uses a different sentence for an empty chat, no results, and a partial CRM read", () => {
    const empty = askSituation({ hasTurns: false });
    const none = askSituation({ hasTurns: true, coverage: "complete", items: 0 });
    const partial = askSituation({ hasTurns: true, coverage: "partial", items: 1 });
    const forbidden = askSituation({ hasTurns: true, coverage: "forbidden", items: 0 });
    assert.equal(empty.action, "ask");
    assert.match(empty.message, /Pregunta/);
    assert.equal(none.action, "none");
    assert.match(none.message, /No hay resultados/);
    assert.equal(partial.action, "retry");
    assert.match(partial.message, /parte/);
    assert.equal(forbidden.action, "retry");
    assert.match(forbidden.message, /permiso/);
    const messages = new Set([empty.message, none.message, partial.message, forbidden.message]);
    assert.equal(messages.size, 4);
    assert.equal(none.message.includes("permiso"), false);
    assert.equal(forbidden.message.includes("No hay resultados"), false);
  });

  it("a confirmation needs the operation, the revision, and the contact", () => {
    assert.equal(askConfirmation({}), null);
    assert.equal(askConfirmation({ confirmation: { operation_id: "op-1", revision: 3 } }), null);
    assert.deepEqual(
      askConfirmation({
        confirmation: { operation_id: "op-1", revision: 3, contact_id: "contact-a" },
      }),
      { operationId: "op-1", revision: 3, contactId: "contact-a" },
    );
  });
});
