import { useQuery } from "@tanstack/react-query";
import { homeApi, homeKeys } from "../api";

/** The rep home's side reads. Each one fails alone; focus reads them again. */
export function useHomeReads() {
  const followups = useQuery({
    queryKey: homeKeys.followups(),
    queryFn: () => homeApi.followups(),
    placeholderData: (previous) => previous,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => (query.state.data?.some((row) => row.status === "generating") ? 5000 : false),
  });
  const reviews = useQuery({
    queryKey: homeKeys.reviews(),
    queryFn: () => homeApi.reviews(),
    placeholderData: (previous) => previous,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  const upcoming = useQuery({
    queryKey: homeKeys.upcoming(),
    queryFn: () => homeApi.upcoming(),
    placeholderData: (previous) => previous,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  const done = useQuery({
    queryKey: homeKeys.done(),
    queryFn: () => homeApi.done(),
    placeholderData: (previous) => previous,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  return { followups, reviews, upcoming, done };
}
