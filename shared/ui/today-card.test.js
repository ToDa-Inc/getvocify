import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  dropLeaving,
  exitMotion,
  presentExit,
  reduceTodayList,
  renderTodayCard,
  retainLeaving,
  settleRowHeights,
  TODAY_EMPTY_FOCUS,
} from "./today-card.js";
import { renderToString } from "./html.js";
import { strings } from "./i18n.js";

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

  it("shows Dismiss or Descartar from caller labels", () => {
    const en = strings("en");
    const es = strings("es");
    const enMarkup = renderToString(
      renderTodayCard(pending, { now: 0, dismiss: en.dismiss, undo: en.undo }),
    );
    assert.match(enMarkup, />Dismiss</);
    const esMarkup = renderToString(
      renderTodayCard(pending, { now: 0, dismiss: es.dismiss, undo: es.undo }),
    );
    assert.match(esMarkup, />Descartar</);
  });

  it("measures real height before a full-motion exit", () => {
    assert.equal(exitMotion(false).measureHeight, true);
    assert.equal(exitMotion(true).measureHeight, undefined);
  });

  it("does not extend the undo deadline while the card is leaving", () => {
    const leaving = presentExit({ ...pending, undoDeadline: "2026-09-22T10:00:05Z" }, true);
    assert.equal(leaving.undoDeadline, "2026-09-22T10:00:05Z");
    assert.equal(leaving.motion.transform, false);
    assert.equal(leaving.motion.height, false);
    const es = strings("es");
    const markup = renderToString(
      renderTodayCard(leaving, {
        now: Date.parse("2026-09-22T10:00:06Z"),
        dismiss: es.dismiss,
        undo: es.undo,
      }),
    );
    assert.equal(markup.includes(es.undo), false);
    const css = readFileSync(new URL("./vocify-ui.css", import.meta.url), "utf8");
    const reducedLine = css.split("\n").find((line) => line.includes(".v-today-card.is-leaving") && line.includes("opacity 180ms ease;"));
    assert.equal(reducedLine.includes("transform"), false);
  });
});

describe("rows leaving the home", () => {
  const keyOf = (entry) => entry.id;
  const rows = (...ids) => ids.map((id) => ({ entry: { id }, leaving: false }));
  const shape = (list) => list.map((row) => `${row.entry.id}${row.leaving ? "~" : ""}`);

  it("keeps a row that vanished on refresh in its old place while it fades out", () => {
    const next = retainLeaving(rows("a", "b", "c"), [{ id: "a" }, { id: "c" }, { id: "d" }], keyOf);
    assert.deepEqual(shape(next), ["a", "b~", "c", "d"]);
  });

  it("keeps the order of several rows leaving at once, at the start and at the end", () => {
    const next = retainLeaving(rows("a", "b", "c", "d"), [{ id: "b" }, { id: "c" }], keyOf);
    assert.deepEqual(shape(next), ["a~", "b", "c", "d~"]);
    assert.deepEqual(shape(retainLeaving(rows("a", "b"), [], keyOf)), ["a~", "b~"]);
  });

  it("keeps a leaving row until it is dropped, and brings it back if it returns", () => {
    const leaving = retainLeaving(rows("a", "b"), [{ id: "a" }], keyOf);
    const again = retainLeaving(leaving, [{ id: "a" }], keyOf);
    assert.deepEqual(shape(again), ["a", "b~"]);
    assert.deepEqual(shape(dropLeaving(again, "b", keyOf)), ["a"]);
    assert.deepEqual(shape(retainLeaving(again, [{ id: "a" }, { id: "b" }], keyOf)), ["a", "b"]);
  });

  it("shows the newest data for rows that stay", () => {
    const next = retainLeaving([{ entry: { id: "a", v: 1 }, leaving: false }], [{ id: "a", v: 2 }], keyOf);
    assert.deepEqual(next, [{ entry: { id: "a", v: 2 }, leaving: false }]);
  });

  it("collapses a resolved card to its measured height, or only fades with reduced motion", () => {
    assert.deepEqual(exitMotion(false), { opacity: true, transform: true, height: true, measureHeight: true });
    assert.deepEqual(exitMotion(true), { opacity: true, transform: false, height: false });
  });

  it("keeps the resolved undo row visible when the card settles", () => {
    const plan = settleRowHeights(120, 44, false);
    assert.equal(plan.animate, true);
    assert.equal(plan.toHeight, 44);
    assert.notEqual(plan.toHeight, 0);
    assert.equal(settleRowHeights(120, 44, true).animate, false);
  });
});
