import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useTodayCardActions, useTodayUndoClock } from "../hooks/useTodayCardActions";
import { TodayItemList } from "./TodayItemList";

export function TodayPanel() {
  const navigate = useNavigate();
  const { surface, listed, dismiss, undo } = useTodayCardActions();
  useTodayUndoClock(surface.kind === "list");

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
          <TodayItemList items={listed} onDismiss={dismiss} onUndo={undo} />
        </div>
      ) : null}
    </section>
  );
}
