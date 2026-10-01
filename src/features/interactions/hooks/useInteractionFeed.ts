import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { memoKeys, memosApi } from "@/features/memos/api";
import { feedBusy, feedQuery, pageOf, type Channel } from "@/lib/interactions";

const POLL_MS = 10_000;
// The app caches forever by default; a capture made elsewhere should show when the list is reopened.
const STALE_MS = 30_000;

/**
 * One page of the interactions feed, server-paginated: it asks for one row more than the page to
 * know whether there is a next one. Changing a filter goes back to the first page. It polls only
 * while a row on screen is still uploading, transcribing or extracting.
 *
 * `defaultAuthorUserId` is where the author filter starts (company scope only); it applies until the
 * viewer picks an author. Pass `enabled: false` while that default is still unknown, so the list
 * does not load once for everyone and again for one person.
 */
export function useInteractionFeed({
  scope,
  pageSize,
  initialChannel = "all",
  defaultAuthorUserId = null,
  enabled = true,
}: {
  scope: "me" | "company";
  pageSize: number;
  initialChannel?: Channel | "all";
  defaultAuthorUserId?: string | null;
  enabled?: boolean;
}) {
  const [page, setPage] = useState(0);
  const [channel, setChannelState] = useState<Channel | "all">(initialChannel);
  const [typeKey, setTypeKeyState] = useState<string | "all">("all");
  const [pickedAuthor, setPickedAuthor] = useState<string | null | undefined>(undefined);
  const authorUserId = scope === "company" ? (pickedAuthor !== undefined ? pickedAuthor : defaultAuthorUserId) : null;

  const filters = {
    ...feedQuery({ channel, typeKey, authorUserId: authorUserId ?? undefined, page }, pageSize),
    scope,
  };
  const query = useQuery({
    queryKey: memoKeys.list(filters),
    queryFn: () => memosApi.list(filters),
    enabled,
    staleTime: STALE_MS,
    placeholderData: keepPreviousData,
    refetchInterval: (current) => (feedBusy(current.state.data ?? []) ? POLL_MS : false),
  });
  const { items, hasMore } = pageOf(query.data ?? [], pageSize);

  // A retag or a delete can empty the last page: step back rather than show "nothing here".
  const emptiedPage = query.isSuccess && !query.isPlaceholderData && page > 0 && items.length === 0;
  useEffect(() => {
    if (emptiedPage) setPage((current) => Math.max(0, current - 1));
  }, [emptiedPage]);

  return {
    items,
    hasMore,
    page,
    setPage,
    channel,
    setChannel: (next: Channel | "all") => {
      setChannelState(next);
      setPage(0);
    },
    typeKey,
    setTypeKey: (next: string | "all") => {
      setTypeKeyState(next);
      setPage(0);
    },
    authorUserId,
    setAuthorUserId: (next: string | null) => {
      setPickedAuthor(next);
      setPage(0);
    },
    isLoading: query.isPending,
    isFetching: query.isFetching,
    isPlaceholderData: query.isPlaceholderData,
    isError: query.isError,
    retry: () => void query.refetch(),
  };
}
