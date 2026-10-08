/**
 * Types by channel (spec 2026-10-07): a recording is a call or a meeting, and its type is one of
 * that channel's types, with or without a playbook. The server says it is on by sending
 * `type_detection` with GET /playbooks, and each type's `channels` in its details.
 *
 * No `@/` imports: this file runs under node --test.
 */
import { INTERNAL_KEY, type TypeOption } from "./interactions.ts";

export type LiveChannel = "call" | "meeting";
export const LIVE_CHANNELS: LiveChannel[] = ["call", "meeting"];
export type TypeDetection = { by_channel: boolean; call_reading: boolean };

type Payload = {
  details?: Record<string, { channels?: string[] | null } | undefined>;
  type_detection?: TypeDetection;
} | null | undefined;

/** A paused type is switched off; a deleted one is not listed at all. */
const DETECTABLE = new Set(["published", "draft", "missing"]);

export function byChannel(payload: unknown): boolean {
  return Boolean((payload as Payload)?.type_detection);
}

export function channelsOf(payload: unknown, key: string): LiveChannel[] {
  const named = ((payload as Payload)?.details?.[key]?.channels ?? []).filter((channel): channel is LiveChannel =>
    LIVE_CHANNELS.includes(channel as LiveChannel),
  );
  return named.length ? named : [...LIVE_CHANNELS];
}

/** The types a recording on `kind` can be (keeping the order of `options`), then Interna. */
export function channelTypeOptions(options: TypeOption[], payload: unknown, kind: string | null | undefined): TypeOption[] {
  const live = LIVE_CHANNELS.includes(kind as LiveChannel) ? (kind as LiveChannel) : null;
  const types = live
    ? options.filter(
        (option) =>
          option.key !== INTERNAL_KEY && DETECTABLE.has(option.status ?? "") && channelsOf(payload, option.key).includes(live),
      )
    : [];
  return [...types, ...options.filter((option) => option.key === INTERNAL_KEY)];
}

/** Settings → Tipos: the keys under Llamadas and under Reuniones, in the order given. */
export function channelGroups(keys: string[], payload: unknown): Record<LiveChannel, string[]> {
  return {
    call: keys.filter((key) => channelsOf(payload, key).includes("call")),
    meeting: keys.filter((key) => channelsOf(payload, key).includes("meeting")),
  };
}

export function otherChannel(kind: LiveChannel): LiveChannel {
  return kind === "call" ? "meeting" : "call";
}
