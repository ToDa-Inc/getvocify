import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { closeAskPanel, emptyAsk, notePosted, noteTick, reopenAsk } from "./ask-turn.ts";

describe("ask turn polling", () => {
  it("waits past 30s without posting again", () => {
    const posted = notePosted(emptyAsk(), {
      turnId: "turn-2",
      status: "pending",
      text: "¿Qué sigue?",
    });
    assert.equal(posted.posts, 1);
    assert.equal(posted.notice, "Esperando respuesta");
    const again = notePosted(posted, {
      turnId: "turn-9",
      status: "pending",
      text: "otro",
    });
    assert.equal(again.posts, 1);
    assert.equal(again.turnId, "turn-2");
    const waited = noteTick(posted, 31000, null, false);
    assert.equal(waited.posts, 1);
    assert.equal(waited.turnId, "turn-2");
    assert.match(waited.notice || "", /No se ha reenviado/);
  });

  it("reopens the same turn and does not scroll the reader", () => {
    const restored = reopenAsk("turn-2", {
      turnId: "turn-2",
      status: "completed",
      text: "Marina queda para el jueves.",
    });
    assert.equal(restored.turnId, "turn-2");
    assert.equal(restored.text, "Marina queda para el jueves.");
    assert.equal(restored.posts, 0);
    const reading = noteTick(
      notePosted(emptyAsk(), { turnId: "turn-2", status: "pending", text: "¿Qué sigue?" }),
      1000,
      { turnId: "turn-2", status: "completed", text: "Marina queda para el jueves." },
      true,
    );
    assert.equal(reading.scroll, false);
    assert.equal(reading.unread, true);
  });

  it("a failed poll and a late answer keep one post and the final text", () => {
    const posted = notePosted(emptyAsk(), {
      turnId: "turn-2",
      status: "pending",
      text: "¿Qué sigue?",
    });
    const failed = noteTick(posted, 2000, null, false);
    assert.equal(failed.posts, 1);
    assert.equal(failed.text, "¿Qué sigue?");
    const late = noteTick(
      failed,
      2000,
      { turnId: "turn-2", status: "completed", text: "Marina queda para el jueves." },
      false,
    );
    assert.equal(late.posts, 1);
    assert.equal(late.text, "Marina queda para el jueves.");
  });

  it("closing the panel returns focus without scrolling the thread", () => {
    const reading = noteTick(
      notePosted(emptyAsk(), { turnId: "turn-2", status: "pending", text: "¿Qué sigue?" }),
      1000,
      null,
      true,
    );
    const closed = closeAskPanel(reading, "ask-open");
    assert.equal(closed.focusId, "ask-open");
    assert.equal(closed.view.scroll, false);
    assert.equal(closed.view.unread, reading.unread);
  });
});
