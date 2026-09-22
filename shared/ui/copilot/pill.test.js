import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatPillText,
  initialPillState,
  pillDecision,
  PILL_CATEGORY_COOLDOWN_MS,
  PILL_MAX_SHOW_MS,
  PILL_MIN_HOLD_MS,
} from "./pill.js";

describe("formatPillText", () => {
  it("collapses newlines and caps at 90 characters", () => {
    assert.equal(formatPillText("  hola\nmundo  "), "hola mundo");
    assert.equal(formatPillText("x".repeat(120)).length, 90);
    assert.equal(formatPillText(""), "");
  });
});

describe("pillDecision", () => {
  const meeting = {
    kind: "meeting",
    enabled: true,
    speakerRole: "prospect",
    meetingId: "m1",
  };

  it("stays off for non-meetings, disabled assist, rep speech, or empty text", () => {
    const s0 = initialPillState();
    assert.deepEqual(
      pillDecision(s0, { ...meeting, kind: "call", text: "Hola" }, 0).show,
      false,
    );
    assert.deepEqual(
      pillDecision(s0, { ...meeting, enabled: false, text: "Hola" }, 0).show,
      false,
    );
    assert.deepEqual(
      pillDecision(s0, { ...meeting, enabled: null, text: "Hola" }, 0).show,
      false,
    );
    assert.deepEqual(
      pillDecision(s0, { ...meeting, speakerRole: "rep", text: "Hola" }, 0).show,
      false,
    );
    assert.deepEqual(pillDecision(s0, { ...meeting, text: "   " }, 0).show, false);
  });

  it("shows normalized text when allowed", () => {
    const out = pillDecision(initialPillState(), { ...meeting, text: "  Aclara\nel coste  " }, 1000);
    assert.equal(out.show, true);
    assert.equal(out.text, "Aclara el coste");
  });

  it("respects min hold, max show, and category cooldown", () => {
    let state = initialPillState();
    const first = pillDecision(state, { ...meeting, text: "Uno", category: "price" }, 0);
    assert.equal(first.show, true);
    state = first.state;

    const duringHold = pillDecision(
      state,
      { ...meeting, text: "Dos", category: "timing" },
      PILL_MIN_HOLD_MS - 1,
    );
    assert.equal(duringHold.show, true);
    assert.equal(duringHold.text, "Uno");

    const afterMax = pillDecision(
      duringHold.state,
      { ...meeting, text: "Uno", category: "price" },
      PILL_MAX_SHOW_MS,
    );
    assert.equal(afterMax.show, false);

    const again = pillDecision(
      afterMax.state,
      { ...meeting, text: "Uno", category: "price" },
      PILL_MAX_SHOW_MS + 1,
    );
    assert.equal(again.show, false);

    const afterCooldown = pillDecision(
      again.state,
      { ...meeting, text: "Uno", category: "price" },
      PILL_CATEGORY_COOLDOWN_MS + 1,
    );
    assert.equal(afterCooldown.show, true);
  });

  it("uses none when category is missing and clears on meeting change", () => {
    let state = initialPillState();
    const shown = pillDecision(state, { ...meeting, text: "Hola" }, 0);
    state = shown.state;
    assert.equal(state.lastShownAt.none, 0);

    const stillVisible = pillDecision(state, { ...meeting, text: "Otra" }, 1000);
    assert.equal(stillVisible.show, true);
    assert.equal(stillVisible.text, "Hola");

    const blocked = pillDecision(
      stillVisible.state,
      { ...meeting, text: "Otra" },
      PILL_MAX_SHOW_MS + 1,
    );
    assert.equal(blocked.show, false);

    const switched = pillDecision(blocked.state, { ...meeting, meetingId: "m2", text: "Nueva" }, 2000);
    assert.equal(switched.show, true);
    assert.equal(switched.state.visible.text, "Nueva");
    assert.deepEqual(switched.state.lastShownAt, { none: 2000 });
  });
});
