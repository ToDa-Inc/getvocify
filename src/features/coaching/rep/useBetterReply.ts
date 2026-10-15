import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";

export type BetterReplyRequest = {
  type: string;
  kind: "step" | "objection";
  key: string;
  memo_id: string;
  quote: string | null;
  response: string | null;
  reason: string | null;
};

/** The line the rep could have said at one moment, written from their playbook. Asked only for the
 * moment on screen and never again for the same one (the server keeps it a day, the browser the session). */
export function useBetterReply(request: BetterReplyRequest, enabled: boolean) {
  return useQuery({
    queryKey: ["rep-coaching", "better-reply", request.type, request.kind, request.key, request.memo_id],
    queryFn: () => api.post<{ say: string | null; reason: string | null }>("/coaching/me/better-reply", request, { timeoutMs: 40_000 }),
    enabled,
    retry: false,
    staleTime: Infinity,
  });
}
