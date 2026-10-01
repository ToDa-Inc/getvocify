import { activityFilterChips, type ActivityAuthor } from "@/lib/activity-authors";
import { CHANNELS, type Channel, type TypeOption } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { FilterMenu } from "./FilterMenu";

const ALL = "all";

/** Channel as one menu: all, calls, meetings, visits, voice notes. */
export function ChannelFilter({ channel, onChannel }: { channel: Channel | "all"; onChannel: (next: Channel | "all") => void }) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  return (
    <FilterMenu
      label={copy.channelFilter}
      value={channel}
      choices={[{ value: "all", label: copy.allChannels }, ...CHANNELS.map((option) => ({ value: option, label: copy.channels[option] }))]}
      onChange={(next) => onChannel(next as Channel | "all")}
    />
  );
}

/**
 * The list's filters, side by side as menus: channel, type and — for a manager — who recorded it.
 * `authors` is null for a rep, who only ever sees their own interactions.
 */
export function InteractionFilters({
  channel,
  onChannel,
  typeKey,
  onType,
  options,
  authors,
  authorUserId,
  onAuthor,
  currentUserId,
}: {
  channel: Channel | "all";
  onChannel: (next: Channel | "all") => void;
  typeKey: string;
  onType: (next: string) => void;
  options: TypeOption[];
  authors: ActivityAuthor[] | null;
  authorUserId: string | null;
  onAuthor: (next: string | null) => void;
  currentUserId?: string | null;
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  // "Everyone" first: the menu treats its first choice as the unfiltered one.
  const chips = authors ? activityFilterChips(authors, currentUserId) : [];
  const authorChoices = [...chips.filter((chip) => chip.id === null), ...chips.filter((chip) => chip.id !== null)];
  const authorName = (chip: { id: string | null; label: string }) =>
    chip.id === null ? copy.allPeople : chip.id === currentUserId ? t.product.activityMine : chip.label;

  return (
    <div role="group" aria-label={copy.filters} className="flex flex-wrap items-center gap-2">
      <ChannelFilter channel={channel} onChannel={onChannel} />
      <FilterMenu
        label={copy.typeFilter}
        value={typeKey}
        choices={[{ value: ALL, label: copy.allTypes }, ...options.map((option) => ({ value: option.key, label: option.label }))]}
        onChange={onType}
      />
      {authors ? (
        <FilterMenu
          label={copy.authorFilter}
          value={authorUserId ?? ALL}
          choices={authorChoices.map((chip) => ({ value: chip.id ?? ALL, label: authorName(chip) }))}
          onChange={(next) => onAuthor(next === ALL ? null : next)}
        />
      ) : null}
    </div>
  );
}
