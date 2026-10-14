// The maths of the STT lab (stt-lab.html): where an utterance ends in the audio, and how long the words take to
// arrive and finish after that. Plain functions on plain data, so they are tested without a microphone
// (scripts/stt-lab-logic.test.mjs).

/** Number of words in a text. */
export function wordCount(text) {
  const t = String(text || "").trim();
  return t ? t.split(/\s+/).length : 0;
}

/** dBFS of a Float32 frame's RMS (0 dB is full scale). Silence is -120. */
export function levelDb(samples) {
  if (!samples.length) return -120;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  const rms = Math.sqrt(sum / samples.length);
  return rms > 1e-6 ? 20 * Math.log10(rms) : -120;
}

/**
 * A voice threshold from the audio itself: a little above the room's noise (the quiet 20th percentile of all
 * frames), so a quiet microphone still counts as speech. Clamped to -60..-30 dBFS.
 */
export function autoThresholdDb(frames, { marginDb = 12 } = {}) {
  const dbs = frames.map((frame) => frame.db).sort((a, b) => a - b);
  if (dbs.length < 25) return -45;
  const floor = dbs[Math.floor(dbs.length * 0.2)];
  return Math.max(-60, Math.min(-30, Math.round(floor + marginDb)));
}

/**
 * Utterances from the audio frames [{t, db}] (t = ms when the frame reached the page, frameMs long):
 * speech starts at the first loud frame and ends at the last loud frame before a quiet gap of gapMs or more.
 * `end` is when the voice stopped, which is what live help calls the moment the prospect finished.
 */
export function detectUtterances(frames, { thresholdDb = -42, gapMs = 800, frameMs = 20 } = {}) {
  const out = [];
  let current = null;
  for (const frame of frames) {
    const loud = frame.db >= thresholdDb;
    if (loud) {
      if (current && frame.t - current.end > gapMs) {
        out.push(current);
        current = null;
      }
      if (!current) current = { start: frame.t, end: frame.t + frameMs };
      else current.end = frame.t + frameMs;
    }
  }
  if (current) out.push(current);
  return out;
}

/**
 * What the screen would show over time, from the service's messages [{t, final, text}]: settled pieces
 * add up, the partial is the still-changing end after them. Returns [{t, text, final}] (one per message
 * that changed the text).
 */
export function displayTimeline(events) {
  const settled = [];
  let partial = "";
  const out = [];
  let last = "";
  for (const event of events) {
    const text = String(event.text || "").trim();
    if (event.final) {
      if (text) settled.push(text);
      partial = "";
    } else {
      partial = text;
    }
    const shown = [...settled, partial].filter(Boolean).join(" ");
    if (shown !== last || event.final) {
      out.push({ t: event.t, text: shown, final: Boolean(event.final) });
      last = shown;
    }
  }
  return out;
}

/** The text on screen at time t. */
export function textAt(timeline, t) {
  let shown = "";
  for (const entry of timeline) {
    if (entry.t > t) break;
    shown = entry.text;
  }
  return shown;
}

export const CHECKPOINTS_MS = [300, 600, 1000, 1500, 2500];

/**
 * For each utterance: how long after the voice stopped the first new words showed, the last change, and the last
 * settled piece; how many words were still missing at the moment it stopped; and how much of the sentence was
 * on screen at each checkpoint after the end (300 ms is when live help counts a pause).
 */
export function analyzeUtterances(utterances, timeline, { tailMs = 6000 } = {}) {
  return utterances.map((u, i) => {
    const windowEnd = i + 1 < utterances.length ? utterances[i + 1].start : u.end + tailMs;
    const base = wordCount(textAt(timeline, u.start - 1));
    const total = wordCount(textAt(timeline, windowEnd)) - base;
    const atEnd = wordCount(textAt(timeline, u.end)) - base;
    const inWindow = timeline.filter((entry) => entry.t > u.end && entry.t <= windowEnd);
    const changesAfter = inWindow.filter((entry, k) => entry.text !== (k ? inWindow[k - 1].text : textAt(timeline, u.end)));
    const finalsAfter = inWindow.filter((entry) => entry.final);
    const shownText = textAt(timeline, windowEnd);
    const before = textAt(timeline, u.start - 1);
    const text = before && shownText.startsWith(before) ? shownText.slice(before.length).trim() : shownText;
    const complete = {};
    for (const ms of CHECKPOINTS_MS) {
      const words = wordCount(textAt(timeline, Math.min(u.end + ms, windowEnd))) - base;
      complete[ms] = total > 0 ? Math.round((Math.max(0, words) / total) * 100) : null;
    }
    return {
      index: i + 1,
      spokeMs: Math.round(u.end - u.start),
      endedAtMs: Math.round(u.end),
      words: total,
      wordsMissingAtEnd: Math.max(0, total - atEnd),
      firstChangeMs: changesAfter.length ? Math.round(changesAfter[0].t - u.end) : null,
      lastChangeMs: changesAfter.length ? Math.round(changesAfter[changesAfter.length - 1].t - u.end) : null,
      lastSettledMs: finalsAfter.length ? Math.round(finalsAfter[finalsAfter.length - 1].t - u.end) : null,
      completePctAt: complete,
      text,
    };
  });
}

/** p50 / p90 / max of the numbers in a list (nulls skipped), or null when there are none. */
export function percentiles(values) {
  const v = values.filter((x) => typeof x === "number").sort((a, b) => a - b);
  if (!v.length) return null;
  const at = (q) => v[Math.min(v.length - 1, Math.floor(q * v.length))];
  return { p50: at(0.5), p90: at(0.9), max: v[v.length - 1], n: v.length };
}

/** The numbers worth reading across all utterances. */
export function summarize(rows) {
  const usable = rows.filter((row) => row.words > 0);
  const complete = {};
  for (const ms of CHECKPOINTS_MS) complete[ms] = percentiles(usable.map((row) => row.completePctAt[ms]));
  return {
    utterances: usable.length,
    firstChangeMs: percentiles(usable.map((row) => row.firstChangeMs)),
    lastChangeMs: percentiles(usable.map((row) => row.lastChangeMs)),
    lastSettledMs: percentiles(usable.map((row) => row.lastSettledMs)),
    wordsMissingAtEnd: percentiles(usable.map((row) => row.wordsMissingAtEnd)),
    completePctAt: complete,
  };
}

/** The user id in a JWT (the `sub` claim), or null. */
export function userIdFromJwt(token) {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = typeof atob === "function" ? atob(payload) : Buffer.from(payload, "base64").toString("utf8");
    const sub = JSON.parse(json).sub;
    return typeof sub === "string" && sub ? sub : null;
  } catch {
    return null;
  }
}

/** When a JWT expires (ms since the epoch), or null (the `exp` claim). */
export function tokenExpiryMs(token) {
  try {
    const payload = String(token).split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = typeof atob === "function" ? atob(payload) : Buffer.from(payload, "base64").toString("utf8");
    const exp = JSON.parse(json).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/** The app's own rule (src/lib/auth-session.ts): fresh while more than a minute is left. */
export function isTokenFresh(token, nowMs = Date.now(), minTtlMs = 60_000) {
  const exp = tokenExpiryMs(token);
  return exp !== null && exp - nowMs > minTtlMs;
}

/** Where the API lives for the page's host, as the app itself chooses (src/lib/app-url.ts). */
export function apiBaseFor(hostname) {
  const host = String(hostname || "").toLowerCase();
  if (host === "staging.getvocify.com") return "https://getvocify-staging.up.railway.app/api/v1";
  if (host === "localhost" || host === "127.0.0.1") return "http://localhost:8888/api/v1";
  return "https://api.getvocify.com/api/v1";
}
