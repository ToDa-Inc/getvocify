/**
 * The calls the rep has finished and the island is still showing as "being finished": the rep can already be on the next
 * recording or call, and each of these tells where its own memo is. One list, plain functions: the provider holds it.
 */

export type JobState = "working" | "needs" | "failed" | "followup" | "done";

export type AfterCallJob = {
  /** The draft's id (a recording or meeting) or the call's sid (a Vocify call). */
  id: string;
  name: string | null;
  state: JobState;
  memoId: string | null;
  /** Opens its own card when it is ready, as before: only until the rep starts something else. */
  autoOpen: boolean;
};

export type IslandJob = { id: string; name: string | null; state: JobState };

export const addJob = (jobs: AfterCallJob[], job: AfterCallJob): AfterCallJob[] => [...jobs.filter((j) => j.id !== job.id), job];
export const patchJob = (jobs: AfterCallJob[], id: string, patch: Partial<AfterCallJob>): AfterCallJob[] => jobs.map((j) => (j.id === id ? { ...j, ...patch } : j));
export const dropJob = (jobs: AfterCallJob[], id: string): AfterCallJob[] => jobs.filter((j) => j.id !== id);
/** The rep took up something else: what is ready waits for them instead of appearing over it. */
export const stopAutoOpen = (jobs: AfterCallJob[]): AfterCallJob[] => (jobs.some((j) => j.autoOpen) ? jobs.map((j) => (j.autoOpen ? { ...j, autoOpen: false } : j)) : jobs);
/** What the island is told: no more than it draws. */
export const forIsland = (jobs: AfterCallJob[]): IslandJob[] => jobs.map(({ id, name, state }) => ({ id, name, state }));

type Memo = { status?: string | null; screeningOutcome?: string | null; hubspotContactId?: string | null };

/**
 * Where a memo that is no longer being processed leaves its job. A call nobody answered has nothing to review: with a CRM
 * contact it still offers a follow-up (the lead status, a task), without one it is done.
 */
export function stateOfMemo(memo: Memo, crmConnected: boolean, noConversation: boolean): JobState {
  if (noConversation) return memo.hubspotContactId && crmConnected ? "followup" : "done";
  if (memo.status === "failed") return "failed";
  return memo.status === "pending_review" ? "needs" : "done";
}
