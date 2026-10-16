import { describe, expect, it } from "vitest";
import { typingPlacement } from "./typing-bubbles";

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
