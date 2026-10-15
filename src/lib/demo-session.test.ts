import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  addBuyerLine,
  addSellerText,
  base64ToArrayBuffer,
  createDemoSession,
  hasPendingSeller,
  historyBeforeLastSeller,
  takeSellerTurn,
} from "./demo-session.ts";

describe("demo session", () => {
  it("joins seller speech into one turn and clears the buffer", () => {
    const s = createDemoSession();
    addSellerText(s, " Hola Marta ");
    addSellerText(s, "   ");
    addSellerText(s, "te llamo por Vocify");
    assert.equal(hasPendingSeller(s), true);
    assert.equal(takeSellerTurn(s), "Hola Marta te llamo por Vocify");
    assert.equal(hasPendingSeller(s), false);
    assert.equal(takeSellerTurn(s), "");
    assert.deepEqual(s.history, [{ role: "seller", text: "Hola Marta te llamo por Vocify" }]);
  });

  it("sends the history without the seller turn that goes as seller_text", () => {
    const s = createDemoSession();
    addBuyerLine(s, "¿Sí?");
    addSellerText(s, "Hola");
    takeSellerTurn(s);
    assert.deepEqual(historyBeforeLastSeller(s), [{ role: "buyer", text: "¿Sí?" }]);
    addBuyerLine(s, "Dime");
    assert.equal(historyBeforeLastSeller(s).length, 3);
  });

  it("decodes base64 audio bytes", () => {
    const buf = base64ToArrayBuffer(Buffer.from([1, 2, 3]).toString("base64"));
    assert.deepEqual([...new Uint8Array(buf)], [1, 2, 3]);
  });
});
