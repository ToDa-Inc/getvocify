import { useEffect, useReducer } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { currentItem, initialQueue, queueReducer } from "@/lib/today-queue";
import { useTodayCardActions, useTodayUndoClock } from "../hooks/useTodayCardActions";
import { TodayItemList } from "./TodayItemList";

export function TodayPanel() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { surface, listed, dismiss, undo } = useTodayCardActions();
  useTodayUndoClock(surface.kind === "list");

  const [queue, dispatchQueue] = useReducer(queueReducer, initialQueue);

  useEffect(() => {
    if (surface.kind !== "list") dispatchQueue({ type: "exit" });
  }, [surface.kind]);

  const active = queue.mode === "queue";
  const done = queue.mode === "done";
  const current = currentItem(queue);
  const canStart = listed.length > 0 && queue.mode === "idle";

  return (
    <section aria-labelledby="today-title" aria-busy={surface.kind === "loading"} className="space-y-3">
      <h2 id="today-title" className={THEME_TOKENS.typography.pageTitle}>Hoy</h2>
      {surface.kind === "loading" ? (
        <div className="space-y-3" aria-hidden="true">
          <div className="h-16 rounded-lg border" />
          <div className="h-16 rounded-lg border" />
          <div className="h-16 rounded-lg border" />
        </div>
      ) : null}
      {surface.kind === "error" ? <p role="alert">{surface.title}</p> : null}
      {surface.kind === "connect" ? (
        <div>
          <p>{surface.title}</p>
          {surface.detail ? <p>{surface.detail}</p> : null}
          {surface.action ? (
            <Button type="button" variant="outline" onClick={() => navigate("/dashboard/settings/integrations")}>
              {surface.action}
            </Button>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "no-activity" ? <p>{surface.title}</p> : null}
      {surface.kind === "incomplete" ? (
        <p>{surface.title}{surface.generatedAt ? ` · ${surface.generatedAt}` : ""}</p>
      ) : null}
      {surface.kind === "clear" ? <p>{surface.title}</p> : null}
      {surface.kind === "list" ? (
        <div className="space-y-3">
          {surface.note ? <p>{surface.note}{surface.generatedAt ? ` · ${surface.generatedAt}` : ""}</p> : null}
          {canStart ? (
            <Button type="button" onClick={() => dispatchQueue({ type: "start", items: listed })}>
              {t.product.startCalling}
            </Button>
          ) : null}
          {active && current ? (
            <div className="rounded-lg border p-4">
              <p>{current.reason}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={() => dispatchQueue({ type: "skip" })}>
                  {t.product.queueSkip}
                </Button>
                <Button type="button" variant="outline" onClick={() => dispatchQueue({ type: "exit" })}>
                  {t.product.queueExit}
                </Button>
              </div>
            </div>
          ) : null}
          {done ? <p>{t.product.queueDone}</p> : null}
          {!active ? (
            <TodayItemList items={listed} onDismiss={dismiss} onUndo={undo} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
