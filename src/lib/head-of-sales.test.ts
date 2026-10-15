import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  HOS_PERIODS,
  adherenceParams,
  processHealthView,
  summaryDiagnosis,
  flowShortName,
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
      { tone: "process", key: "hosDiagPlaybook", motion: "closing", href: "/dashboard/playbook" },
      { tone: "rep", key: "hosDiagCoach", motion: "discovery", href: "/dashboard/insights?tab=people" },
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

describe("flowShortName", () => {
  it("names the role flows by role and anything else by its label", () => {
    const copy = { hosRoleSdr: "Llamadas", hosRoleAe: "Reuniones" };
    assert.equal(flowShortName("discovery", "Flujo Llamadas", copy), "Llamadas");
    assert.equal(flowShortName("closing", "Flujo Reuniones", copy), "Reuniones");
    assert.equal(flowShortName("qualification", "Cualificación", copy), "Cualificación");
  });
});
