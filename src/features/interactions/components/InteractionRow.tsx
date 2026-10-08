import { Link } from "react-router-dom";
import { AudioLines, MapPin, Phone, Timer, Video, type LucideIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { Memo } from "@/features/memos/types";
import { formatCallDuration } from "@/lib/call-duration";
import {
  channelOf,
  groupByDay,
  rowContacts,
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
import { useCrmContactLink } from "../hooks/useCrmContactLink";
import { ContactStack } from "./ContactStack";
import { TypeChip } from "./TypeChip";

const CHANNEL_ICON: Record<Channel, LucideIcon> = {
  call: Phone,
  meeting: Video,
  visit: MapPin,
  voice_note: AudioLines,
};

/** The glyph says what it was; the tint tells calls from meetings at a glance. */
const CHANNEL_TILE: Record<Channel, string> = {
  call: "border-success/20 bg-success/10 text-success",
  meeting: "border-beige/25 bg-beige/10 text-beige",
  visit: "border-border/60 bg-secondary/60 text-foreground/80",
  voice_note: "border-border/50 bg-muted/70 text-muted-foreground",
};

// Only what asks for something: a call to review, one that failed, one still being read. A synced
// call says nothing; voicemail and no answer are a quiet word. It leads the subtitle.
const STATUS_CLASS: Partial<Record<RowStatus, string>> = {
  review: "font-medium text-warning",
  failed: "font-medium text-destructive",
  processing: "text-muted-foreground",
  voicemail: "text-muted-foreground",
  no_answer: "text-muted-foreground",
};

/** The corner mark on the tile for what needs the person: to review, or failed. */
const STATUS_MARK: Partial<Record<RowStatus, string>> = {
  review: "bg-warning",
  failed: "bg-destructive",
};

/**
 * One capture, the way a notes app lists a note: what it was about, a line of what was said, who was
 * in it, its type as a tag you can change, and when it happened. The whole row opens the memo; the
 * contacts and the tag sit above that link so they work on their own. `author` is who recorded it,
 * shown to managers only.
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
  const Icon = channel ? CHANNEL_ICON[channel] : AudioLines;
  const found = typeChip(memo, options);
  // A type the viewer's list doesn't carry comes back as its key: name it from the copy if we can.
  const chip = found && found.label === found.key ? { ...found, label: labelOf(found.key) } : found;
  const duration = formatCallDuration(memo.audioDuration);
  const channelName = channel ? copy.channel[channel] : "";
  const fallback = duration ? copy.untitledWith.replace("{channel}", channelName).replace("{duration}", duration) : channelName || copy.untitled;
  const { title, preview } = rowHeadline(memo, fallback);
  const status = rowStatus(memo);
  const statusClass = status ? STATUS_CLASS[status] : undefined;
  const statusWord = status && statusClass ? copy.status[status] : null;
  const subtitle = [author?.trim(), preview].filter(Boolean).join(" · ");
  const when = new Date(memo.createdAt);
  const fullDate = Number.isNaN(when.getTime())
    ? undefined
    : new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(when);
  const contacts = rowContacts(memo);
  const crm = useCrmContactLink(memo.hubspotContactId);

  return (
    <li className="group relative flex items-center gap-3.5 rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none">
      <span
        aria-hidden
        className={cn(
          "relative flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border",
          CHANNEL_TILE[channel ?? "voice_note"],
        )}
      >
        <Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
        {status && STATUS_MARK[status] ? (
          <span className={cn("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full ring-2 ring-background group-hover:ring-secondary", STATUS_MARK[status])} />
        ) : null}
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
        {statusWord || subtitle ? (
          <p className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground">
            {statusWord ? (
              <span className={cn("inline-flex shrink-0 items-center gap-1.5", statusClass)}>
                {status === "processing" ? <VocifySpinner size={12} /> : null}
                {statusWord}
              </span>
            ) : null}
            {statusWord && subtitle ? <span aria-hidden>·</span> : null}
            {subtitle ? <span className="truncate">{subtitle}</span> : null}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-3.5 text-xs text-muted-foreground">
        <ContactStack
          contacts={contacts}
          kind={channel === "meeting" ? "meeting" : "single"}
          crmUrl={crm.url}
          crmName={crm.name}
        />
        {/* No type yet: the dashed chip says so and tags it on one click. */}
        <span className="relative z-10">
          <TypeChip
            memoId={memo.id}
            chip={chip ?? { key: "", label: copy.noType }}
            options={options}
            channel={memo.interactionKind}
            untyped={!chip}
          />
        </span>
        <div className="w-[4.25rem] text-right tabular-nums leading-tight">
          <time dateTime={memo.createdAt} title={fullDate} className="block text-[13px] text-foreground/85">
            {timeLabel(memo.createdAt, locale)}
          </time>
          {duration ? (
            <span className="mt-0.5 inline-flex items-center gap-1 text-[11.5px]">
              <Timer aria-hidden className="h-3 w-3" strokeWidth={1.5} />
              {duration}
            </span>
          ) : null}
        </div>
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
