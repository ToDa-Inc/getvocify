import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { CADENCE_STOPPERS, cadenceInputs, cadenceOverrides, validDays } from "./followup-cadence.ts";

const DEFAULTS = {
  interest_high: 2, interest_medium: 5, interest_low: 30, price: 7, authority: 5,
  trust: 7, competitor: 14, status_quo: 14, timing: 21, other: 7,
};

describe("follow-up cadence editor", () => {
  it("shows the override where there is one, else the default", () => {
    const inputs = cadenceInputs({ price: 3 }, DEFAULTS);
    assert.equal(inputs.price, "3");
    assert.equal(inputs.timing, "21");
    assert.deepEqual(Object.keys(inputs), [...CADENCE_STOPPERS]);
    assert.equal(cadenceInputs(null, null).price, "");
  });

  it("saves only the waits that differ from the default", () => {
    const inputs = cadenceInputs({ price: 3 }, DEFAULTS);
    assert.deepEqual(cadenceOverrides(inputs, DEFAULTS), { price: 3 });
    assert.deepEqual(cadenceOverrides({ ...inputs, price: "7" }, DEFAULTS), {});
    assert.deepEqual(cadenceOverrides({ ...inputs, timing: "90" }, DEFAULTS), { price: 3, timing: 90 });
  });

  it("refuses anything that is not 1 to 90 whole days", () => {
    for (const bad of ["0", "91", "2.5", "", "abc", "-3"]) {
      assert.equal(validDays(bad), false, bad);
      assert.equal(cadenceOverrides({ ...cadenceInputs(null, DEFAULTS), price: bad }, DEFAULTS), null);
    }
    assert.equal(validDays("1"), true);
    assert.equal(validDays("90"), true);
  });
});
