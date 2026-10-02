import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { Diagnosis } from "./head-of-sales.ts";
import type { TrendPayload, TrendWeek } from "./team-adherence-trend.ts";
import { DROP_POINTS, MAX_SIGNALS, MIN_SCORED, signalReps, teamSignals, type SignalRep } from "./team-signals.ts";

function rep(overrides: Partial<SignalRep> & { name: string }): SignalRep {
  return {
    userId: overrides.name.toLowerCase(),
    adherence: 0.7,
    prevAdherence: 0.7,
    scored: 40,
    prevScored: 40,
    attempts: 50,
    ...overrides,
  };
}

const coach: Diagnosis = { tone: "rep", key: "hosDiagCoach", motion: "discovery", href: "/dashboard/insights?tab=people" };
const playbook: Diagnosis = { tone: "process", key: "hosDiagPlaybook", motion: "closing", href: "/dashboard/process" };

describe("teamSignals", () => {
  it("returns nothing for an empty team", () => {
    assert.deepEqual(teamSignals({ reps: [], diagnosis: [] }), []);
  });

  it("fires the drop rule at exactly 15 points and not at 14", () => {
    assert.equal(DROP_POINTS, 15);
    const fifteen = teamSignals({ reps: [rep({ name: "Ana", prevAdherence: 0.7, adherence: 0.55 })], diagnosis: [] });
    assert.equal(fifteen.length, 1);
    assert.equal(fifteen[0].id, "drop:ana");
    assert.equal(fifteen[0].tone, "warn");
    assert.deepEqual(fifteen[0].params, { name: "Ana", points: 15, from: 70, to: 55 });
    const fourteen = teamSignals({ reps: [rep({ name: "Ana", prevAdherence: 0.7, adherence: 0.56 })], diagnosis: [] });
    assert.deepEqual(fourteen, []);
  });

  it("needs 30 scored calls in both periods before a drop counts", () => {
    assert.equal(MIN_SCORED, 30);
    const dropped = { prevAdherence: 0.9, adherence: 0.5 };
    const fire = (scored: number, prevScored: number) =>
      teamSignals({ reps: [rep({ name: "Ana", ...dropped, scored, prevScored })], diagnosis: [] }).length;
    assert.equal(fire(30, 30), 1);
    assert.equal(fire(29, 30), 0);
    assert.equal(fire(30, 29), 0);
  });

  it("never fires the drop rule when either adherence is unknown", () => {
    const unknown = teamSignals({
      reps: [rep({ name: "Ana", adherence: null, prevAdherence: 0.9 }), rep({ name: "Bea", adherence: 0.1, prevAdherence: null })],
      diagnosis: [],
    });
    assert.deepEqual(unknown, []);
  });

  it("names a rep with no attempts", () => {
    const out = teamSignals({ reps: [rep({ name: "Ana", attempts: 0 })], diagnosis: [] });
    assert.deepEqual(out.map((signal) => [signal.id, signal.tone, signal.textKey, signal.params.name]), [["idle:ana", "neutral", "signalIdle", "Ana"]]);
  });

  it("turns process and coaching diagnosis lines into signals, and skips the ones that are not a problem", () => {
    const works: Diagnosis = { tone: "ok", key: "hosDiagWorks", motion: "discovery", href: null };
    const collecting: Diagnosis = { tone: "neutral", key: "hosDiagCollecting", motion: null, href: null };
    const out = teamSignals({ reps: [], diagnosis: [playbook, coach, works, collecting] });
    assert.deepEqual(
      out.map((signal) => [signal.id, signal.textKey, signal.params.flow]),
      [
        ["diag:hosDiagPlaybook:closing", "signalPlaybook", "closing"],
        ["diag:hosDiagCoach:discovery", "signalCoach", "discovery"],
      ],
    );
    assert.ok(out.every((signal) => signal.question.length > 0 && signal.question !== signal.textKey));
  });

  it("orders by rule, then by name - never by how far a score fell", () => {
    const out = teamSignals({
      reps: [
        rep({ name: "Zoe", attempts: 0 }),
        rep({ name: "Carla", prevAdherence: 0.9, adherence: 0.2 }),
        rep({ name: "Bruno", prevAdherence: 0.7, adherence: 0.5 }),
      ],
      diagnosis: [],
    });
    assert.deepEqual(out.map((signal) => signal.id), ["drop:bruno", "drop:carla", "idle:zoe"]);
  });

  it("caps at three, keeping the earlier rules", () => {
    assert.equal(MAX_SIGNALS, 3);
    const out = teamSignals({
      reps: [
        rep({ name: "Ana", attempts: 0 }),
        rep({ name: "Bea", prevAdherence: 0.9, adherence: 0.5 }),
        rep({ name: "Cris", prevAdherence: 0.9, adherence: 0.5 }),
      ],
      diagnosis: [coach],
    });
    assert.deepEqual(out.map((signal) => signal.id), ["diag:hosDiagCoach:discovery", "drop:bea", "drop:cris"]);
  });
});

function week(start: string, overrides: Partial<TrendWeek> = {}): TrendWeek {
  return {
    week_start: start,
    state: "gap",
    interactions: 0,
    scored: 0,
    without_playbook: 0,
    without_score: 0,
    met_steps: 0,
    missed_steps: 0,
    applicable_steps: 0,
    unknown_steps: 0,
    not_applicable_steps: 0,
    adherence: null,
    coverage: null,
    sample_limited: false,
    playbook_version_ids: [],
    new_playbook_version: false,
    ...overrides,
  };
}

const STARTS = ["08-03", "08-10", "08-17", "08-24", "08-31", "09-07", "09-14", "09-21"].map((day) => `2026-${day}`);

function trend(userId: string, perWeek: (index: number) => Partial<TrendWeek>): TrendPayload {
  return {
    coverage: "complete",
    timezone: "Europe/Madrid",
    weeks: STARTS.map((start, index) => ({ week_start: start, week_end: start, in_progress: index === STARTS.length - 1 })),
    team: null,
    reps: [{ user_id: userId, name: "", weeks: STARTS.map((start, index) => week(start, perWeek(index))) }],
  };
}

describe("signalReps", () => {
  it("sums the last four weeks against the four before, counts not percentages", () => {
    const payload = trend("u1", (index) =>
      index < 4
        ? { state: "scored", scored: 10, met_steps: 8, applicable_steps: 10 }
        : { state: "scored", scored: 8, met_steps: index === 7 ? 0 : 6, applicable_steps: index === 7 ? 10 : 10 },
    );
    const [out] = signalReps([{ userId: "u1", name: "Ana", activity: { attempts: 12, connected: 3, meetings: 1 } }], payload);
    assert.deepEqual(out, { userId: "u1", name: "Ana", attempts: 12, scored: 32, prevScored: 40, adherence: 18 / 40, prevAdherence: 0.8 });
  });

  it("leaves adherence unknown without a trend, without a row for the rep, or without applicable steps", () => {
    const reps = [
      { userId: "u1", name: "Ana" },
      { userId: "u2", name: "Bea", activity: { attempts: 0, connected: 0, meetings: 0 } },
    ];
    assert.deepEqual(signalReps(reps, null), [
      { userId: "u1", name: "Ana", attempts: 0, scored: 0, prevScored: 0, adherence: null, prevAdherence: null },
      { userId: "u2", name: "Bea", attempts: 0, scored: 0, prevScored: 0, adherence: null, prevAdherence: null },
    ]);
    const [first] = signalReps(reps, trend("u1", () => ({ state: "unscored", interactions: 2 })));
    assert.equal(first.adherence, null);
    assert.equal(first.prevAdherence, null);
  });
});
