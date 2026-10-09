import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { ChannelFilter } from "@/features/interactions/components/InteractionFilters";
import { InteractionList, InteractionSkeleton } from "@/features/interactions/components/InteractionRow";
import { useInteractionFeed } from "@/features/interactions/hooks/useInteractionFeed";
import { useTypeOptions } from "@/features/interactions/hooks/useTypeOptions";
import type { Memo } from "@/features/memos/types";
import { scrolledToEnd } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { PAGINATION } from "@/shared/lib/constants";

/** Inicio shows the latest page in a panel you scroll; everything else is one click away in Interacciones. */
const FEED_SIZE = PAGINATION.DEFAULT_PAGE_SIZE;
const FADE = "linear-gradient(to bottom, black calc(100% - 72px), transparent 100%)";
const boxClass = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;


/** The latest captures, the same rows as Interacciones: a rep's own, the whole company for a manager. */
export function LatestInteractions({ manager }: { manager: boolean }) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const copy = t.product.interactions;
  const home = t.product.home;
  const feed = useInteractionFeed({ scope: manager ? "company" : "me", pageSize: FEED_SIZE });
  const { options, labelOf } = useTypeOptions();
  const empty = !feed.isLoading && !feed.isError && feed.items.length === 0;
  // Nothing recorded yet is the account's first step, not an empty filter: no filter over nothing.
  const firstRun = empty && feed.channel === "all";
  // Who recorded it, for a manager: only when it was someone else, not "You" on every row.
  const authorOf = (memo: Memo) => (manager && memo.userId !== user?.id ? memo.authorName?.trim() || null : null);

  // The list dissolves at the bottom edge while there is more to scroll to, and is plain once read to its end.
  const scroller = useRef<HTMLDivElement>(null);
  const [atEnd, setAtEnd] = useState(true);
  const measure = useCallback(() => {
    if (scroller.current) setAtEnd(scrolledToEnd(scroller.current));
  }, []);
  useEffect(() => {
    measure();
    const node = scroller.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [measure, feed.items.length]);
  const fade = atEnd ? undefined : { maskImage: FADE, WebkitMaskImage: FADE };

  return (
    <section aria-labelledby="home-latest" className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 px-3">
        <h2 id="home-latest" className={THEME_TOKENS.typography.sectionTitle}>
          {home.latest}
        </h2>
        {firstRun ? null : (
          <div className="flex items-center gap-3">
            <ChannelFilter channel={feed.channel} onChannel={feed.setChannel} />
            <Link
              to="/dashboard/interactions"
              className="inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {home.seeAll}
              <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}
      </div>

      {feed.isLoading ? (
        <InteractionSkeleton rows={4} />
      ) : feed.isError && feed.items.length === 0 ? (
        <div className={cn(boxClass, "flex items-center justify-between gap-3 px-4 py-4")} role="alert">
          <p className={THEME_TOKENS.typography.body}>{copy.loadFailed}</p>
          <Button variant="outline" size="sm" onClick={feed.retry}>
            {copy.retry}
          </Button>
        </div>
      ) : firstRun ? (
        <div className={cn(boxClass, "flex items-center justify-between gap-3 px-4 py-4")}>
          <p className="text-[15px] text-foreground">{home.firstRecording}</p>
          <Button asChild variant="outline" size="sm">
            <Link to="/dashboard/record">
              <Mic aria-hidden />
              {copy.record}
            </Link>
          </Button>
        </div>
      ) : empty ? (
        <p className={cn(THEME_TOKENS.typography.body, "px-3 py-2")}>{copy.emptyFiltered}</p>
      ) : (
        <div
          ref={scroller}
          onScroll={measure}
          style={fade}
          className="app-scroll max-h-[min(56vh,34rem)] overflow-y-auto overscroll-contain"
        >
          <InteractionList items={feed.items} options={options} labelOf={labelOf} authorOf={authorOf} stale={feed.isPlaceholderData} />
          {feed.hasMore ? (
            <div className="flex justify-center px-3 py-3">
              <Button asChild variant="quiet" size="text">
                <Link to="/dashboard/interactions">
                  {home.seeAll}
                  <ArrowRight aria-hidden strokeWidth={1.5} />
                </Link>
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
