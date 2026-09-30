import { Link } from "react-router-dom";
import { MapPin, Mic, Phone, Users, type LucideIcon } from "lucide-react";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { Memo } from "@/features/memos/types";
import { formatCallDuration } from "@/lib/call-duration";
import {
  ageLabel,
  channelOf,
  rowPeople,
  rowStatus,
  rowTitle,
  typeChip,
  type Channel,
  type RowStatus,
  type TypeOption,
} from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { chipClass, TypeChip } from "./TypeChip";

const CHANNEL_ICON: Record<Channel, LucideIcon> = {
  call: Phone,
  meeting: Users,
  visit: MapPin,
  voice_note: Mic,
};

const STATUS_CLASS: Record<RowStatus, string> = {
  synced: "bg-success/10 text-success",
  review: "bg-warning/10 text-warning",
  processing: "text-muted-foreground",
  failed: "bg-destructive/10 text-destructive",
  voicemail: "bg-muted text-muted-foreground",
  no_answer: "bg-muted text-muted-foreground",
};

/**
 * One capture: channel, type (a menu that retags), who it was with, how long, where it stands and
 * when. The row opens the memo; the type chip sits above that link so it can be clicked on its own.
 * `author` is who recorded it, shown to managers only.
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
  const channel = channelOf(memo.interactionKind);
  const Icon = channel ? CHANNEL_ICON[channel] : null;
  const found = typeChip(memo, options);
  // A type the viewer's list doesn't carry comes back as its key: name it from the copy if we can.
  const chip = found && found.label === found.key ? { ...found, label: labelOf(found.key) } : found;
  const title = rowTitle(memo, copy.untitled);
  const people = rowPeople(memo, author);
  const duration = formatCallDuration(memo.audioDuration);
  const status = rowStatus(memo);
  const locale = t.product.hourLocale;
  const age = ageLabel(memo.createdAt, new Date(), locale);
  const when = new Date(memo.createdAt);
  const fullDate = Number.isNaN(when.getTime())
    ? undefined
    : new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(when);

  return (
    <li className="group relative flex items-center gap-4 border-b border-border/40 px-4 py-3 transition-colors duration-150 last:border-b-0 hover:bg-secondary/40 motion-reduce:transition-none">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex min-w-0 items-center gap-2">
          {channel && Icon ? (
            <span className={cn(chipClass, "shrink-0 bg-secondary text-muted-foreground")}>
              <Icon aria-hidden className="h-3 w-3" />
              {/* A phone keeps the icon only, so the title has room. */}
              <span className="sr-only sm:not-sr-only">{copy.channel[channel]}</span>
            </span>
          ) : null}
          {chip ? (
            <span className="relative z-10 shrink-0">
              <TypeChip memoId={memo.id} chip={chip} options={options} />
            </span>
          ) : null}
          <Link
            to={`/dashboard/memos/${memo.id}`}
            title={title}
            className="min-w-0 truncate text-[15px] text-foreground after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {title}
          </Link>
        </div>
        {people ? <p className="truncate text-[13px] text-muted-foreground">{people}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground sm:gap-3">
        {duration ? <span className="hidden tabular-nums sm:inline">{duration}</span> : null}
        {status ? (
          <span className={cn(chipClass, STATUS_CLASS[status])}>
            {status === "processing" ? <VocifySpinner size={12} /> : null}
            {copy.status[status]}
          </span>
        ) : null}
        <time dateTime={memo.createdAt} title={fullDate} className="text-right tabular-nums sm:w-20">
          {age}
        </time>
      </div>
    </li>
  );
}
