import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import { HOY_SIGNAL_COPY } from "../../shared/ui/hoy-copy.js";

describe("Hoy card reason labels", () => {
  it("come from the one copy the pre-call brief also uses, unchanged", () => {
    assert.equal(productCatalog.ES.today_signal_uncalled, HOY_SIGNAL_COPY.es.today_signal_uncalled);
    assert.equal(productCatalog.ES.today_signal_pain, HOY_SIGNAL_COPY.es.today_signal_pain);
    assert.equal(productCatalog.EN.today_signal_uncalled, HOY_SIGNAL_COPY.en.today_signal_uncalled);
    assert.equal(productCatalog.EN.today_signal_pain, HOY_SIGNAL_COPY.en.today_signal_pain);
    assert.equal(productCatalog.ES.today_signal_uncalled, "Sin llamar");
    assert.equal(productCatalog.ES.today_signal_pain, "Dolor confirmado");
    assert.equal(productCatalog.EN.today_signal_uncalled, "Not called yet");
    assert.equal(productCatalog.EN.today_signal_pain, "Confirmed pain");
  });
});
