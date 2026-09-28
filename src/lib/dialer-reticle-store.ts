export type DialerReticleState = {
  phase: string;
  contactId: string | null;
  contactName: string | null;
  callSid: string | null;
  elapsed: string;
};

const empty: DialerReticleState = {
  phase: "idle",
  contactId: null,
  contactName: null,
  callSid: null,
  elapsed: "0:00",
};

let state = empty;
const listeners = new Set<() => void>();

export const dialerReticleStore = {
  getState: () => state,
  setState: (next: Partial<DialerReticleState>) => {
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  },
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  reset: () => {
    state = empty;
    listeners.forEach((listener) => listener());
  },
};
