import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  HOS_PERIODS,
  adherenceParams,
  countDelta,
  processHealthView,
  summaryDiagnosis,
  flowShortName,
  rateDelta,
  repActivityCsv,
  repActivityRows,
  shareOf,
  teamActivityFooter,
  type ProcessHealthFlow,
} from "./head-of-sales.ts";

const ES = productCatalog.ES;
const EN = productCatalog.EN;

describe("adherenceParams", () => {
  it("a manager always sends the period, and the role only when narrowed", () => {
    assert.equal(
      adherenceParams({ manager: true, period: "month", salesRole: "all", userId: null, motion: null }),
      "period=month",
    );
    assert.equal(
      adherenceParams({ manager: true, period: "week", salesRole: "sdr", userId: "u1", motion: "discovery" }),
      "user_id=u1&motion=discovery&period=week&sales_role=sdr",
    );
  });

  it("a member with team visibility sends exactly what it sent before phase 2", () => {
    assert.equal(
      adherenceParams({ manager: false, period: "month", salesRole: "sdr", userId: null, motion: null }),
      "",
    );
    assert.equal(
      adherenceParams({ manager: false, period: "month", salesRole: "sdr", userId: "u1", motion: null }),
      "user_id=u1",
    );
  });
});

describe("deltas", () => {
  it("counts compare in percent, and a start from zero is 'new'", () => {
    assert.deepEqual(countDelta(12, 10), { text: "+20%", direction: "up" });
    assert.deepEqual(countDelta(5, 10), { text: "-50%", direction: "down" });
    assert.deepEqual(countDelta(3, 0), { text: "new", direction: "up" });
    assert.equal(countDelta(0, 0), null);
    assert.equal(countDelta(null, 4), null);
  });

  it("rates compare in points, never in percent of a percent", () => {
    assert.deepEqual(rateDelta(0.5, 0.42), { text: "+8 pts", direction: "up" });
    assert.deepEqual(rateDelta(0.3, 0.3), { text: "0 pts", direction: "flat" });
    // Same size of change either way: -22.5 pts is "-23", like +22.5 is "+23".
    assert.deepEqual(rateDelta(0.675, 0.9), { text: "-23 pts", direction: "down" });
    assert.deepEqual(rateDelta(0.9, 0.675), { text: "+23 pts", direction: "up" });
    assert.equal(rateDelta(null, 0.3), null);
  });
});

describe("shareOf", () => {
  it("is null without a denominator", () => {
    assert.equal(shareOf(0, 0), null);
    assert.equal(shareOf(1, 4), 0.25);
  });
});

const reps = [
  { userId: "b", name: "Carlos", salesRole: "sdr", activity: { attempts: 40, connected: 4, meetings: 1 } },
  { userId: "a", name: "Ana", salesRole: "ae", activity: { attempts: 10, connected: 5, meetings: 2 } },
  { userId: "c", name: "Dani", activity: { attempts: 0, connected: 0, meetings: 0 } },
];

describe("repActivityRows", () => {
  it("keeps alphabetical order (no ranking) and derives the connection rate", () => {
    const rows = repActivityRows(reps);
    assert.deepEqual(rows.map((r) => r.name), ["Ana", "Carlos", "Dani"]);
    assert.equal(rows[1].connectionRate, 0.1);
    assert.equal(rows[2].connectionRate, null);
  });
});

describe("teamActivityFooter", () => {
  it("median only over people with activity; total over everyone", () => {
    const { median, total } = teamActivityFooter(repActivityRows(reps));
    assert.equal(median.people, 2);
    assert.equal(median.attempts, 25);
    assert.equal(median.meetings, 1.5);
    assert.equal(total.attempts, 50);
    assert.equal(total.connectionRate, 9 / 50);
  });
});

describe("repActivityCsv", () => {
  it("escapes names and leaves empty rates empty", () => {
    const csv = repActivityCsv(
      repActivityRows([{ userId: "x", name: 'Ana "La" Ruiz, SL', activity: { attempts: 0, connected: 0, meetings: 0 } }]),
      EN,
    );
    const [, line] = csv.split("\n");
    assert.equal(line, '"Ana ""La"" Ruiz, SL",,0,0,,0');
  });
});

const flow = (over: Partial<ProcessHealthFlow>): ProcessHealthFlow => ({
  motion: "discovery",
  goal: "meeting_booked",
  scored: 30,
  verdict: "playbook_underperforms",
  matrix: { follows_goal: 1, follows_no_goal: 9, deviates_goal: 4, deviates_no_goal: 6 },
  follow_share: 0.5,
  follows_goal_rate: 0.1,
  deviates_goal_rate: 0.4,
  needed: 0,
  ...over,
});

describe("processHealthView", () => {
  it("every verdict has copy in both languages", () => {
    const verdicts: ProcessHealthFlow["verdict"][] = [
      "playbook_underperforms",
      "coach_reps",
      "playbook_works",
      "no_difference",
      "no_comparison",
      "insufficient_data",
      "goal_not_measurable",
    ];
    for (const copy of [ES, EN]) {
      for (const verdict of verdicts) {
        const view = processHealthView(flow({ verdict, needed: 4 }), copy);
        assert.ok(view.title.length > 0, `${verdict} title`);
        assert.ok(!view.detail.includes("{"), `${verdict} detail placeholders filled: ${view.detail}`);
      }
    }
  });

  it("a playbook problem names both rates and points at the playbook", () => {
    const view = processHealthView(flow({}), ES);
    assert.equal(view.tone, "process");
    assert.match(view.detail, /10%/);
    assert.match(view.detail, /40%/);
  });

  it("a rep problem is tone rep; not enough data says how many are missing", () => {
    assert.equal(processHealthView(flow({ verdict: "coach_reps" }), ES).tone, "rep");
    assert.match(processHealthView(flow({ verdict: "insufficient_data", needed: 7 }), ES).detail, /7/);
  });
});

describe("HOS_PERIODS", () => {
  it("has copy for every preset", () => {
    for (const copy of [ES, EN]) {
      for (const period of HOS_PERIODS) assert.ok(copy[period.labelKey]);
    }
  });
});

describe("summaryDiagnosis", () => {
  const f = (verdict: ProcessHealthFlow["verdict"], motion = "discovery") => flow({ verdict, motion });

  it("no activity says so before anything else", () => {
    assert.equal(summaryDiagnosis({ attempts: 0, adherence: 0.8, processHealth: [f("playbook_underperforms")] }).key, "hosDiagNoActivity");
  });

  it("a playbook problem wins over a coaching one and links to the process", () => {
    const d = summaryDiagnosis({ attempts: 10, adherence: 0.5, processHealth: [f("coach_reps", "closing"), f("playbook_underperforms")] });
    assert.deepEqual(d, { tone: "process", key: "hosDiagPlaybook", motion: "discovery", href: "/dashboard/process" });
  });

  it("coaching links to the team", () => {
    const d = summaryDiagnosis({ attempts: 10, adherence: 0.5, processHealth: [f("coach_reps")] });
    assert.equal(d.key, "hosDiagCoach");
    assert.equal(d.href, "/dashboard/insights");
  });

  it("without scored calls it asks for the process", () => {
    assert.equal(summaryDiagnosis({ attempts: 10, adherence: null, processHealth: [] }).key, "hosDiagNoProcess");
  });

  it("not enough data is 'collecting', a working playbook is ok", () => {
    assert.equal(summaryDiagnosis({ attempts: 10, adherence: 0.7, processHealth: [f("insufficient_data")] }).key, "hosDiagCollecting");
    assert.equal(summaryDiagnosis({ attempts: 10, adherence: 0.7, processHealth: [f("playbook_works")] }).tone, "ok");
  });

  it("every diagnosis has copy in both languages", () => {
    for (const copy of [ES, EN]) {
      for (const key of ["hosDiagNoActivity", "hosDiagPlaybook", "hosDiagPlaybookNoEffect", "hosDiagCoach", "hosDiagNoProcess", "hosDiagWorks", "hosDiagCollecting"] as const) {
        assert.ok(copy[key], key);
      }
    }
  });
});

describe("flowShortName", () => {
  it("names the role flows by role and anything else by its label", () => {
    assert.equal(flowShortName("discovery", "Flujo SDR"), "SDR");
    assert.equal(flowShortName("closing", "Flujo AE"), "AE");
    assert.equal(flowShortName("qualification", "Cualificación"), "Cualificación");
  });
});
