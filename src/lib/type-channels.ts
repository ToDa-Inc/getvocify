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
  details?: Record<string, { channels?: string[] | null; applies_to?: { channels?: string[] | null } | null } | undefined>;
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

/** The channels a type is listed under in "Playbook", whatever the company's mode: its own
 * `channels` when types go by channel, else the channels of its routing rule (a visit is a meeting).
 * A type with none is both. */
export function railChannels(payload: unknown, key: string): LiveChannel[] {
  const detail = (payload as Payload)?.details?.[key];
  const own = (detail?.channels ?? []).filter((channel): channel is LiveChannel => LIVE_CHANNELS.includes(channel as LiveChannel));
  if (own.length) return own;
  const rule = detail?.applies_to?.channels ?? [];
  const mapped = LIVE_CHANNELS.filter((channel) => rule.includes(channel) || (channel === "meeting" && rule.includes("visit")));
  return mapped.length ? mapped : [...LIVE_CHANNELS];
}

/** The rule channels a tab stands for: "Reuniones" also covers visits. */
export function ruleChannelsOf(channel: LiveChannel): string[] {
  return channel === "meeting" ? ["meeting", "visit"] : ["call"];
}

/** Which of the three texts says where a type is used: "Llamadas", "Reuniones" or "Llamadas y reuniones". */
export function channelsLabelKey(channels: LiveChannel[]): "call" | "meeting" | "both" {
  const call = channels.includes("call");
  const meeting = channels.includes("meeting");
  return call && !meeting ? "call" : meeting && !call ? "meeting" : "both";
}
