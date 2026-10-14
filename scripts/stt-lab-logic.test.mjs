import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  analyzeUtterances,
  apiBaseFor,
  autoThresholdDb,
  detectUtterances,
  isTokenFresh,
  tokenExpiryMs,
  displayTimeline,
  levelDb,
  percentiles,
  revisedWords,
  summarize,
  textAt,
  userIdFromJwt,
  wordCount,
} from "../public/dev/stt-lab-logic.js";

// Frames of 20 ms: loud from `from` to `to` (ms), quiet elsewhere.
function frames(spans, totalMs = 20_000) {
  const out = [];
  for (let t = 0; t < totalMs; t += 20) {
    const loud = spans.some(([from, to]) => t >= from && t < to);
    out.push({ t, db: loud ? -20 : -80 });
  }
  return out;
}

describe("where the voice stops", () => {
  it("an utterance ends at its last loud frame, not at the quiet gap that confirms it", () => {
    const found = detectUtterances(frames([[1000, 3000]]));
    assert.deepEqual(found, [{ start: 1000, end: 3000 }]);
  });

  it("a short breath inside a sentence does not split it, a real gap does", () => {
    const found = detectUtterances(frames([[1000, 2000], [2400, 3000], [5000, 6000]]), { gapMs: 800 });
    assert.deepEqual(found, [{ start: 1000, end: 3000 }, { start: 5000, end: 6000 }]);
  });

  it("quiet audio is silence at any threshold above its level", () => {
    assert.deepEqual(detectUtterances(frames([])), []);
    assert.equal(levelDb(new Float32Array(100)), -120);
    assert.ok(Math.abs(levelDb(new Float32Array(100).fill(0.1)) - -20) < 0.01);
  });
});

describe("how the words arrive after the voice stops", () => {
  // The voice runs 1000-3000 ms. Of 6 words, 2 arrive while speaking, 3 more 400 ms after it stops, the last one
  // at +1300 ms (partial), and the settled version at +2100 ms.
  const events = [
    { t: 1800, final: false, text: "me parece" },
    { t: 3400, final: false, text: "me parece muy caro la" },
    { t: 4300, final: false, text: "me parece muy caro la verdad" },
    { t: 5100, final: true, text: "me parece muy caro la verdad." },
  ];
  const timeline = displayTimeline(events);
  const utterances = detectUtterances(frames([[1000, 3000]]));
  const [row] = analyzeUtterances(utterances, timeline);

  it("measures from the moment the voice stopped", () => {
    assert.equal(row.endedAtMs, 3000);
    assert.equal(row.spokeMs, 2000);
    assert.equal(row.firstChangeMs, 400);
    assert.equal(row.lastChangeMs, 2100);
    assert.equal(row.lastSettledMs, 2100);
  });

  it("counts the words that were still missing when the voice stopped", () => {
    assert.equal(row.words, 6);
    assert.equal(row.wordsMissingAtEnd, 4);
  });

  it("says how much of the sentence a check at each pause length would have seen", () => {
    // At +300 ms only "me parece" was there (2 of 6 words); at +1000 ms 5 of 6; from +1500 ms all 6.
    assert.equal(row.completePctAt[300], 33);
    assert.equal(row.completePctAt[600], 83);
    assert.equal(row.completePctAt[1000], 83);
    assert.equal(row.completePctAt[1500], 100);
    assert.equal(row.completePctAt[2500], 100);
  });

  it("reads the text back without the earlier sentences", () => {
    assert.equal(row.text, "me parece muy caro la verdad.");
  });
});

describe("two sentences in a row", () => {
  it("the second is measured on its own words and the first stops at the second's start", () => {
    const events = [
      { t: 2200, final: true, text: "hola buenas." },
      { t: 6300, final: false, text: "mándame un email" },
      { t: 7000, final: true, text: "mándame un email." },
    ];
    const timeline = displayTimeline(events);
    const rows = analyzeUtterances(detectUtterances(frames([[1000, 2000], [6000, 6200]])), timeline);
    assert.equal(rows.length, 2);
    assert.equal(rows[0].words, 2);
    assert.equal(rows[0].lastSettledMs, 200);
    assert.equal(rows[1].words, 3);
    assert.equal(rows[1].text, "mándame un email.");
    assert.equal(rows[1].firstChangeMs, 100);
  });

  it("a voice that produced no words is not counted", () => {
    const rows = analyzeUtterances(detectUtterances(frames([[1000, 1500]])), displayTimeline([]));
    assert.equal(rows[0].words, 0);
    assert.equal(summarize(rows).utterances, 0);
    assert.equal(summarize(rows).lastChangeMs, null);
  });
});

describe("the display timeline", () => {
  it("settled pieces add up and the partial is only the still-changing end", () => {
    const timeline = displayTimeline([
      { t: 100, final: false, text: "hola me" },
      { t: 200, final: true, text: "hola" },
      { t: 210, final: false, text: "me parece" },
      { t: 400, final: true, text: "me parece caro" },
    ]);
    assert.equal(textAt(timeline, 150), "hola me");
    assert.equal(textAt(timeline, 205), "hola");
    assert.equal(textAt(timeline, 300), "hola me parece");
    assert.equal(textAt(timeline, 500), "hola me parece caro");
    assert.equal(wordCount("  a  b "), 2);
  });
});

describe("the small helpers", () => {
  it("percentiles skip nulls", () => {
    assert.deepEqual(percentiles([null, 100, 300, 200]), { min: 100, p50: 200, p90: 300, max: 300, n: 3 });
    assert.equal(percentiles([null]), null);
  });

  it("reads the user id from a token and picks the API the app would", () => {
    const payload = Buffer.from(JSON.stringify({ sub: "user-1" })).toString("base64url");
    assert.equal(userIdFromJwt(`x.${payload}.y`), "user-1");
    assert.equal(userIdFromJwt("not a token"), null);
    assert.match(apiBaseFor("staging.getvocify.com"), /getvocify-staging/);
    assert.match(apiBaseFor("app.getvocify.com"), /^https:\/\/api\.getvocify\.com/);
    assert.match(apiBaseFor("localhost"), /localhost:8888/);
  });
});

describe("the automatic voice threshold", () => {
  const room = (db, speech, n = 200) => Array.from({ length: n }, (_, i) => ({ t: i * 20, db: i % 5 === 0 ? speech : db }));

  it("sits a little above the room noise, so a quiet microphone still counts as speech", () => {
    // Noise at -62 dBFS, quiet speech at -48: a fixed -42 would never hear it.
    const quiet = room(-62, -48);
    const threshold = autoThresholdDb(quiet);
    assert.equal(threshold, -50);
    assert.equal(detectUtterances(quiet, { thresholdDb: -42 }).length, 0);
    assert.ok(detectUtterances(quiet, { thresholdDb: threshold }).length > 0);
  });

  it("stays inside -60..-30 and has a default before there is audio", () => {
    assert.equal(autoThresholdDb(room(-120, -20)), -60);
    assert.equal(autoThresholdDb(room(-30, -10)), -30);
    assert.equal(autoThresholdDb([]), -45);
  });
});

describe("the sign-in token", () => {
  const token = (exp) => `h.${Buffer.from(JSON.stringify({ sub: "u", exp })).toString("base64url")}.s`;
  const now = Date.UTC(2026, 9, 14, 16, 0, 0);

  it("is fresh while more than a minute is left, as in the app", () => {
    assert.equal(tokenExpiryMs(token(now / 1000 + 3600)), now + 3_600_000);
    assert.equal(isTokenFresh(token(now / 1000 + 3600), now), true);
    assert.equal(isTokenFresh(token(now / 1000 + 30), now), false);
    assert.equal(isTokenFresh(token(now / 1000 - 5), now), false);
  });

  it("is not fresh when it cannot be read", () => {
    assert.equal(isTokenFresh("not a token", now), false);
    assert.equal(isTokenFresh(`h.${Buffer.from(JSON.stringify({ sub: "u" })).toString("base64url")}.s`, now), false);
  });
});

describe("words that change after a check would have read them", () => {
  it("counts the early words that are not in the final text, each final word matched once", () => {
    assert.equal(revisedWords("me parece muy claro", "me parece muy caro la verdad."), 1);
    assert.equal(revisedWords("me parece", "me parece muy caro la verdad."), 0);
    assert.equal(revisedWords("caro caro", "es muy caro"), 1);
    assert.equal(revisedWords("", "hola"), 0);
  });

  it("the analysis keeps the text seen at each checkpoint and how much of it was revised", () => {
    const events = [
      { t: 3100, final: false, text: "me parece muy claro" },
      { t: 4000, final: true, text: "me parece muy caro la verdad." },
    ];
    const [row] = analyzeUtterances(detectUtterances(frames([[1000, 3000]])), displayTimeline(events));
    assert.equal(row.textSeenAt[300], "me parece muy claro");
    assert.equal(row.revisedWordsAt[300], 1);
    assert.equal(row.revisedWordsAt[1500], 0);
    assert.equal(summarize([row]).revisedWordsAt300.p50, 1);
  });
});
