import { useEffect, useReducer, useState } from "react";
import { ListNumbers, Microphone, Phone, SignOut, SkipForward } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { currentItem, initialQueue, queueReducer } from "@/lib/today-queue";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { splitTodayItems } from "@/lib/today";
import { useTodayCardActions, useTodayUndoClock } from "../hooks/useTodayCardActions";
import { ContactPriorities } from "./ContactPriorities";
import { TodayItemList } from "./TodayItemList";

function formatStamp(iso: string, locale: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function TodayPanel() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { surface, listed, dismiss, confirm, undo, contactsUrl, provider, portalId } = useTodayCardActions();
  const dialer = useOptionalDialerFocus();
  useTodayUndoClock(surface.kind === "list");

  const [queue, dispatchQueue] = useReducer(queueReducer, initialQueue);
  const [captureOpen, setCaptureOpen] = useState(false);

  useEffect(() => {
    if (surface.kind !== "list") dispatchQueue({ type: "exit" });
  }, [surface.kind]);

  const active = queue.mode === "queue";
  const done = queue.mode === "done";
  const current = currentItem(queue);
  const calls = splitTodayItems(listed).calls;
  const canStart = calls.length > 0 && (queue.mode === "idle" || queue.mode === "done");

  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-3`;

  return (
    <section aria-labelledby="today-title" aria-busy={surface.kind === "loading"} className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="today-title" className={THEME_TOKENS.typography.sectionTitle}>{t.product.todayTitle}</h2>
        <div className="flex items-center gap-0.5">
          {canStart ? (
            <IconAction
              label={t.product.startCalling}
              onClick={() => dispatchQueue({ type: "start", items: calls })}
            >
              <ListNumbers size={16} weight="light" />
            </IconAction>
          ) : null}
          <IconAction
            label={t.product.today_capture}
            onClick={() => setCaptureOpen((open) => !open)}
          >
            <Microphone size={16} weight="light" />
          </IconAction>
        </div>
      </div>
      {captureOpen ? (
        <VoiceRecorderWidget
          quiet
          onComplete={(memoId) => navigate(`/dashboard/memos/${memoId}`)}
        />
      ) : null}
      {surface.kind === "loading" ? (
        <div className="space-y-3" aria-hidden="true">
          <div className={`h-16 ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`} />
          <div className={`h-16 ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`} />
          <div className={`h-16 ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`} />
        </div>
      ) : null}
      {surface.kind === "error" ? <p className={THEME_TOKENS.typography.body} role="alert">{surface.title}</p> : null}
      {surface.kind === "connect" ? (
        <div className={card}>
          <p className="text-[15px] text-foreground">{surface.title}</p>
          {surface.detail ? <p className={THEME_TOKENS.typography.body}>{surface.detail}</p> : null}
          {surface.action ? (
            <Button type="button" variant="outline" size="sm" onClick={() => navigate("/dashboard/settings/integrations")}>
              {surface.action}
            </Button>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "no-activity" ? (
        <div className={card}>
          <p className="text-[15px] text-foreground">{surface.title}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setCaptureOpen(true)}>
              {t.product.today_record}
            </Button>
            {contactsUrl ? (
              <a className="text-sm text-beige" href={contactsUrl} target="_blank" rel="noreferrer">
                {t.product.open_contacts}
              </a>
            ) : null}
          </div>
        </div>
      ) : null}
      {surface.kind === "incomplete" ? (
        <p className={THEME_TOKENS.typography.body}>{surface.title}{surface.generatedAt ? ` · ${formatStamp(surface.generatedAt, t.product.hourLocale)}` : ""}</p>
      ) : null}
      {surface.kind === "clear" ? <p className={THEME_TOKENS.typography.body}>{surface.title}</p> : null}
      {surface.kind === "list" ? (
        <div className="space-y-3">
          {surface.note ? <p className={THEME_TOKENS.typography.body}>{surface.note}{surface.generatedAt ? ` · ${formatStamp(surface.generatedAt, t.product.hourLocale)}` : ""}</p> : null}
          {active && current ? (
            <div className={card}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[15px] text-foreground">{current.contact_name || t.product.today_unknown_contact}</p>
                  {current.company_name ? <p className={THEME_TOKENS.typography.capsLabel}>{current.company_name}</p> : null}
                  <p className="mt-2 text-[15px] leading-relaxed text-foreground">{current.reason}</p>
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  {current.contact_id && dialer ? (
                    <IconAction
                      label={t.product.today_call}
                      onClick={() =>
                        dialer.openForContact({
                          contactId: current.contact_id as string,
                          name: current.contact_name ?? null,
                        })
                      }
                    >
                      <Phone size={16} weight="light" />
                    </IconAction>
                  ) : null}
                  <IconAction label={t.product.queueSkip} onClick={() => dispatchQueue({ type: "skip" })}>
                    <SkipForward size={16} weight="light" />
                  </IconAction>
                  <IconAction label={t.product.queueExit} onClick={() => dispatchQueue({ type: "exit" })}>
                    <SignOut size={16} weight="light" />
                  </IconAction>
                </div>
              </div>
            </div>
          ) : null}
          {done ? <p className={THEME_TOKENS.typography.body}>{t.product.queueDone}</p> : null}
          {!active ? (
            <TodayItemList
              items={listed}
              onDismiss={dismiss}
              onConfirm={confirm}
              onReview={(memoId) => navigate(`/dashboard/memos/${memoId}`)}
              onUndo={undo}
              provider={provider}
              portalId={portalId}
            />
          ) : null}
        </div>
      ) : null}
      <ContactPriorities hideEmpty embedded />
    </section>
  );
}
