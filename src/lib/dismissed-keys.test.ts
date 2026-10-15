import assert from "node:assert/strict";
import test from "node:test";
import { addDismissed, parseDismissed, removeDismissed } from "./dismissed-keys.ts";

const store = (keys: Set<string>) => JSON.stringify([...keys]);

test("two instances that mounted before either hid a line both keep their key", () => {
  let stored: string | null = null; // both instances read an empty list at mount
  stored = store(addDismissed(stored, "A"));
  stored = store(addDismissed(stored, "B")); // B's own view is still empty; the change starts from storage
  assert.deepEqual([...parseDismissed(stored)].sort(), ["A", "B"]);
});

test("removing a key leaves the others and tolerates a key that is not stored", () => {
  const stored = store(new Set(["A", "B"]));
  assert.deepEqual([...removeDismissed(stored, "A")], ["B"]);
  assert.deepEqual([...removeDismissed(stored, "C")].sort(), ["A", "B"]);
  assert.deepEqual([...removeDismissed(null, "A")], []);
});

test("unreadable or malformed storage is an empty list", () => {
  assert.deepEqual([...parseDismissed("not json")], []);
  assert.deepEqual([...parseDismissed('{"a":1}')], []);
  assert.deepEqual([...parseDismissed(null)], []);
});
