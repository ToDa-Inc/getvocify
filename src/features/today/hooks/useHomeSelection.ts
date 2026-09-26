import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import {
  holdOrder,
  homeRows,
  homeSelection,
  homeSelectionLocked,
  initialHomeSelection,
  selectedRow,
  type HomeOrder,
  type HomeRow,
  type HomeSelection,
  type HomeView,
} from "@shared/ui/home.js";
import { HOME_KEYS, queueKeyAction } from "@shared/ui/queue.js";
import { useHomeColumn } from "@/components/dashboard/HomeColumn";
import type { CallEndedPayload } from "@/features/calling/DialerFocusProvider";
import type { CallResolvedEvent } from "@/lib/today-queue";
import { useWideScreen } from "./useWideScreen";

type OpenState = { needsOkOpen: boolean; groupOpen: boolean };

export function useHomeSelection(
  view: HomeView,
  open: OpenState,
  onPrimary: (row: HomeRow) => void,
) {
  const column = useHomeColumn();
  const wide = useWideScreen();
  const orderRef = useRef<HomeOrder | null>(null);
  const frozenViewRef = useRef<HomeView | null>(null);
  const [selection, dispatchSelection] = useReducer(homeSelection, initialHomeSelection);

  const held = useMemo(() => {
    if (selection.mode === "calling" || selection.mode === "review") {
      if (frozenViewRef.current) {
        return { view: frozenViewRef.current, order: orderRef.current };
      }
    }
    return holdOrder(orderRef.current, view);
  }, [view, selection.mode]);

  const stable = held.view;

  useEffect(() => {
    if (selection.mode === "calling" || selection.mode === "review") {
      if (!frozenViewRef.current) frozenViewRef.current = stable;
      return;
    }
    frozenViewRef.current = null;
    orderRef.current = held.order;
  }, [held.order, selection.mode, stable]);

  const rows = useMemo(
    () => homeRows(stable, { needsOkOpen: open.needsOkOpen, groupOpen: open.groupOpen }),
    [stable, open.needsOkOpen, open.groupOpen],
  );

  useEffect(() => {
    dispatchSelection({ type: "rows", rows, wide });
  }, [rows, wide]);

  const row = useMemo(() => selectedRow(selection, rows), [selection, rows]);
  const selectedKey = row?.key ?? null;
  const sheetOpen = Boolean(row) && !wide;
  const locked = homeSelectionLocked(selection);

  const select = useCallback(
    (key: string) => {
      if (locked) return;
      dispatchSelection({ type: "select", key });
    },
    [locked],
  );

  const clear = useCallback(() => {
    dispatchSelection({ type: "exit" });
  }, []);

  const moveNext = useCallback(() => dispatchSelection({ type: "next" }), []);
  const movePrev = useCallback(() => dispatchSelection({ type: "prev" }), []);
  const skip = useCallback(() => dispatchSelection({ type: "skip" }), []);
  const finishReview = useCallback(() => dispatchSelection({ type: "reviewed" }), []);
  const lockOnCall = useCallback((key: string) => dispatchSelection({ type: "call", key }), []);

  const onCallEnded = useCallback((payload: CallEndedPayload) => {
    dispatchSelection({
      type: "call_ended",
      answered: payload.answered,
      callSid: payload.callSid,
      memoId: payload.memoId,
      screeningOutcome: payload.screeningOutcome,
      callStatus: payload.callStatus,
    });
  }, []);

  const resolveCall = useCallback((event: CallResolvedEvent) => {
    dispatchSelection({ type: "call_resolved", ...event });
  }, []);

  const primaryRef = useRef(onPrimary);
  primaryRef.current = onPrimary;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (column?.askOpen) {
        if (event.key === "Escape") {
          event.preventDefault();
          column.closeAsk();
        }
        return;
      }
      const action = queueKeyAction(selection.mode, event.key, event, HOME_KEYS);
      if (!action) return;
      event.preventDefault();
      if (action === "call") {
        if (row) primaryRef.current(row);
        return;
      }
      if (action === "reviewed") {
        finishReview();
        return;
      }
      if (action === "next") moveNext();
      else if (action === "prev") movePrev();
      else if (action === "skip") skip();
      else if (action === "exit") clear();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [column, selection.mode, row, moveNext, movePrev, skip, clear, finishReview]);

  return {
    view: stable,
    rows,
    row,
    selectedKey,
    wide,
    sheetOpen,
    locked,
    select,
    clear,
    lockOnCall,
    onCallEnded,
    resolveCall,
    finishReview,
    selection: selection as HomeSelection,
  };
}
