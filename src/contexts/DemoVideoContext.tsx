import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { DemoVideoDialog } from "@/components/landing/DemoVideoDialog";

type DemoVideoContextValue = {
  openDemo: () => void;
};

const DemoVideoContext = createContext<DemoVideoContextValue | null>(null);

export function DemoVideoProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const value = useMemo(() => ({ openDemo: () => setOpen(true) }), []);

  return (
    <DemoVideoContext.Provider value={value}>
      {children}
      <DemoVideoDialog open={open} onOpenChange={setOpen} />
    </DemoVideoContext.Provider>
  );
}

export function useDemoVideo() {
  const ctx = useContext(DemoVideoContext);
  if (!ctx) {
    throw new Error("useDemoVideo must be used within DemoVideoProvider");
  }
  return ctx;
}
