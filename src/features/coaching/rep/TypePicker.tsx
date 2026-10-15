import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { callTypeIcon } from "@/features/playbooks/icons";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import type { CoachCalls } from "@/lib/rep-coaching";
import { channelGroups, LIVE_CHANNELS, type LiveChannel } from "@/lib/type-channels";

/** The name a type reads as: the company's own, else the catalog's, else the key's label. */
export function useTypeName() {
  const { t } = useLanguage();
  const p = t.product;
  return (key: string, label?: string | null) =>
    label || p.pb2.typeLabels[key as keyof typeof p.pb2.typeLabels] || motionLabel(key, p.motions);
}

/**
 * The one control that says which interaction type the page is about: Progreso and Playbook both
 * follow it. Types by channel group under Llamadas / Reuniones when each type belongs to one;
 * a single type is a label, not a menu.
 */
export function TypePicker({
  types,
  value,
  onChange,
  playbooks,
}: {
  types: CoachCalls["types"];
  value: string;
  onChange: (key: string) => void;
  /** GET /playbooks, for the channels of each type; absent until it loads or when types are not by channel. */
  playbooks?: unknown;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const name = useTypeName();
  const current = types.find((type) => type.key === value);
  const Icon = callTypeIcon(value);
  const label = name(value, current?.label);

  if (types.length < 2) {
    return (
      <span className="inline-flex h-8 items-center gap-1.5 px-1 text-[13px] text-foreground" data-testid="coach-type">
        <Icon aria-hidden size={14} strokeWidth={1.5} className="text-muted-foreground" />
        {label}
      </span>
    );
  }

  // Grouped only when every type belongs to exactly one channel: a type of both would appear twice.
  const keys = types.map((type) => type.key);
  const groups = channelGroups(keys, playbooks);
  const grouped = Boolean(playbooks) && LIVE_CHANNELS.every((channel) => groups[channel].length) && groups.call.length + groups.meeting.length === keys.length;
  const item = (key: string) => {
    const type = types.find((candidate) => candidate.key === key);
    const ItemIcon = callTypeIcon(key);
    return (
      <SelectItem key={key} value={key}>
        <span className="inline-flex items-center gap-2">
          <ItemIcon aria-hidden size={14} strokeWidth={1.5} className="shrink-0 text-muted-foreground" />
          {name(key, type?.label)}
        </span>
      </SelectItem>
    );
  };

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger variant="chip" aria-label={p.coachTypeLabel} data-testid="coach-type">
        <SelectValue>
          <span className="inline-flex items-center gap-1.5">
            <Icon aria-hidden size={14} strokeWidth={1.5} className="shrink-0 text-muted-foreground" />
            {label}
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent align="end">
        {grouped
          ? LIVE_CHANNELS.map((channel: LiveChannel) => (
              <SelectGroup key={channel}>
                <SelectLabel>{p.pb2.ruleChannels[channel]}</SelectLabel>
                {groups[channel].map(item)}
              </SelectGroup>
            ))
          : keys.map(item)}
      </SelectContent>
    </Select>
  );
}
