/**
 * The call type (which playbook) during a live call on the Mac. Vocify proposes it (a free guess
 * at the start, then one model proposal once the conversation says enough); the rep's pick is
 * final. Live help and the memo use whatever type the call has.
 *
 * No `@/` imports: this file runs under node --test.
 */

export type CallTypeState = {
  /** Vocify's latest proposal (the guess at the start, then the model's). */
  vocify: string | null;
  /** The rep's pick: final while set. */
  rep: string | null;
};

export const NO_CALL_TYPE: CallTypeState = { vocify: null, rep: null };

const INTERNAL_KEY = "internal";

/** Words in the conversation before the first proposal (both sides; about half a minute of talk:
 * the 2026-10-03 test call reached 150 only at its last objection, so help ran on the guess). */
export const FIRST_PROPOSAL_WORDS = 70;
/** Words before the second and last proposal, only when the first was unsure. */
export const SECOND_PROPOSAL_WORDS = 200;

export function withProposal(state: CallTypeState, key: string | null): CallTypeState {
  return key ? { ...state, vocify: key } : state;
}

/** A type the rep chose, or null for "let Vocify decide". */
export function withPick(state: CallTypeState, key: string | null): CallTypeState {
  return { ...state, rep: key };
}

/** After a channel switch: a type (Vocify's or the rep's) that is not one of the new channel's is dropped. */
export function withChannelTypes(state: CallTypeState, allowed: readonly string[]): CallTypeState {
  return {
    vocify: state.vocify && allowed.includes(state.vocify) ? state.vocify : null,
    rep: state.rep && allowed.includes(state.rep) ? state.rep : null,
  };
}

/** What the island's chip shows: the type, and whether it is still Vocify's proposal. */
export function callTypeShown(state: CallTypeState): { key: string | null; proposed: boolean } {
  if (state.rep) return { key: state.rep, proposed: false };
  return { key: state.vocify, proposed: Boolean(state.vocify) };
}

/** Who chose the type the memo is sent with: the rep's pick is theirs; Vocify's suggestion stays one,
 * so the call reading after the call can still correct it. */
export type TypeSource = "rep" | "vocify";

export function typeForMemo(state: CallTypeState): { key: string; source: TypeSource } | null {
  if (state.rep) return { key: state.rep, source: "rep" };
  return state.vocify ? { key: state.vocify, source: "vocify" } : null;
}

/** Proposals in one call whatever happens: a channel switch starts the two again, up to this many. */
export const MAX_PROPOSALS_PER_CALL = 4;

/** At most two proposals per channel, none once the rep picked, never more than MAX_PROPOSALS_PER_CALL
 * in the call (`total`): the type never costs more model calls. */
export function proposalDue(input: { words: number; attempts: number; picked: boolean; lastConfident: boolean; total?: number }): boolean {
  if (input.picked || (input.total ?? 0) >= MAX_PROPOSALS_PER_CALL) return false;
  if (input.attempts === 0) return input.words >= FIRST_PROPOSAL_WORDS;
  if (input.attempts === 1) return !input.lastConfident && input.words >= SECOND_PROPOSAL_WORDS;
  return false;
}

/** The call_mode /copilot/suggest routes by: the platform that caught the call decides it. */
export function assistCallMode(kind: string | null | undefined): "softphone" | "meeting" {
  return kind === "call" ? "softphone" : "meeting";
}

/** Live help runs when the remembered setting (or this call's switch) says so, never on an internal call. */
export function liveHelpActive(input: { remembered: boolean; override: boolean | null; typeKey: string | null }): boolean {
  if (input.typeKey === INTERNAL_KEY) return false;
  return input.override ?? input.remembered;
}

/**
 * Call or meeting: the channel the rep switched to on the island, else the app the call happens
 * in, else a recording with the CRM contact on screen is that contact's call. One answer for live
 * help and the memo.
 */
export function callKind(draft: {
  channel?: "call" | "meeting";
  source?: { kind: string | null } | null;
  contact?: unknown;
}): "call" | "meeting" {
  if (draft.channel) return draft.channel;
  const kind = draft.source?.kind;
  if (kind === "call" || kind === "meeting") return kind;
  return draft.contact ? "call" : "meeting";
}
