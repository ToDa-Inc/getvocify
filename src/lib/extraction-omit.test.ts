import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildApproveExtraction,
  canEditOrRemoveProposedField,
  omittedKeysFrom,
  proposedFieldKey,
  stripOmittedFields,
} from "./extraction-omit.ts";

describe("canEditOrRemoveProposedField", () => {
  it("allows bin on contact, deal, and company properties", () => {
    assert.equal(canEditOrRemoveProposedField({ object_type: "contacts", field_name: "phone" }), true);
    assert.equal(canEditOrRemoveProposedField({ object_type: "deals", field_name: "amount" }), true);
    assert.equal(canEditOrRemoveProposedField({ object_type: "companies", field_name: "domain" }), true);
  });

  it("does not treat identity labels or insights or line items as removable rows", () => {
    assert.equal(canEditOrRemoveProposedField({ object_type: "contacts", field_name: "contact_name" }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: "deals", field_name: "description" }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: "line_items", field_name: "name" }), false);
  });
});

describe("stripOmittedFields + approve", () => {
  it("drops omitted contact and deal values so approve cannot write them", () => {
    const next = buildApproveExtraction({
      memoExtraction: {
        contactPhone: "+34000000000",
        dealAmount: 5000,
        summary: "Old summary",
        raw_extraction: {
          amount: 5000,
          contact_properties: { phone: "+34000000000", jobtitle: "VP" },
        },
      },
      updates: [{ object_type: "contacts", field_name: "jobtitle", new_value: "CRO" }],
      omittedKeys: ["contacts:phone", "deals:amount"],
      summary: "Call recap",
      nextSteps: ["Send proposal"],
    });
    assert.equal((next.raw_extraction as Record<string, unknown>).contact_properties &&
      (next.raw_extraction as { contact_properties: Record<string, unknown> }).contact_properties.jobtitle, "CRO");
    assert.equal((next.raw_extraction as { contact_properties: Record<string, unknown> }).contact_properties.phone, undefined);
    assert.equal(next.contactPhone, null);
    assert.equal(next.dealAmount, null);
    assert.equal(next.summary, "Call recap");
  });

  it("computes omitted keys from original vs current proposed updates", () => {
    const original = [
      { object_type: "contacts", field_name: "phone" },
      { object_type: "deals", field_name: "amount" },
    ];
    const current = [{ object_type: "deals", field_name: "amount" }];
    assert.deepEqual(omittedKeysFrom(original, current), ["contacts:phone"]);
    assert.equal(proposedFieldKey(original[0]), "contacts:phone");
  });
});
