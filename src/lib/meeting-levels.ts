import { useSyncExternalStore } from "react";

export type Levels = { you: number; them: number };

/**
 * A value that changes during a recording without passing through React state: the levels (up to eight times a second
 * while anyone talks) and the clock (every second). Held in the recording's context they re-rendered everything that
 * reads the recording (the live view, both transcripts, live help) at that rate for the whole call. Only what draws or
 * reads one subscribes to it.
 */
export class LiveValue<T> {
  private value: T;
  private readonly same: (a: T, b: T) => boolean;
  private readonly listeners = new Set<() => void>();

  constructor(initial: T, same: (a: T, b: T) => boolean = Object.is) {
    this.value = initial;
    this.same = same;
  }

  get = (): T => this.value;

  /** Listeners hear only a change. */
  set(next: T): void {
    if (this.same(next, this.value)) return;
    this.value = next;
    for (const listener of this.listeners) listener();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };
}

/** Each side's loudness during a recording (0–1). */
export class MeetingLevels extends LiveValue<Levels> {
  constructor() {
    super({ you: 0, them: 0 }, (a, b) => a.you === b.you && a.them === b.them);
  }
}

/** A live value, for a component that draws it: it alone re-renders when it changes. */
export function useLive<T>(value: LiveValue<T>): T {
  return useSyncExternalStore(value.subscribe, value.get);
}

/** The levels, for a component that draws them. */
export function useMeetingLevels(levels: MeetingLevels): Levels {
  return useLive(levels);
}
