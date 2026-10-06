import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { CRMSchema, Pipeline } from "@/lib/api/crm.ts";
import {
  buildHubSpotDealStageOptions,
  buildPipedriveStateOptions,
  buildQueueStateOptions,
  getHubSpotLeadStatusOptions,
  hasHubSpotLeadStatusOptions,
  normalizeQueueStateSource,
  prepareQueueStatesForSave,
  pruneQueueStates,
  toggleQueueState,
} from "./queue-states.ts";

const pipelines: Pipeline[] = [
  {
    id: "p1",
    label: "Sales",
    stages: [
      { id: "s1", label: "New" },
      { id: "s2", label: "Qualified" },
    ],
  },
  {
    id: "p2",
    label: "Enterprise",
    stages: [{ id: "s3", label: "Discovery" }],
  },
];

const contactSchema: CRMSchema = {
  object_type: "contacts",
  properties: [
    {
      name: "hs_lead_status",
      label: "Lead Status",
      type: "enumeration",
      options: [
        { label: "New", value: "NEW" },
        { label: "Open Deal", value: "OPEN_DEAL" },
      ],
    },
  ],
};

describe("buildHubSpotDealStageOptions", () => {
  it("labels stages with pipeline prefix when multiple pipelines", () => {
    const options = buildHubSpotDealStageOptions(pipelines);
    assert.deepEqual(options, [
      { value: "s1", label: "Sales · New" },
      { value: "s2", label: "Sales · Qualified" },
      { value: "s3", label: "Enterprise · Discovery" },
    ]);
  });

  it("uses stage label only for a single pipeline", () => {
    assert.deepEqual(buildHubSpotDealStageOptions([pipelines[0]]), [
      { value: "s1", label: "New" },
      { value: "s2", label: "Qualified" },
    ]);
  });
});

describe("lead status options", () => {
  it("reads hs_lead_status options from contacts schema", () => {
    assert.deepEqual(getHubSpotLeadStatusOptions(contactSchema), [
      { value: "NEW", label: "New" },
      { value: "OPEN_DEAL", label: "Open Deal" },
    ]);
    assert.equal(hasHubSpotLeadStatusOptions(contactSchema), true);
    assert.equal(hasHubSpotLeadStatusOptions({ object_type: "contacts", properties: [] }), false);
  });
});

describe("buildQueueStateOptions", () => {
  it("returns lead status options in lead_status mode", () => {
    const options = buildQueueStateOptions({
      provider: "hubspot",
      source: "lead_status",
      pipelines,
      contactSchema,
    });
    assert.equal(options.length, 2);
    assert.equal(options[0]?.value, "NEW");
  });

  it("appends won/lost for Pipedrive", () => {
    const options = buildPipedriveStateOptions(pipelines, { won: "Ganado", lost: "Perdido" });
    assert.equal(options.at(-2)?.value, "status:won");
    assert.equal(options.at(-1)?.value, "status:lost");
  });
});

describe("normalizeQueueStateSource", () => {
  it("forces deal_stage for Pipedrive", () => {
    assert.equal(normalizeQueueStateSource("lead_status", "pipedrive", contactSchema), "deal_stage");
  });

  it("falls back when lead status options are missing", () => {
    assert.equal(normalizeQueueStateSource("lead_status", "hubspot", null), "deal_stage");
  });
});

describe("toggleQueueState", () => {
  it("removes a state from the other group when checked", () => {
    assert.deepEqual(toggleQueueState("s1", "booked", [], ["s1"]), {
      queue_booked_states: ["s1"],
      queue_ended_states: [],
    });
    assert.deepEqual(toggleQueueState("s1", "ended", ["s1"], []), {
      queue_booked_states: [],
      queue_ended_states: ["s1"],
    });
  });

  it("unchecks within the same group", () => {
    assert.deepEqual(toggleQueueState("s1", "booked", ["s1"], []), {
      queue_booked_states: [],
      queue_ended_states: [],
    });
  });
});

describe("pruneQueueStates", () => {
  it("drops ids that are not in current options", () => {
    assert.deepEqual(pruneQueueStates(["s1", "gone"], ["bad", "s2"], ["s1", "s2"]), {
      queue_booked_states: ["s1"],
      queue_ended_states: ["s2"],
    });
  });
});

describe("prepareQueueStatesForSave", () => {
  it("prunes stale ids and normalizes source on save", () => {
    const result = prepareQueueStatesForSave({
      provider: "hubspot",
      source: "lead_status",
      booked: ["NEW", "stale"],
      ended: ["OPEN_DEAL", "missing"],
      pipelines,
      contactSchema,
    });
    assert.deepEqual(result, {
      queue_state_source: "lead_status",
      queue_booked_states: ["NEW"],
      queue_ended_states: ["OPEN_DEAL"],
    });
  });

  it("forces deal_stage for Pipedrive regardless of requested source", () => {
    const result = prepareQueueStatesForSave({
      provider: "pipedrive",
      source: "lead_status",
      booked: ["s1"],
      ended: ["status:won"],
      pipelines,
    });
    assert.equal(result.queue_state_source, "deal_stage");
    assert.deepEqual(result.queue_booked_states, ["s1"]);
    assert.deepEqual(result.queue_ended_states, ["status:won"]);
  });
});
