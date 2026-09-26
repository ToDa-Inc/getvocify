import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { followupPoll } from "@shared/ui/home.js";
import { homeApi, homeKeys } from "../api";

/** The rep home's side reads. Each one fails alone; focus reads them again. */
export function useHomeReads() {
  const writingSince = useRef<number | null>(null);
  const followups = useQuery({
    queryKey: homeKeys.followups(),
    queryFn: () => homeApi.followups(),
    placeholderData: (previous) => previous,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      const next = followupPoll(query.state.data, writingSince.current, Date.now());
      writingSince.current = next.since;
      return next.interval;
    },
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
