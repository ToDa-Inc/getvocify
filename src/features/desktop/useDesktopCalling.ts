import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDesktopBridge, type DesktopCalling } from "@/lib/desktop-host";

const callingKey = ["desktop-calling"] as const;

/** Vocify calling on this computer (kept by the desktop app); null outside it or in builds without it. */
export function useDesktopCalling() {
  const calling = getDesktopBridge()?.calling;
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: callingKey,
    queryFn: () => calling!.get(),
    enabled: Boolean(calling),
    staleTime: Infinity,
  });
  const save = useMutation({
    mutationFn: (onPhone: boolean) => calling!.set(onPhone),
    onMutate: (onPhone) => {
      const before = queryClient.getQueryData<DesktopCalling>(callingKey);
      if (before) queryClient.setQueryData<DesktopCalling>(callingKey, { ...before, onPhone });
      return before;
    },
    onSuccess: (next) => queryClient.setQueryData(callingKey, next),
    onError: (_error, _onPhone, before) => queryClient.setQueryData(callingKey, before),
  });
  return { calling: calling ? (data ?? null) : null, setOnPhone: (onPhone: boolean) => save.mutate(onPhone) };
}
