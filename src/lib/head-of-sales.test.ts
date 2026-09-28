import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  HOS_PERIODS,
  adherenceParams,
  countDelta,
  csvCell,
  hosOutcomes,
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
  it("asks for the coaching focus only when a manager requests it", () => {
    assert.equal(
      adherenceParams({ manager: true, period: "month", salesRole: "all", userId: null, motion: null, withFocus: true }),
      "period=month&with_focus=true",
    );
    assert.equal(
      adherenceParams({ manager: false, period: "month", salesRole: "all", userId: null, motion: null, withFocus: true }),
      "",
    );
  });

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

  it("passes coaching_focus through: undefined when not sent, null when there is none", () => {
    const rows = repActivityRows([
      { userId: "b", name: "Beto", coaching_focus: null },
      { userId: "a", name: "Ana", coaching_focus: { step_id: "open", label: "Apertura", rate: 0.2 } },
      { userId: "c", name: "Cris" },
    ]);
    assert.deepEqual(rows.map((r) => r.name), ["Ana", "Beto", "Cris"]);
    assert.equal(rows[0].focus?.label, "Apertura");
    assert.equal(rows[1].focus, null);
    assert.equal(rows[2].focus, undefined);
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
    assert.equal(line, '"Ana ""La"" Ruiz, SL",,0,0,,0,');
  });

  it("carries the focus label as the last column; no focus stays empty", () => {
    const withFocus = [
      { userId: "a", name: "Ana", coaching_focus: { step_id: "open", label: "Apertura, clara", rate: 0.2 } },
      { userId: "b", name: "Beto", coaching_focus: null },
    ];
    const csv = repActivityCsv(repActivityRows(withFocus), EN);
    const [header, ana, beto] = csv.split("\n");
    assert.ok(header.endsWith(",Focus (this week)"));
    assert.ok(ana.endsWith(',"Apertura, clara"'));
    assert.ok(beto.endsWith(",0,,0,"));
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
  const keys = (list: { key: string }[]) => list.map((d) => d.key);

  it("no activity says so before anything else", () => {
    assert.deepEqual(
      keys(summaryDiagnosis({ attempts: 0, adherence: 0.8, processHealth: [f("playbook_underperforms")] })),
      ["hosDiagNoActivity"],
    );
  });

  it("gives one line per flow, most severe first, so a second problem is not hidden", () => {
    const d = summaryDiagnosis({ attempts: 10, adherence: 0.5, processHealth: [f("coach_reps", "discovery"), f("playbook_underperforms", "closing")] });
    assert.deepEqual(d, [
      { tone: "process", key: "hosDiagPlaybook", motion: "closing", href: "/dashboard/process" },
      { tone: "rep", key: "hosDiagCoach", motion: "discovery", href: "/dashboard/insights" },
    ]);
  });

  it("same severity keeps SDR before AE; never more than two lines", () => {
    const d = summaryDiagnosis({
      attempts: 10,
      adherence: 0.5,
      processHealth: [f("coach_reps", "closing"), f("coach_reps", "discovery"), f("coach_reps", "qualification")],
    });
    assert.deepEqual(d.map((x) => x.motion), ["discovery", "closing"]);
  });

  it("a flow without a verdict adds no line", () => {
    const d = summaryDiagnosis({ attempts: 10, adherence: 0.5, processHealth: [f("coach_reps", "discovery"), f("insufficient_data", "closing")] });
    assert.deepEqual(keys(d), ["hosDiagCoach"]);
  });

  it("a working flow shows next to a problem in the other", () => {
    const d = summaryDiagnosis({ attempts: 10, adherence: 0.5, processHealth: [f("playbook_works", "discovery"), f("no_difference", "closing")] });
    assert.deepEqual(keys(d), ["hosDiagPlaybookNoEffect", "hosDiagWorks"]);
  });

  it("without scored calls it asks for the process", () => {
    assert.deepEqual(keys(summaryDiagnosis({ attempts: 10, adherence: null, processHealth: [] })), ["hosDiagNoProcess"]);
  });

  it("not enough data is 'collecting', a working playbook is ok", () => {
    assert.deepEqual(keys(summaryDiagnosis({ attempts: 10, adherence: 0.7, processHealth: [f("insufficient_data")] })), ["hosDiagCollecting"]);
    assert.equal(summaryDiagnosis({ attempts: 10, adherence: 0.7, processHealth: [f("playbook_works")] })[0].tone, "ok");
  });

  it("every diagnosis has copy in both languages", () => {
    for (const copy of [ES, EN]) {
      for (const key of ["hosDiagNoActivity", "hosDiagPlaybook", "hosDiagPlaybookNoEffect", "hosDiagCoach", "hosDiagNoProcess", "hosDiagWorks", "hosDiagCollecting"] as const) {
        assert.ok(copy[key], key);
      }
    }
  });
});

describe("hosOutcomes", () => {
  it("is hidden when the CRM has no outcomes", () => {
    assert.equal(hosOutcomes({ won: null, lost: null, crmCoverage: "complete" }), null);
    assert.equal(hosOutcomes({ won: 3, lost: null, crmCoverage: "complete" }), null);
    assert.equal(hosOutcomes({ won: undefined, lost: 2, crmCoverage: "complete" }), null);
    assert.equal(hosOutcomes({ won: 3, lost: 2, crmCoverage: "unavailable" }), null);
    assert.equal(hosOutcomes({ won: 3, lost: 2, crmCoverage: undefined }), null);
  });

  it("quotes the win rate on complete coverage", () => {
    assert.deepEqual(hosOutcomes({ won: 3, lost: 1, crmCoverage: "complete" }), { won: 3, lost: 1, winRate: 0.75 });
  });

  it("shows counts without a rate when partial, sample-limited or nothing closed", () => {
    assert.equal(hosOutcomes({ won: 3, lost: 1, crmCoverage: "partial" })?.winRate, null);
    assert.equal(hosOutcomes({ won: 3, lost: 1, crmCoverage: "complete", sampleLimited: true })?.winRate, null);
    assert.deepEqual(hosOutcomes({ won: 0, lost: 0, crmCoverage: "complete" }), { won: 0, lost: 0, winRate: null });
  });
});

describe("csvCell", () => {
  it("neutralises formula starts in text", () => {
    for (const bad of ["=SUM(A1)", "+1", "-1", "@cmd", "\tx", "\rx"]) {
      assert.ok(csvCell(bad).replace(/^"/, "").startsWith("'"), bad);
    }
    assert.equal(csvCell("=1+1"), "'=1+1");
  });

  it("keeps numbers as numbers, even negative", () => {
    assert.equal(csvCell(-5), "-5");
    assert.equal(csvCell(12.5), "12.5");
    assert.equal(csvCell(null), "");
  });

  it("quotes commas, quotes, newlines and carriage returns", () => {
    assert.equal(csvCell("a,b"), '"a,b"');
    assert.equal(csvCell('a"b'), '"a""b"');
    assert.equal(csvCell("a\nb"), '"a\nb"');
    assert.equal(csvCell("a\rb"), '"a\rb"');
    assert.equal(csvCell("\rb"), '"\'\rb"');
  });
});

describe("flowShortName", () => {
  it("names the role flows by role and anything else by its label", () => {
    assert.equal(flowShortName("discovery", "Flujo SDR"), "SDR");
    assert.equal(flowShortName("closing", "Flujo AE"), "AE");
    assert.equal(flowShortName("qualification", "Cualificación"), "Cualificación");
  });
});
