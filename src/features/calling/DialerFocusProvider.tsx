import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type DialerFocus = {
  contactId: string;
  name?: string | null;
};

type DialerFocusContextValue = {
  focus: DialerFocus | null;
  openForContact: (next: DialerFocus) => void;
  clearFocus: () => void;
};

const DialerFocusContext = createContext<DialerFocusContextValue | null>(null);

export function DialerFocusProvider({
  children,
  onOpenDialer,
}: {
  children: ReactNode;
  onOpenDialer: () => void;
}) {
  const [focus, setFocus] = useState<DialerFocus | null>(null);
  const openForContact = useCallback(
    (next: DialerFocus) => {
      setFocus(next);
      onOpenDialer();
    },
    [onOpenDialer],
  );
  const clearFocus = useCallback(() => setFocus(null), []);
  const value = useMemo(
    () => ({ focus, openForContact, clearFocus }),
    [focus, openForContact, clearFocus],
  );
  return <DialerFocusContext.Provider value={value}>{children}</DialerFocusContext.Provider>;
}

export function useDialerFocus(): DialerFocusContextValue {
  const ctx = useContext(DialerFocusContext);
  if (!ctx) {
    throw new Error("useDialerFocus must be used within DialerFocusProvider");
  }
  return ctx;
}

export function useOptionalDialerFocus(): DialerFocusContextValue | null {
  return useContext(DialerFocusContext);
}
