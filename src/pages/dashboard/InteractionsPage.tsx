import { useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pagination, PaginationContent, PaginationItem } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth";
import { companyApi, companyKeys } from "@/features/company/api";
import { InteractionFilters } from "@/features/interactions/components/InteractionFilters";
import { InteractionRow } from "@/features/interactions/components/InteractionRow";
import { useInteractionFeed } from "@/features/interactions/hooks/useInteractionFeed";
import { useTypeOptions } from "@/features/interactions/hooks/useTypeOptions";
import type { Memo } from "@/features/memos/types";
import { authorDisplayName, canViewCompanyActivity, defaultActivityAuthorId } from "@/lib/activity-authors";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { PAGINATION } from "@/shared/lib/constants";

const listClass = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-hidden`;

/** Every capture — calls, meetings, visits, voice notes — in one paginated list, by channel and type. */
const InteractionsPage = () => {
  const { user } = useAuth();
  const { t } = useLanguage();
  const copy = t.product.interactions;
  // A member always lists their own; a manager lists the company, starting on themselves when
  // there is a team, or on the person `?author=` names (rep detail links here).
  const canViewCompany = canViewCompanyActivity(user?.company?.role);
  const [searchParams] = useSearchParams();

  const { data: membersData, isPending: membersPending } = useQuery({
    queryKey: companyKeys.members(),
    queryFn: companyApi.listMembers,
    enabled: canViewCompany,
  });
  const authors = (membersData?.members ?? [])
    .filter((member) => member.status === "active")
    .map((member) => ({ userId: member.userId, label: authorDisplayName(member.fullName, member.email), email: member.email }));
  const authorParam = canViewCompany ? searchParams.get("author") : null;

  const feed = useInteractionFeed({
    scope: canViewCompany ? "company" : "me",
    pageSize: PAGINATION.DEFAULT_PAGE_SIZE,
    defaultAuthorUserId: authorParam ?? defaultActivityAuthorId(canViewCompany, user?.id, authors.length),
    // The default author depends on the team size: wait for it rather than load the list twice.
    enabled: !canViewCompany || Boolean(authorParam) || !membersPending,
  });
  const { options, labelOf } = useTypeOptions();
  // Your own list with nothing in it is an empty account, not a filter: offer to record.
  const filtered =
    feed.channel !== "all" || feed.typeKey !== "all" || Boolean(feed.authorUserId && feed.authorUserId !== user?.id);

  const listRef = useRef<HTMLDivElement>(null);
  const goTo = (page: number) => {
    feed.setPage(page);
    // Back to the top of the list, not of the page, and only when it has scrolled out of view.
    const list = listRef.current;
    const viewTop = list?.closest("main")?.getBoundingClientRect().top ?? 0;
    if (list && list.getBoundingClientRect().top < viewTop) list.scrollIntoView({ block: "start" });
  };
  const clearFilters = () => {
    feed.setChannel("all");
    feed.setTypeKey("all");
    feed.setAuthorUserId(null);
  };
  // Who recorded it, for a manager looking at more than one person; a single author is already the filter.
  const authorOf = (memo: Memo) =>
    canViewCompany && !feed.authorUserId ? (memo.userId === user?.id ? copy.you : memo.authorName?.trim() || null) : null;

  return (
    <div className={cn("mx-auto max-w-4xl space-y-6", THEME_TOKENS.motion.fadeIn, "motion-reduce:animate-none")}>
      <h1 className={THEME_TOKENS.typography.pageTitle}>{copy.title}</h1>

      <InteractionFilters
        channel={feed.channel}
        onChannel={feed.setChannel}
        typeKey={feed.typeKey}
        onType={feed.setTypeKey}
        options={options}
        authors={canViewCompany ? authors : null}
        authorUserId={feed.authorUserId}
        onAuthor={feed.setAuthorUserId}
        currentUserId={user?.id}
      />

      <div ref={listRef} className="scroll-mt-6">
        {feed.isLoading ? (
          <ul aria-busy className={listClass}>
            {Array.from({ length: 6 }, (_, index) => (
              <li key={index} className="flex items-center gap-4 border-b border-border/40 px-4 py-3.5 last:border-b-0">
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/2 motion-reduce:animate-none" />
                  <Skeleton className="h-3 w-1/4 motion-reduce:animate-none" />
                </div>
                <Skeleton className="h-5 w-24 motion-reduce:animate-none" />
              </li>
            ))}
          </ul>
        ) : feed.isError && feed.items.length === 0 ? (
          <div className={cn(listClass, "flex flex-col items-center gap-3 px-6 py-12 text-center")}>
            <p className={THEME_TOKENS.typography.body}>{copy.loadFailed}</p>
            <Button variant="outline" size="sm" onClick={feed.retry}>
              {copy.retry}
            </Button>
          </div>
        ) : feed.items.length === 0 ? (
          <div className={cn(listClass, "flex flex-col items-center gap-4 px-6 py-14 text-center")}>
            <p className={THEME_TOKENS.typography.sectionTitle}>{filtered ? copy.emptyFiltered : copy.empty}</p>
            {filtered ? (
              <Button variant="outline" size="sm" onClick={clearFilters}>
                {copy.clearFilters}
              </Button>
            ) : (
              <Button asChild size="sm">
                <Link to="/dashboard/record">
                  <Mic aria-hidden />
                  {copy.record}
                </Link>
              </Button>
            )}
          </div>
        ) : (
          <ul
            className={cn(
              listClass,
              "transition-opacity duration-150 motion-reduce:transition-none",
              feed.isPlaceholderData && "opacity-60",
            )}
          >
            {feed.items.map((memo) => (
              <InteractionRow key={memo.id} memo={memo} options={options} labelOf={labelOf} author={authorOf(memo)} />
            ))}
          </ul>
        )}
      </div>

      {feed.page > 0 || feed.hasMore ? (
        <Pagination aria-label={copy.pages}>
          <PaginationContent className="gap-3">
            <PaginationItem>
              <Button variant="ghost" size="sm" disabled={feed.page === 0 || feed.isPlaceholderData} onClick={() => goTo(feed.page - 1)}>
                <ChevronLeft aria-hidden />
                {copy.previous}
              </Button>
            </PaginationItem>
            <PaginationItem aria-current="page" className="text-[13px] tabular-nums text-muted-foreground">
              {copy.page.replace("{n}", String(feed.page + 1))}
            </PaginationItem>
            <PaginationItem>
              <Button variant="ghost" size="sm" disabled={!feed.hasMore || feed.isPlaceholderData} onClick={() => goTo(feed.page + 1)}>
                {copy.next}
                <ChevronRight aria-hidden />
              </Button>
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      ) : null}
    </div>
  );
};

export default InteractionsPage;
