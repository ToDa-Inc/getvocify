import assert from "node:assert/strict";
import test from "node:test";
import { isAskShortcut } from "./ask-shortcut.ts";

const chord = { key: "k", metaKey: false, ctrlKey: false, shiftKey: false, altKey: false };

test("Cmd+K and Ctrl+K open Ask, in either case", () => {
  assert.equal(isAskShortcut({ ...chord, metaKey: true }), true);
  assert.equal(isAskShortcut({ ...chord, ctrlKey: true }), true);
  assert.equal(isAskShortcut({ ...chord, key: "K", metaKey: true }), true);
  assert.equal(isAskShortcut({ ...chord, metaKey: true, ctrlKey: true }), true);
});

test("K alone, another key, or an extra modifier does not", () => {
  assert.equal(isAskShortcut(chord), false);
  assert.equal(isAskShortcut({ ...chord, key: "j", metaKey: true }), false);
  assert.equal(isAskShortcut({ ...chord, metaKey: true, shiftKey: true }), false);
  assert.equal(isAskShortcut({ ...chord, ctrlKey: true, altKey: true }), false);
  assert.equal(isAskShortcut({ ...chord, ctrlKey: true, shiftKey: true }), false);
  assert.equal(isAskShortcut({ ...chord, key: "K", metaKey: true, shiftKey: true }), false);
});

test("a keydown without a key (browser autofill) is ignored, not a crash", () => {
  assert.equal(isAskShortcut({ ...chord, key: undefined, metaKey: true }), false);
});

test("typing through an IME composition is ignored", () => {
  assert.equal(isAskShortcut({ ...chord, metaKey: true, isComposing: true }), false);
});
