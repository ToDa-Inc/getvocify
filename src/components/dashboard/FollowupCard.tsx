import "@shared/ui/components/v-followup.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { composeTarget } from "@shared/ui/compose.js";
import { flashCopied } from "@shared/ui/components/anim-icon.js";
import { memosApi } from "@/features/memos/api";
import type { FollowupView } from "@/features/memos/types";
import { useVElement, type VAction } from "@/hooks/use-v-element";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { htmlLang } from "@/lib/app-language";

const POLL_MS = 1500;
const MAIL_CLIENT_KEY = "vocify_mail_client";

function savedMailClient(): string | null {
  try {
    return localStorage.getItem(MAIL_CLIENT_KEY);
  } catch {
    return null;
  }
}

type FollowupElement = HTMLElement & { value: { subject: string; body: string } };

function openTarget(url: string) {
  if (url.startsWith("mailto:")) window.location.href = url;
  else window.open(url, "_blank", "noopener");
}

/**
 * The follow-up draft on the memo review, for the memo's author. `onSendReady` receives a send
 * that presses the card's own primary pill (its channel), or null when there is nothing to send.
 */
export function FollowupCard({
  memoId,
  onSendReady,
  onStatus,
  fallbackTo,
}: {
  memoId: string;
  /** The CRM contact picked on the update page; used when the call itself had no email. */
  fallbackTo?: string | null;
  onSendReady?: (send: (() => void) | null) => void;
  /** The draft's status, for the review's Email tab (shown while writing, ready or sent). */
  onStatus?: (status: FollowupView["status"] | null) => void;
}) {
  const { language, t } = useLanguage();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const uiLang = htmlLang(language);
  const sendFromVocify = Boolean(user?.company?.features?.includes("FOLLOWUP_SEND_ENABLED"));
  const [isSending, setIsSending] = useState(false);
  const { data } = useQuery({
    queryKey: ["memo-followup", memoId],
    queryFn: () => memosApi.getFollowup(memoId),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? POLL_MS : false),
  });

  const onAction = useCallback(
    async ({ action, value, element }: VAction) => {
      if (action === "client") {
        try {
          if (value) localStorage.setItem(MAIL_CLIENT_KEY, value);
        } catch {
          // the pick just isn't remembered
        }
        return;
      }
      if (isSending) return; // a send is already in flight: never fire a second one
      const view = queryClient.getQueryData<FollowupView>(["memo-followup", memoId]);
      if (!view) return;
      const { subject, body } = (element as FollowupElement).value;
      try {
        if (action === "copy") {
          await navigator.clipboard.writeText(body);
          flashCopied(element.querySelector('[data-action="copy"]'), t.product.askCopied);
          await memosApi.followupAction(memoId, { action: "copied", channel: "email", subject, body });
          return;
        }
        const channel = value === "whatsapp" ? "whatsapp" : "email";
        if (channel === "email" && sendFromVocify && (view.to || fallbackTo)) {
          setIsSending(true);
          try {
            const next = await memosApi.sendFollowup(memoId, { to: view.to || fallbackTo!, subject, body });
            queryClient.setQueryData(["memo-followup", memoId], next);
            toast.success(t.product.followupSentToast);
          } finally {
            setIsSending(false);
          }
          return;
        }
        const to = view.to || fallbackTo || undefined;
        const target = composeTarget({ channel, to, phone: view.phone, subject, body, mailClient: (value ?? undefined) as "default" | "gmail" | "outlook" | undefined });
        const url = target.ok ? target.url : target.fallback;
        if (!url) return;
        if (!target.ok) {
          await navigator.clipboard.writeText(body);
          toast(t.product.followupEmailBodyCopied);
        }
        openTarget(url);
        const next = await memosApi.followupAction(memoId, { action: "sent", channel, subject, body });
        queryClient.setQueryData(["memo-followup", memoId], next);
      } catch {
        toast.error(t.product.followupCompleteFailed);
      }
    },
    [memoId, queryClient, t.product, sendFromVocify, isSending, fallbackTo],
  );

  const view = useMemo(() => (data ? { ...data, mailClient: savedMailClient() } : data), [data]);
  const setElement = useVElement(view, onAction);
  const elementRef = useRef<FollowupElement | null>(null);
  const bindRef = useCallback(
    (node: FollowupElement | null) => {
      elementRef.current = node;
      setElement(node);
    },
    [setElement],
  );

  useEffect(() => {
    onStatus?.(data?.status ?? null);
  }, [onStatus, data?.status]);

  const canSend = data?.status === "ready" && Boolean(data.to || fallbackTo || data.phone) && !isSending;

  useEffect(() => {
    if (!onSendReady) return;
    onSendReady(
      canSend
        ? () => elementRef.current?.querySelector<HTMLButtonElement>('[data-action="send"].v-pill--primary')?.click()
        : null,
    );
    return () => onSendReady(null);
  }, [onSendReady, canSend]);

  if (!data || data.status === "unavailable" || data.status === "skipped") return null;
  return (
    <div className={`mb-4${isSending ? " opacity-60 pointer-events-none" : ""}`} aria-busy={isSending}>
      <v-followup ref={bindRef} lang={uiLang} />
    </div>
  );
}
