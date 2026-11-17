import { useLive, type LiveValue } from "@/lib/meeting-levels";

/** The recording's clock: it alone re-renders each second. `paused`: the word shown before it while paused. */
export function Elapsed({ clock, paused }: { clock: LiveValue<string>; paused?: string | null }) {
  const time = useLive(clock);
  return <>{paused ? `${paused} · ${time}` : time}</>;
}
