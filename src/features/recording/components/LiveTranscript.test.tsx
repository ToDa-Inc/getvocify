// @vitest-environment node
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LiveTranscript } from "./LiveTranscript";
import type { MeetingDisplayTurn } from "@/lib/meeting-transcript";

const turn = (speaker: "rep" | "prospect", text: string, pending = ""): MeetingDisplayTurn =>
  ({ key: `${speaker}-${text}`, speaker, label: speaker === "rep" ? "" : "Them", text, pending }) as unknown as MeetingDisplayTurn;

const render = (turns: MeetingDisplayTurn[], speaking?: { rep?: boolean; prospect?: boolean }, isActive = true) =>
  renderToStaticMarkup(createElement(LiveTranscript, { finalTranscript: "", interimTranscript: "", turns, speaking, isActive }));

const bubbles = (html: string) => (html.match(/aria-label="Speaking"/g) ?? []).length;

describe("LiveTranscript typing bubbles", () => {
  it("shows none when nobody is speaking", () => {
    expect(bubbles(render([turn("prospect", "Hola")], { rep: false, prospect: false }))).toBe(0);
    expect(bubbles(render([turn("prospect", "Hola")]))).toBe(0);
  });

  it("shows one under the last turn while its speaker talks", () => {
    expect(bubbles(render([turn("prospect", "Hola")], { prospect: true }))).toBe(1);
  });

  it("shows the other side's bubble in its own row", () => {
    expect(bubbles(render([turn("prospect", "Hola")], { rep: true }))).toBe(1);
  });

  it("shows a bubble before anything has been said", () => {
    const html = render([], { prospect: true });
    expect(bubbles(html)).toBe(1);
    expect(html).not.toContain("Listening");
  });

  it("does not double up with the bubble of words still settling", () => {
    expect(bubbles(render([turn("prospect", "Hola", "qué")], { prospect: true }))).toBe(1);
  });

  it("shows none once the call is not live", () => {
    expect(bubbles(render([turn("prospect", "Hola")], { prospect: true }, false))).toBe(0);
  });
});

describe("LiveTranscript during a long call", () => {
  const many = (n: number): MeetingDisplayTurn[] =>
    Array.from({ length: n }, (_, i) => ({ key: `t${i}`, speaker: i % 2 ? "prospect" : "rep", text: `line ${i}` }) as MeetingDisplayTurn);
  it("draws only the latest lines while live, and says how many are earlier", () => {
    const html = renderToStaticMarkup(createElement(LiveTranscript, { finalTranscript: "", interimTranscript: "", turns: many(300), isActive: true }));
    expect(html).toContain("260 earlier");
    expect(html).not.toContain("line 259<");
    expect(html).toContain("line 299");
  });
  it("draws every line once the call is over", () => {
    const html = renderToStaticMarkup(createElement(LiveTranscript, { finalTranscript: "", interimTranscript: "", turns: many(300), isActive: false }));
    expect(html).not.toContain("earlier");
    expect(html).toContain("line 0");
  });
});
