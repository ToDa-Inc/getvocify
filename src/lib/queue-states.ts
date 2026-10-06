import type { CRMSchema, Pipeline } from "@/lib/api/crm";

export type QueueStateSource = "deal_stage" | "lead_status";
export type CrmProvider = "hubspot" | "pipedrive";

export type QueueStateOption = {
  value: string;
  label: string;
};

export type PipedriveStatusLabels = {
  won: string;
  lost: string;
};

export function getHubSpotLeadStatusOptions(
  contactSchema?: CRMSchema | null,
): QueueStateOption[] {
  const prop = contactSchema?.properties.find((p) => p.name === "hs_lead_status");
  return (prop?.options ?? []).map((o) => ({ value: o.value, label: o.label }));
}

export function hasHubSpotLeadStatusOptions(contactSchema?: CRMSchema | null): boolean {
  return getHubSpotLeadStatusOptions(contactSchema).length > 0;
}

export function buildHubSpotDealStageOptions(pipelines: Pipeline[]): QueueStateOption[] {
  const multiPipeline = pipelines.length > 1;
  const options: QueueStateOption[] = [];
  for (const pipeline of pipelines) {
    for (const stage of pipeline.stages) {
      options.push({
        value: stage.id,
        label: multiPipeline ? `${pipeline.label} · ${stage.label}` : stage.label,
      });
    }
  }
  return options;
}

export function buildPipedriveStateOptions(
  pipelines: Pipeline[],
  statusLabels: PipedriveStatusLabels,
): QueueStateOption[] {
  return [
    ...buildHubSpotDealStageOptions(pipelines),
    { value: "status:won", label: statusLabels.won },
    { value: "status:lost", label: statusLabels.lost },
  ];
}

export function buildQueueStateOptions(params: {
  provider: CrmProvider;
  source: QueueStateSource;
  pipelines: Pipeline[];
  contactSchema?: CRMSchema | null;
  pipedriveStatusLabels?: PipedriveStatusLabels;
}): QueueStateOption[] {
  if (params.provider === "pipedrive") {
    return buildPipedriveStateOptions(
      params.pipelines,
      params.pipedriveStatusLabels ?? { won: "Won", lost: "Lost" },
    );
  }
  if (params.source === "lead_status") {
    return getHubSpotLeadStatusOptions(params.contactSchema);
  }
  return buildHubSpotDealStageOptions(params.pipelines);
}

export function normalizeQueueStateSource(
  source: QueueStateSource | undefined,
  provider: CrmProvider,
  contactSchema?: CRMSchema | null,
): QueueStateSource {
  if (provider === "pipedrive") return "deal_stage";
  if (source === "lead_status" && hasHubSpotLeadStatusOptions(contactSchema)) {
    return "lead_status";
  }
  return "deal_stage";
}

export function pruneQueueStates(
  booked: string[],
  ended: string[],
  validValues: Iterable<string>,
): { queue_booked_states: string[]; queue_ended_states: string[] } {
  const valid = new Set(validValues);
  return {
    queue_booked_states: booked.filter((id) => valid.has(id)),
    queue_ended_states: ended.filter((id) => valid.has(id)),
  };
}

export function toggleQueueState(
  stateId: string,
  group: "booked" | "ended",
  booked: string[],
  ended: string[],
): { queue_booked_states: string[]; queue_ended_states: string[] } {
  if (group === "booked") {
    const nextBooked = booked.includes(stateId)
      ? booked.filter((id) => id !== stateId)
      : [...booked, stateId];
    return {
      queue_booked_states: nextBooked,
      queue_ended_states: ended.filter((id) => id !== stateId),
    };
  }
  const nextEnded = ended.includes(stateId)
    ? ended.filter((id) => id !== stateId)
    : [...ended, stateId];
  return {
    queue_booked_states: booked.filter((id) => id !== stateId),
    queue_ended_states: nextEnded,
  };
}

export function prepareQueueStatesForSave(params: {
  provider: CrmProvider;
  source: QueueStateSource | undefined;
  booked: string[];
  ended: string[];
  pipelines: Pipeline[];
  contactSchema?: CRMSchema | null;
  pipedriveStatusLabels?: PipedriveStatusLabels;
}): {
  queue_state_source: QueueStateSource;
  queue_booked_states: string[];
  queue_ended_states: string[];
} {
  const queue_state_source = normalizeQueueStateSource(
    params.source,
    params.provider,
    params.contactSchema,
  );
  const options = buildQueueStateOptions({
    provider: params.provider,
    source: queue_state_source,
    pipelines: params.pipelines,
    contactSchema: params.contactSchema,
    pipedriveStatusLabels: params.pipedriveStatusLabels,
  });
  const pruned = pruneQueueStates(
    params.booked,
    params.ended,
    options.map((o) => o.value),
  );
  return {
    queue_state_source,
    queue_booked_states: pruned.queue_booked_states,
    queue_ended_states: pruned.queue_ended_states,
  };
}
