import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { activityFilterChips, type ActivityAuthor } from "@/lib/activity-authors";
import { CHANNELS, type Channel, type TypeOption } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";

const ALL = "all";
const selectClass = "h-9 w-auto min-w-[9rem] max-w-[14rem] gap-2 rounded-full border-border/70 bg-card text-[13px]";

/**
 * Channel as tabs (the same list seen five ways), type and — for a manager — author as selects.
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
  const authorChoices = authors ? activityFilterChips(authors, currentUserId) : [];
  const authorName = (chip: { id: string | null; label: string }) =>
    chip.id === null ? t.product.activityAll : chip.id === currentUserId ? t.product.activityMine : chip.label;

  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <Tabs value={channel} onValueChange={(next) => onChannel(next as Channel | "all")}>
        <TabsList aria-label={copy.channelFilter} className="h-auto max-w-full flex-wrap justify-start rounded-full border border-border bg-card p-1">
          {(["all", ...CHANNELS] as const).map((option) => (
            <TabsTrigger
              key={option}
              value={option}
              className="rounded-full px-3.5 py-1 text-xs font-normal text-muted-foreground transition-colors duration-150 hover:text-foreground motion-reduce:transition-none data-[state=active]:bg-beige data-[state=active]:text-cream data-[state=active]:shadow-none"
            >
              {copy.channels[option]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={typeKey} onValueChange={onType}>
          <SelectTrigger aria-label={copy.typeFilter} className={selectClass}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{copy.allTypes}</SelectItem>
            {options.map((option) => (
              <SelectItem key={option.key} value={option.key}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {authors ? (
          <Select value={authorUserId ?? ALL} onValueChange={(next) => onAuthor(next === ALL ? null : next)}>
            <SelectTrigger aria-label={copy.authorFilter} className={selectClass}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {authorChoices.map((chip) => (
                <SelectItem key={chip.id ?? ALL} value={chip.id ?? ALL}>
                  {authorName(chip)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
      </div>
    </div>
  );
}
