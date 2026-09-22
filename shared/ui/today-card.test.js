import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { presentExit, reduceTodayList, renderTodayCard, TODAY_EMPTY_FOCUS } from "./today-card.js";
import { renderToString } from "./html.js";

const pending = { id: "sig-1", status: "pending", version: 3, reason: "Quedaste en llamarle.", undoDeadline: null };

describe("today card", () => {
  it("moves pending v3 to dismissed v4 and undo returns pending v5", () => {
    const dismissed = reduceTodayList({ cards: [pending] }, {
      type: "action_result",
      id: "sig-1",
      status: "dismissed",
      version: 4,
      undoDeadline: "2026-09-22T10:00:05Z",
    });
    assert.equal(dismissed.cards[0].version, 4);
    assert.equal(dismissed.cards[0].undoDeadline, "2026-09-22T10:00:05Z");
    const restored = reduceTodayList(dismissed, { type: "undo", id: "sig-1", version: 5 });
    assert.equal(restored.cards.length, 1);
    assert.equal(restored.cards[0].status, "pending");
    assert.equal(restored.cards[0].version, 5);
    assert.equal(restored.focusId, "sig-1");
  });

  it("refreshes a conflict in place and keeps one card through a refetch", () => {
    const conflict = reduceTodayList({ cards: [{ ...pending, status: "dismissed", version: 4 }] }, {
      type: "conflict",
      card: { id: "sig-1", status: "dismissed", version: 4, undoDeadline: "2026-09-22T10:00:05Z" },
    });
    assert.equal(conflict.cards.length, 1);
    assert.equal(conflict.cards[0].version, 4);
    const duringExit = reduceTodayList({
      cards: [conflict.cards[0], { ...conflict.cards[0] }],
    }, { type: "undo", id: "sig-1", version: 5 });
    assert.equal(duringExit.cards.length, 1);
    assert.equal(duringExit.cards[0].id, "sig-1");
  });

  it("keeps focus on a useful empty state when the last card leaves", () => {
    const empty = reduceTodayList({ cards: [pending], focusId: "sig-1" }, { type: "remove", id: "sig-1" });
    assert.deepEqual(empty.cards, []);
    assert.equal(empty.focusId, TODAY_EMPTY_FOCUS);
  });

  it("does not extend the undo deadline while the card is leaving", () => {
    const leaving = presentExit({ ...pending, undoDeadline: "2026-09-22T10:00:05Z" }, true);
    assert.equal(leaving.undoDeadline, "2026-09-22T10:00:05Z");
    assert.equal(leaving.motion.transform, false);
    assert.equal(leaving.motion.height, false);
    const markup = renderToString(renderTodayCard(leaving, { now: Date.parse("2026-09-22T10:00:06Z") }));
    assert.equal(markup.includes("Deshacer"), false);
    const css = readFileSync(new URL("./vocify-ui.css", import.meta.url), "utf8");
    const reducedLine = css.split("\n").find((line) => line.includes(".v-today-card.is-leaving") && line.includes("opacity 180ms ease;"));
    assert.equal(reducedLine.includes("transform"), false);
  });
});
