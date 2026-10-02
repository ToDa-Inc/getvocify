import { Link } from "react-router-dom";
import { ArrowRight, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { ChannelFilter } from "@/features/interactions/components/InteractionFilters";
import { InteractionList, InteractionSkeleton } from "@/features/interactions/components/InteractionRow";
import { useInteractionFeed } from "@/features/interactions/hooks/useInteractionFeed";
import { useTypeOptions } from "@/features/interactions/hooks/useTypeOptions";
import type { Memo } from "@/features/memos/types";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/** Inicio shows the latest few at any volume; everything else is one click away in Interacciones. */
const FEED_SIZE = 8;
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

  // Fade-out at the bottom of the list: mask-image linear-gradient over roughly the last 64-72px
  const fadeOutStyle = {
    maskImage: "linear-gradient(to bottom, black calc(100% - 72px), transparent 100%)",
    WebkitMaskImage: "linear-gradient(to bottom, black calc(100% - 72px), transparent 100%)",
  };

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
        <div style={fadeOutStyle}>
          <InteractionList items={feed.items} options={options} labelOf={labelOf} authorOf={authorOf} stale={feed.isPlaceholderData} />
        </div>
      )}
    </section>
  );
}
