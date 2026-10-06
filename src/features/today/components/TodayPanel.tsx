import { Link } from "react-router-dom";
import { Phone } from "lucide-react";
import { afterActionError, composeHome } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { useContactPriorities } from "@/features/today/hooks/useContactPriorities";
import { useHomeReads } from "@/features/today/hooks/useHomeReads";
import { forgetActed, useTodayCardActions } from "@/features/today/hooks/useTodayCardActions";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { splitByLane } from "@/lib/hoy-lanes";
import { todayConversationItems } from "@/lib/today";
import { useTodayCardActions, useTodayUndoClock } from "../hooks/useTodayCardActions";
import { ContactPriorities } from "./ContactPriorities";
import { TodayItemList } from "./TodayItemList";

/** `undefined` while the first read is in flight, `null` once it failed without data. */
function settled<T>(query: { data: T | undefined; isError: boolean }): T | null | undefined {
  return query.data ?? (query.isError ? null : undefined);
}

export function TodayPanel() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { surface, listed, dismiss, undo, contactsUrl, provider, portalId } = useTodayCardActions();
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
  const { calls: laneCalls, meetings: laneMeetings } = splitByLane(listed);
  const calls = todayConversationItems(laneCalls);
  const meetings = todayConversationItems(laneMeetings);
  const showLanes = listed.some((item) => item.lane === "calls" || item.lane === "meetings");
  const canStart = calls.length > 0 && (queue.mode === "idle" || queue.mode === "done");

  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-3`;

  return (
    <li className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 ${THEME_TOKENS.interaction.rowHover}`}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-foreground">{name}</p>
        {reason && <p className={`mt-px truncate text-[13px] ${THEME_TOKENS.typography.capsLabel}`}>{reason}</p>}
        {item.company_name && <p className={`mt-px truncate text-[13px] ${THEME_TOKENS.typography.capsLabel}`}>{item.company_name}</p>}
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
            showLanes ? (
              <div className="space-y-4">
                {calls.length > 0 ? (
                  <div className="space-y-2">
                    <p className={THEME_TOKENS.typography.capsLabel}>{t.product.todayLaneCalls}</p>
                    <TodayItemList
                      items={laneCalls}
                      onDismiss={dismiss}
                      onUndo={undo}
                      provider={provider}
                      portalId={portalId}
                    />
                  </div>
                ) : null}
                {meetings.length > 0 ? (
                  <div className="space-y-2">
                    <p className={THEME_TOKENS.typography.capsLabel}>{t.product.todayLaneMeetings}</p>
                    <TodayItemList
                      items={laneMeetings}
                      onDismiss={dismiss}
                      onUndo={undo}
                      provider={provider}
                      portalId={portalId}
                    />
                  </div>
                ) : null}
              </div>
            ) : (
              <TodayItemList
                items={listed}
                onDismiss={dismiss}
                onUndo={undo}
                provider={provider}
                portalId={portalId}
              />
            )
          ) : null}
        </div>
      ) : null}
      <ContactPriorities hideEmpty embedded />
    </section>
  );
}
