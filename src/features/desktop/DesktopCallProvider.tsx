import { useEffect, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { useCallingConfig } from "@/features/calls/useCallingConfig";
import { callEngine } from "@/features/calling/callEngine";
import { useDesktopMeeting } from "@/features/desktop/DesktopMeetingProvider";
import { api } from "@/shared/lib/api-client";
import { ROUTES } from "@/shared/lib/constants";
import { companyCanUseDialer } from "@/lib/billing-access";
import { latestOnly, type CallPreview } from "@/lib/call-contact";
import { isCallEnded, isCallUp, type CallEngineState } from "@/lib/call-engine-state";
import {
  ENDED_HOLD_MS,
  crmRecordKey,
  dialIsland,
  dialTargetFor,
  onScreenFromPreview,
  outgoingCallerId,
  parseCallCommand,
  type CallingAccess,
} from "@/lib/desktop-call";
import { getDesktopBridge } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";

/**
 * Calling the CRM contact on screen from the desktop island (desktop host only).
 *
 * The shell sends `crm:screen` when the frontmost browser's CRM page changes and the island's
 * call commands; this turns them into `onScreen` / `dial` shell state and `callEngine` calls, and
 * runs the live transcript from the call's own two sides once it is answered.
 */
export function DesktopCallProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useLanguage();
  const { config } = useCallingConfig();
  const meeting = useDesktopMeeting();

  const access: CallingAccess = {
    canDial: companyCanUseDialer(user?.company) && config?.enabled !== false,
    callerId: outgoingCallerId(config?.callerIds),
  };
  const accessRef = useRef(access);
  accessRef.current = access;
  const previewRef = useRef<CallPreview | null>(null);
  const copyRef = useRef(t.product);
  copyRef.current = t.product;
  const meetingRef = useRef(meeting);
  meetingRef.current = meeting;

  // The CRM record in the frontmost browser → who the island offers to call.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.crm?.onScreen) return;
    const lookups = latestOnly();
    let shownKey: string | null = null;
    return bridge.crm.onScreen(({ urls }) => {
      // Moving around inside the same record (its tabs, a query string) keeps the offer as it is.
      const key = urls[0] ? crmRecordKey(urls[0]) : null;
      if (key && key === shownKey) return;
      const ticket = lookups.next();
      // Another record: the old offer goes at once, so a quick click can never call the previous contact.
      shownKey = null;
      previewRef.current = null;
      bridge.shell.setState({ onScreen: null });
      if (!urls.length || !api.getToken()) return;
      api
        .post<CallPreview>("/live-calls/preview", { page_urls: urls })
        .then((preview) => {
          if (!lookups.isLatest(ticket)) return;
          shownKey = key;
          previewRef.current = preview;
          bridge.shell.setState({ onScreen: onScreenFromPreview(preview, accessRef.current) });
        })
        .catch(() => {
          // Unknown contact: no phone offer rather than a wrong one.
          if (lookups.isLatest(ticket)) bridge.shell.setState({ onScreen: null });
        });
    });
  }, []);

  // The plan or the caller ID changed (e.g. the rep just verified a number): redraw the offer.
  const { canDial, callerId } = access;
  useEffect(() => {
    if (!previewRef.current) return;
    getDesktopBridge()?.shell.setState({ onScreen: onScreenFromPreview(previewRef.current, { canDial, callerId }) });
  }, [canDial, callerId]);

  // The island's call commands.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge) return;
    return bridge.shell.onCommand((name) => {
      const command = parseCallCommand(name);
      if (!command) return;
      if (command.kind === "dial") {
        // Never on top of a meeting being recorded (the island only offers it at rest, but say so anyway).
        if (meetingRef.current.phase !== "idle") return;
        const target = dialTargetFor(previewRef.current, accessRef.current);
        if (target) void callEngine.dial(target, copyRef.current);
      } else if (command.kind === "hangup") {
        callEngine.hangup();
      } else if (command.kind === "mute") {
        callEngine.setMuted(command.muted);
      } else if (command.kind === "digit") {
        callEngine.sendDigits(command.digit);
      } else if (command.kind === "open-calling") {
        navigate(ROUTES.CALLING);
        bridge.shell.command("show");
      }
    });
  }, [navigate]);

  // The call (from the island or the dock) → the island, and the live session while it is answered.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge) return;
    let previous: CallEngineState = callEngine.getState();
    let holdTimer = 0;
    const onCall = (state: CallEngineState) => {
      bridge.shell.setState({ dial: dialIsland(state) });
      const target = state.target;
      if (previous.phase !== "active" && state.phase === "active" && target) {
        const streams = callEngine.streams();
        if (streams && state.callSid) {
          navigate(ROUTES.RECORD);
          void meetingRef.current.startCall({
            callSid: state.callSid,
            streams,
            contact: target.contactId ? { hubspotId: target.contactId, name: target.name } : null,
          });
        }
      }
      if (isCallUp(previous) && isCallEnded(state)) {
        if (state.answered) {
          if (meetingRef.current.phase === "live") void meetingRef.current.stop();
          else if (state.callSid) meetingRef.current.followCall(state.callSid, target?.name ?? null);
          callEngine.reset();
        } else {
          window.clearTimeout(holdTimer);
          holdTimer = window.setTimeout(() => callEngine.reset(), ENDED_HOLD_MS);
        }
      }
      previous = state;
    };
    const unsubscribe = callEngine.subscribe(onCall);
    return () => {
      window.clearTimeout(holdTimer);
      unsubscribe();
    };
  }, [navigate]);

  return <>{children}</>;
}
