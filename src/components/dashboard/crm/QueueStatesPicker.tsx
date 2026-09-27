import { useMemo } from "react";
import { ChevronDown } from "lucide-react";
import type { CRMConfiguration, CRMSchema, Pipeline } from "@/lib/api/crm";
import {
  buildQueueStateOptions,
  hasHubSpotLeadStatusOptions,
  normalizeQueueStateSource,
  toggleQueueState,
  type CrmProvider,
  type QueueStateSource,
} from "@/lib/queue-states";
import { useLanguage } from "@/lib/i18n";

type QueueStatesPickerProps = {
  provider: CrmProvider;
  config: Pick<
    CRMConfiguration,
    "queue_state_source" | "queue_booked_states" | "queue_ended_states"
  >;
  onChange: (
    patch: Partial<
      Pick<
        CRMConfiguration,
        "queue_state_source" | "queue_booked_states" | "queue_ended_states"
      >
    >,
  ) => void;
  pipelines: Pipeline[];
  contactSchema?: CRMSchema | null;
  readOnly?: boolean;
  selectClassName?: string;
};

function StateCheckboxList({
  title,
  options,
  selected,
  group,
  readOnly,
  prominent,
  onToggle,
}: {
  title: string;
  options: { value: string; label: string }[];
  selected: string[];
  group: "booked" | "ended";
  readOnly?: boolean;
  prominent?: boolean;
  onToggle: (stateId: string, group: "booked" | "ended") => void;
}) {
  return (
    <div className="space-y-2 min-w-0">
      <p className={prominent ? "text-[13px] text-foreground" : "text-[11px] text-muted-foreground"}>{title}</p>
      <div className="max-h-40 overflow-y-auto rounded-2xl border border-border/20 bg-secondary/5 p-2 space-y-0.5">
        {options.length > 0 ? (
          options.map((option) => {
            const checked = selected.includes(option.value);
            return (
              <label
                key={option.value}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-xl text-[12px] cursor-pointer ${
                  checked ? "text-foreground" : "text-muted-foreground"
                } ${readOnly ? "cursor-default opacity-60" : "hover:bg-secondary/10"}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={readOnly}
                  onChange={() => onToggle(option.value, group)}
                  className="h-3.5 w-3.5 shrink-0 rounded border-border/50 accent-beige"
                />
                <span className="truncate">{option.label}</span>
              </label>
            );
          })
        ) : (
          <p className="px-2 py-3 text-[11px] text-muted-foreground/60 italic">No states available</p>
        )}
      </div>
    </div>
  );
}

export const QueueStatesPicker = ({
  provider,
  config,
  onChange,
  pipelines,
  contactSchema,
  readOnly = false,
  selectClassName = "w-full h-10 pl-4 pr-10 rounded-full border border-border/40 bg-secondary/5 text-sm text-foreground appearance-none cursor-pointer focus:outline-none disabled:opacity-60",
}: QueueStatesPickerProps) => {
  const { t } = useLanguage();
  const source = normalizeQueueStateSource(
    config.queue_state_source,
    provider,
    contactSchema,
  );
  const leadStatusAvailable = hasHubSpotLeadStatusOptions(contactSchema);
  const booked = config.queue_booked_states ?? [];
  const ended = config.queue_ended_states ?? [];

  const options = useMemo(
    () =>
      buildQueueStateOptions({
        provider,
        source,
        pipelines,
        contactSchema,
        pipedriveStatusLabels: {
          won: t.product.queueStateWon,
          lost: t.product.queueStateLost,
        },
      }),
    [provider, source, pipelines, contactSchema, t.product.queueStateWon, t.product.queueStateLost],
  );

  const handleSourceChange = (next: QueueStateSource) => {
    onChange({ queue_state_source: next, queue_booked_states: [], queue_ended_states: [] });
  };

  const handleToggle = (stateId: string, group: "booked" | "ended") => {
    if (readOnly) return;
    const next = toggleQueueState(stateId, group, booked, ended);
    onChange(next);
  };

  return (
    <div className="space-y-3">
      {provider === "hubspot" ? (
        <label className="space-y-1.5 block min-w-0">
          <span className="block text-[11px] text-muted-foreground">{t.product.queueStateSourceLabel}</span>
          <div className="relative">
            <select
              value={source}
              disabled={readOnly}
              onChange={(e) => handleSourceChange(e.target.value as QueueStateSource)}
              className={selectClassName}
            >
              <option value="deal_stage">{t.product.queueStateSourceDealStage}</option>
              <option value="lead_status" disabled={!leadStatusAvailable}>
                {t.product.queueStateSourceLeadStatus}
              </option>
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
          </div>
        </label>
      ) : null}

      <div className="space-y-3">
        <StateCheckboxList
          title={t.product.queueExitBooked}
          options={options}
          selected={booked}
          group="booked"
          readOnly={readOnly}
          prominent
          onToggle={handleToggle}
        />
        <StateCheckboxList
          title={t.product.queueExitEnded}
          options={options}
          selected={ended}
          group="ended"
          readOnly={readOnly}
          onToggle={handleToggle}
        />
      </div>
    </div>
  );
};
