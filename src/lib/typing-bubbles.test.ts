import { describe, expect, it } from "vitest";
import { WAITING_WORDS, overlayWithSpeaking, typingPlacement } from "./typing-bubbles";

describe("typingPlacement", () => {
  it("shows nothing while nobody is speaking", () => {
    expect(typingPlacement([{ speaker: "prospect" }], {})).toEqual({ insideLast: false, extra: [] });
  });

  it("puts the bubble under the last turn when its speaker is talking and no words are settling there", () => {
    expect(typingPlacement([{ speaker: "rep" }, { speaker: "prospect" }], { prospect: true })).toEqual({ insideLast: true, extra: [] });
  });

  it("leaves a turn whose words are still settling to its own bubble", () => {
    expect(typingPlacement([{ speaker: "prospect", pending: "no sé" }], { prospect: true })).toEqual({ insideLast: false, extra: [] });
  });

  it("gives a side with no turn at the end its own row, before anything has been said too", () => {
    expect(typingPlacement([{ speaker: "rep" }], { prospect: true })).toEqual({ insideLast: false, extra: ["prospect"] });
    expect(typingPlacement([], { rep: true })).toEqual({ insideLast: false, extra: ["rep"] });
  });

  it("handles both talking at once: the last turn's speaker inside, the other after it", () => {
    expect(typingPlacement([{ speaker: "rep" }], { rep: true, prospect: true })).toEqual({ insideLast: true, extra: ["prospect"] });
  });
});

describe("overlayWithSpeaking (the island)", () => {
  const turn = (you: boolean, text: string, pending = "") => ({ key: `${you}-${text}`, you, label: you ? null : "Ana", text, pending });

  it("changes nothing while nobody is speaking", () => {
    const turns = [turn(false, "Hola")];
    expect(overlayWithSpeaking(turns, {}, "Ana")).toBe(turns);
  });

  it("marks the last turn as waiting for words when its speaker talks", () => {
    const out = overlayWithSpeaking([turn(true, "Hola"), turn(false, "Dime")], { prospect: true }, "Ana");
    expect(out.map((t) => t.pending)).toEqual(["", WAITING_WORDS]);
  });

  it("adds a waiting turn for a speaker with no turn at the end, named like the prospect, and one before anything is said", () => {
    expect(overlayWithSpeaking([turn(true, "Hola")], { prospect: true }, "Ana")).toEqual([
      turn(true, "Hola"),
      { key: "speaking-prospect", you: false, label: "Ana", text: "", pending: WAITING_WORDS },
    ]);
    expect(overlayWithSpeaking([], { rep: true }, null)).toEqual([{ key: "speaking-rep", you: true, label: null, text: "", pending: WAITING_WORDS }]);
  });

  it("leaves words that are already settling alone, and never shows text (a no-break space trims away)", () => {
    const turns = [turn(false, "Dime", "algo")];
    expect(overlayWithSpeaking(turns, { prospect: true }, "Ana")).toBe(turns);
    expect(WAITING_WORDS.trim()).toBe("");
  });
});
