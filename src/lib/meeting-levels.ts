import { useSyncExternalStore } from "react";

export type Levels = { you: number; them: number };

/**
 * Each side's loudness during a recording (0–1), outside React state. It changes up to eight times a second while
 * anyone talks; held in the recording's context it re-rendered everything that reads the recording (the live view, both
 * transcripts, live help) at that rate for the whole call. Only what draws or reads a level subscribes to it.
 */
export class MeetingLevels {
  private value: Levels = { you: 0, them: 0 };
  private readonly listeners = new Set<() => void>();

  get = (): Levels => this.value;

  /** Sets both sides; listeners hear only a change. */
  set(next: Levels): void {
    if (next.you === this.value.you && next.them === this.value.them) return;
    this.value = next;
    for (const listener of this.listeners) listener();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };
}

/** The levels, for a component that draws them: it alone re-renders when they move. */
export function useMeetingLevels(levels: MeetingLevels): Levels {
  return useSyncExternalStore(levels.subscribe, levels.get);
}
