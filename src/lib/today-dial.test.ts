import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { callTargetFromTodayItem } from "./today-dial.ts";

describe("callTargetFromTodayItem", () => {
  it("uses the card contact_id without a search query", () => {
    const target = callTargetFromTodayItem(
      { contact_id: "42" },
      [
        { contact_id: "99", phone: "+34600999888", name: "Other" },
        { contact_id: "42", phone: "+34600111222", name: "Ana" },
      ],
    );
    assert.deepEqual(target, {
      contactId: "42",
      phone: "+34600111222",
      name: "Ana",
    });
  });

  it("returns null when the card contact has no dialable phone", () => {
    assert.equal(
      callTargetFromTodayItem({ contact_id: "42" }, [{ contact_id: "42", phone: "n/a" }]),
      null,
    );
  });
});
