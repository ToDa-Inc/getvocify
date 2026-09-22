import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { askChoices, choiceFollowUp, showAskChoices, viewForFollowUp } from "./ask-choices.ts";
import { emptyAsk } from "./ask-turn.ts";

describe("ask choices", () => {
  it("keeps both labels when the turn has two choices", () => {
    const rows = askChoices({
      choices: [
        { id: "c1", label: "Marina López" },
        { id: "c2", label: "Marina Ruiz" },
      ],
    });
    assert.deepEqual(rows.map((row) => row.label), ["Marina López", "Marina Ruiz"]);
  });

  it("has no choices when the turn omits the key", () => {
    assert.deepEqual(askChoices({}), []);
    assert.equal(showAskChoices({ ...emptyAsk(), status: "completed", turnId: "t1" }, []), false);
  });

  it("sends the choice id to the copilot when present", () => {
    assert.equal(
      choiceFollowUp({ id: "pick:contact:42", label: "Marina" }),
      "pick:contact:42",
    );
    assert.equal(choiceFollowUp({ id: "", label: "Marina Ruiz" }), "Marina Ruiz");
  });

  it("drops choices missing id or label", () => {
    assert.deepEqual(
      askChoices({
        choices: [
          { id: "", label: "Marina" },
          { id: "c1", label: "" },
          { id: "c2", label: "Ok" },
        ],
      }),
      [{ id: "c2", label: "Ok" }],
    );
  });

  it("clears the turn id before a follow-up message", () => {
    const ready = viewForFollowUp({
      ...emptyAsk(),
      turnId: "turn-1",
      status: "completed",
      text: "¿Cuál Marina?",
      posts: 2,
    });
    assert.equal(ready.turnId, null);
    assert.equal(ready.posts, 2);
  });
});
