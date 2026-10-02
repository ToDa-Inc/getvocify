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

/** Words in the conversation before the first proposal (both sides; roughly the first minute). */
export const FIRST_PROPOSAL_WORDS = 150;
/** Words before the second and last proposal, only when the first was unsure. */
export const SECOND_PROPOSAL_WORDS = 350;

export function withProposal(state: CallTypeState, key: string | null): CallTypeState {
  return key ? { ...state, vocify: key } : state;
}

/** A type the rep chose, or null for "let Vocify decide". */
export function withPick(state: CallTypeState, key: string | null): CallTypeState {
  return { ...state, rep: key };
}

/** What the island's chip shows: the type, and whether it is still Vocify's proposal. */
export function callTypeShown(state: CallTypeState): { key: string | null; proposed: boolean } {
  if (state.rep) return { key: state.rep, proposed: false };
  return { key: state.vocify, proposed: Boolean(state.vocify) };
}

/** At most two proposals a call, none once the rep picked: the type never costs more model calls. */
export function proposalDue(input: { words: number; attempts: number; picked: boolean; lastConfident: boolean }): boolean {
  if (input.picked) return false;
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
 * Call or meeting: the app the call happens in says which; without it, a recording with the CRM
 * contact on screen is that contact's call. One answer for live help and the memo.
 */
export function callKind(draft: { source?: { kind: string | null } | null; contact?: unknown }): "call" | "meeting" {
  const kind = draft.source?.kind;
  if (kind === "call" || kind === "meeting") return kind;
  return draft.contact ? "call" : "meeting";
}
