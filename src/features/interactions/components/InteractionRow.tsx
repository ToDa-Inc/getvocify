import { Link } from "react-router-dom";
import { MapPin, Mic, Phone, Users, type LucideIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { Memo } from "@/features/memos/types";
import { formatCallDuration } from "@/lib/call-duration";
import {
  channelOf,
  groupByDay,
  rowHeadline,
  rowStatus,
  timeLabel,
  typeChip,
  type Channel,
  type RowStatus,
  type TypeOption,
} from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { TypeChip } from "./TypeChip";

const CHANNEL_ICON: Record<Channel, LucideIcon> = {
  call: Phone,
  meeting: Users,
  visit: MapPin,
  voice_note: Mic,
};

// Only what asks for something: a call to review, one that failed, one still being read. A synced
// call says nothing; voicemail and no answer are a quiet word.
const STATUS_CLASS: Partial<Record<RowStatus, string>> = {
  review: "text-warning",
  failed: "text-destructive",
  processing: "text-muted-foreground",
  voicemail: "text-muted-foreground",
  no_answer: "text-muted-foreground",
};

/**
 * One capture, the way a notes app lists a note: what it was about, a line of what was said, its
 * type as a tag you can change, and the time. The whole row opens the memo; the tag sits above
 * that link so it can be clicked on its own. `author` is who recorded it, shown to managers only.
 */
export function InteractionRow({
  memo,
  options,
  labelOf = (key) => key,
  author = null,
}: {
  memo: Memo;
  options: TypeOption[];
  labelOf?: (key: string) => string;
  author?: string | null;
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  const locale = t.product.hourLocale;
  const channel = channelOf(memo.interactionKind);
  const Icon = channel ? CHANNEL_ICON[channel] : Mic;
  const found = typeChip(memo, options);
  // A type the viewer's list doesn't carry comes back as its key: name it from the copy if we can.
  const chip = found && found.label === found.key ? { ...found, label: labelOf(found.key) } : found;
  const duration = formatCallDuration(memo.audioDuration);
  const channelName = channel ? copy.channel[channel] : "";
  const fallback = duration ? copy.untitledWith.replace("{channel}", channelName).replace("{duration}", duration) : channelName || copy.untitled;
  const { title, preview } = rowHeadline(memo, fallback);
  const subtitle = [author?.trim(), preview].filter(Boolean).join(" · ");
  const status = rowStatus(memo);
  const statusClass = status ? STATUS_CLASS[status] : undefined;
  const when = new Date(memo.createdAt);
  const fullDate = Number.isNaN(when.getTime())
    ? undefined
    : new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(when);

  return (
    <li className="group relative flex items-center gap-3.5 rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-secondary/50 motion-reduce:transition-none">
      <span
        aria-hidden
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-secondary/60 text-muted-foreground"
      >
        <Icon className="h-4 w-4" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <Link
          to={`/dashboard/memos/${memo.id}`}
          title={title}
          className="block truncate text-[15px] leading-snug text-foreground after:absolute after:inset-0 after:rounded-xl after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {channelName ? <span className="sr-only">{channelName}: </span> : null}
          {title}
        </Link>
        {subtitle ? <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{subtitle}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
        {status && statusClass ? (
          <span className={cn("hidden items-center gap-1.5 sm:inline-flex", statusClass)}>
            {status === "processing" ? <VocifySpinner size={12} /> : <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />}
            {copy.status[status]}
          </span>
        ) : null}
        {/* No type yet: the chip to tag it shows on hover or focus, not as the same word on every row. */}
        <span
          className={cn(
            "relative z-10",
            !chip && "opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100 motion-reduce:transition-none",
          )}
        >
          <TypeChip
            memoId={memo.id}
            chip={chip ?? { key: "", label: copy.noType }}
            options={options}
            untyped={!chip}
          />
        </span>
        <time
          dateTime={memo.createdAt}
          title={[fullDate, duration].filter(Boolean).join(" · ")}
          className="w-12 text-right tabular-nums"
        >
          {timeLabel(memo.createdAt, locale)}
        </time>
      </div>
    </li>
  );
}

/** Rows under "Hoy", "Ayer" and dates. `stale` = old rows showing under a new filter. */
export function InteractionList({
  items,
  options,
  labelOf,
  authorOf,
  stale = false,
}: {
  items: Memo[];
  options: TypeOption[];
  labelOf?: (key: string) => string;
  authorOf: (memo: Memo) => string | null;
  stale?: boolean;
}) {
  const { t } = useLanguage();
  const groups = groupByDay(items, new Date(), t.product.hourLocale);
  return (
    <div
      aria-busy={stale || undefined}
      className={cn("space-y-4 transition-opacity duration-150 motion-reduce:transition-none", stale && "opacity-60")}
    >
      {groups.map((group) => (
        <section key={group.key} aria-label={group.label || undefined}>
          {group.label ? <h3 className="px-3 pb-1 text-[13px] font-medium text-muted-foreground">{group.label}</h3> : null}
          <ul className="space-y-0.5">
            {group.items.map((memo) => (
              <InteractionRow key={memo.id} memo={memo} options={options} labelOf={labelOf} author={authorOf(memo)} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** Placeholder rows with the same shape as a real one, so nothing jumps when they land. */
export function InteractionSkeleton({ rows }: { rows: number }) {
  return (
    <ul aria-busy className="space-y-0.5">
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className="flex items-center gap-3.5 px-3 py-2.5">
          <Skeleton className="h-10 w-10 rounded-lg motion-reduce:animate-none" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/2 motion-reduce:animate-none" />
            <Skeleton className="h-3 w-2/3 motion-reduce:animate-none" />
          </div>
          <Skeleton className="h-4 w-12 motion-reduce:animate-none" />
        </li>
      ))}
    </ul>
  );
}
