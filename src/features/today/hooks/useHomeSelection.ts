import { useCallback, useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from "react";
import {
  HOME_WIDE_PX,
  holdOrder,
  homeRows,
  homeSelection,
  initialHomeSelection,
  selectedRow,
  type HomeOrder,
  type HomeRow,
  type HomeSelection,
  type HomeView,
} from "@shared/ui/home.js";
import { HOME_KEYS, queueKeyAction } from "@shared/ui/queue.js";
import { useHomeColumn } from "@/components/dashboard/HomeColumn";

function useWideScreen() {
  const subscribe = useCallback((onStore: () => void) => {
    const mq = window.matchMedia(`(min-width: ${HOME_WIDE_PX}px)`);
    mq.addEventListener("change", onStore);
    return () => mq.removeEventListener("change", onStore);
  }, []);
  const getSnapshot = useCallback(
    () => window.matchMedia(`(min-width: ${HOME_WIDE_PX}px)`).matches,
    [],
  );
  const getServerSnapshot = useCallback(() => true, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

type OpenState = { needsOkOpen: boolean; groupOpen: boolean };

export function useHomeSelection(
  view: HomeView,
  open: OpenState,
  onPrimary: (row: HomeRow) => void,
) {
  const column = useHomeColumn();
  const wide = useWideScreen();
  const orderRef = useRef<HomeOrder | null>(null);
  const [stable, setStable] = useState(view);

  useEffect(() => {
    const next = holdOrder(orderRef.current, view);
    orderRef.current = next.order;
    setStable(next.view);
  }, [view]);

  const rows = useMemo(
    () => homeRows(stable, { needsOkOpen: open.needsOkOpen, groupOpen: open.groupOpen }),
    [stable, open.needsOkOpen, open.groupOpen],
  );

  const [selection, dispatchSelection] = useReducer(homeSelection, initialHomeSelection);

  useEffect(() => {
    dispatchSelection({ type: "rows", rows, wide });
  }, [rows, wide]);

  const row = useMemo(() => selectedRow(selection, rows), [selection, rows]);
  const selectedKey = row?.key ?? null;
  const sheetOpen = Boolean(row) && !wide;

  const select = useCallback((key: string) => {
    dispatchSelection({ type: "select", key });
  }, []);

  const clear = useCallback(() => {
    dispatchSelection({ type: "exit" });
  }, []);

  const moveNext = useCallback(() => dispatchSelection({ type: "next" }), []);
  const movePrev = useCallback(() => dispatchSelection({ type: "prev" }), []);
  const skip = useCallback(() => dispatchSelection({ type: "skip" }), []);

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
      if (action === "next") moveNext();
      else if (action === "prev") movePrev();
      else if (action === "skip") skip();
      else if (action === "exit") clear();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [column, selection.mode, row, moveNext, movePrev, skip, clear]);

  return {
    view: stable,
    rows,
    row,
    selectedKey,
    wide,
    sheetOpen,
    select,
    clear,
    selection: selection as HomeSelection,
  };
}
