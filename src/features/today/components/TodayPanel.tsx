import { useEffect, useReducer } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { currentItem, initialQueue, queueReducer } from "@/lib/today-queue";
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
  const { surface, listed, dismiss, undo, contactsUrl, provider, portalId } = useTodayCardActions();
  useTodayUndoClock(surface.kind === "list");

  const [queue, dispatchQueue] = useReducer(queueReducer, initialQueue);

  useEffect(() => {
    if (surface.kind !== "list") dispatchQueue({ type: "exit" });
  }, [surface.kind]);

  const active = queue.mode === "queue";
  const done = queue.mode === "done";
  const current = currentItem(queue);
  const canStart = listed.length > 0 && (queue.mode === "idle" || queue.mode === "done");

  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-3`;

  return (
    <section aria-labelledby="today-title" aria-busy={surface.kind === "loading"} className="space-y-4">
      <h2 id="today-title" className={THEME_TOKENS.typography.sectionTitle}>{t.product.todayTitle}</h2>
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
            <Button type="button" variant="outline" size="sm" onClick={() => document.getElementById("hoy-capture")?.scrollIntoView({ block: "nearest" })}>
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
          {canStart ? (
            <Button type="button" size="sm" onClick={() => dispatchQueue({ type: "start", items: listed })}>
              {t.product.startCalling}
            </Button>
          ) : null}
          {active && current ? (
            <div className={card}>
              <p className="text-[15px] leading-relaxed text-foreground">{current.reason}</p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => dispatchQueue({ type: "skip" })}>
                  {t.product.queueSkip}
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => dispatchQueue({ type: "exit" })}>
                  {t.product.queueExit}
                </Button>
              </div>
            </div>
          ) : null}
          {done ? <p className={THEME_TOKENS.typography.body}>{t.product.queueDone}</p> : null}
          {!active ? (
            <TodayItemList items={listed} onDismiss={dismiss} onUndo={undo} provider={provider} portalId={portalId} />
          ) : null}
          {surface.foldedCount > 0 ? (
            <p className={THEME_TOKENS.typography.body}>{t.product.today_folded.replace("{count}", String(surface.foldedCount))}</p>
          ) : null}
        </div>
      ) : null}
      <ContactPriorities hideEmpty embedded />
    </section>
  );
}
