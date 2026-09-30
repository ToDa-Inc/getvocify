import { Link } from "react-router-dom";
import { ArrowRight, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth";
import { ChannelTabs } from "@/features/interactions/components/InteractionFilters";
import { InteractionRow } from "@/features/interactions/components/InteractionRow";
import { useInteractionFeed } from "@/features/interactions/hooks/useInteractionFeed";
import { useTypeOptions } from "@/features/interactions/hooks/useTypeOptions";
import type { Memo } from "@/features/memos/types";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/** Inicio shows the latest few at any volume; everything else is one click away in Interacciones. */
const FEED_SIZE = 8;
const listClass = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-hidden`;

/** The latest captures, the same rows as Interacciones: a rep's own, the whole company for a manager. */
export function LatestInteractions({ manager }: { manager: boolean }) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const copy = t.product.interactions;
  const home = t.product.home;
  const feed = useInteractionFeed({ scope: manager ? "company" : "me", pageSize: FEED_SIZE });
  const { options, labelOf } = useTypeOptions();
  const empty = !feed.isLoading && !feed.isError && feed.items.length === 0;
  // Nothing recorded yet is the account's first step, not an empty filter: no tabs over nothing.
  const firstRun = empty && feed.channel === "all";
  const authorOf = (memo: Memo) => (manager ? (memo.userId === user?.id ? copy.you : memo.authorName?.trim() || null) : null);

  return (
    <section aria-labelledby="home-latest" className="flex flex-col gap-3 md:min-h-0 md:flex-1">
      <div className="flex items-center justify-between gap-4">
        <h2 id="home-latest" className={THEME_TOKENS.typography.sectionTitle}>
          {home.latest}
        </h2>
        {firstRun ? null : (
          <Link
            to="/dashboard/interactions"
            className="inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {home.seeAll}
            <ArrowRight aria-hidden className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      {firstRun ? null : <ChannelTabs channel={feed.channel} onChannel={feed.setChannel} />}

      <div className="md:min-h-0 md:flex-1 md:overflow-y-auto">
        {feed.isLoading ? (
          <ul aria-busy className={listClass}>
            {Array.from({ length: 4 }, (_, index) => (
              <li key={index} className="flex items-center gap-4 border-b border-border/40 px-4 py-3.5 last:border-b-0">
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/2 motion-reduce:animate-none" />
                  <Skeleton className="h-3 w-1/4 motion-reduce:animate-none" />
                </div>
                <Skeleton className="h-5 w-20 motion-reduce:animate-none" />
              </li>
            ))}
          </ul>
        ) : feed.isError && feed.items.length === 0 ? (
          <div className={cn(listClass, "flex items-center justify-between gap-3 px-4 py-4")} role="alert">
            <p className={THEME_TOKENS.typography.body}>{copy.loadFailed}</p>
            <Button variant="outline" size="sm" onClick={feed.retry}>
              {copy.retry}
            </Button>
          </div>
        ) : firstRun ? (
          <div className={cn(listClass, "flex items-center justify-between gap-3 px-4 py-4")}>
            <p className="text-[15px] text-foreground">{home.firstRecording}</p>
            <Button asChild size="sm">
              <Link to="/dashboard/record">
                <Mic aria-hidden />
                {copy.record}
              </Link>
            </Button>
          </div>
        ) : empty ? (
          <p className={cn(THEME_TOKENS.typography.body, "px-1 py-2")}>{copy.emptyFiltered}</p>
        ) : (
          <ul
            className={cn(listClass, "transition-opacity duration-150 motion-reduce:transition-none", feed.isPlaceholderData && "opacity-60")}
          >
            {feed.items.map((memo) => (
              <InteractionRow key={memo.id} memo={memo} options={options} labelOf={labelOf} author={authorOf(memo)} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
