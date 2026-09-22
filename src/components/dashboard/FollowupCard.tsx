import "@shared/ui/components/v-followup.js";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { composeTarget } from "@shared/ui/compose.js";
import { memosApi } from "@/features/memos/api";
import type { FollowupView } from "@/features/memos/types";
import { useVElement, type VAction } from "@/hooks/use-v-element";

const POLL_MS = 1500;

type FollowupElement = HTMLElement & { value: { subject: string; body: string } };

function openTarget(url: string) {
  if (url.startsWith("mailto:")) window.location.href = url;
  else window.open(url, "_blank", "noopener");
}

/** The follow-up draft on the memo review, for the memo's author. */
export function FollowupCard({ memoId }: { memoId: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["memo-followup", memoId],
    queryFn: () => memosApi.getFollowup(memoId),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? POLL_MS : false),
  });

  const onAction = useCallback(
    async ({ action, value, element }: VAction) => {
      const view = queryClient.getQueryData<FollowupView>(["memo-followup", memoId]);
      if (!view) return;
      const { subject, body } = (element as FollowupElement).value;
      try {
        if (action === "copy") {
          await navigator.clipboard.writeText(body);
          toast.success("Follow-up copied");
          await memosApi.followupAction(memoId, { action: "copied", channel: "email", subject, body });
          return;
        }
        const channel = value === "whatsapp" ? "whatsapp" : "email";
        const target = composeTarget({ channel, to: view.to, phone: view.phone, subject, body });
        const url = target.ok ? target.url : target.fallback;
        if (!url) return;
        if (!target.ok) {
          await navigator.clipboard.writeText(body);
          toast("Email body copied: paste it into the draft");
        }
        openTarget(url);
        const next = await memosApi.followupAction(memoId, { action: "sent", channel, subject, body });
        queryClient.setQueryData(["memo-followup", memoId], next);
      } catch {
        toast.error("Could not complete the follow-up");
      }
    },
    [memoId, queryClient],
  );

  const ref = useVElement(data, onAction);
  if (!data || data.status === "unavailable") return null;
  return (
    <div className="mb-4">
      <v-followup ref={ref} />
    </div>
  );
}
