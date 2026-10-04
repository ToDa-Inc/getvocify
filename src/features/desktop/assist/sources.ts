import { streamObjectionSuggestion } from "@/features/copilot";
import type { ObjectionSuggestion } from "@/features/copilot/types";
import { objectionCard, streamedDraft, type AssistCard, type AssistSource } from "@/lib/live-assist";

/** Live objection handling from /copilot/suggest (the call's playbook and the rep's saved offer). */
const objectionSource: AssistSource = {
  id: "objection",
  request: (context, signal, onDraft) =>
    new Promise((resolve) => {
      let result: ObjectionSuggestion | null = null;
      let streamed = "";
      let draft: AssistCard | null = null;
      void streamObjectionSuggestion(
        {
          transcript_window: context.transcriptWindow,
          latest_turn: context.latestTurn,
          call_mode: context.callMode ?? "meeting",
          speaker_role: "prospect",
          ...(context.contactId && { contact_id: context.contactId }),
          ...(context.typeKey && { sales_motion_key: context.typeKey }),
        },
        (event) => {
          if (event.type === "restart") {
            // The server asks again without the playbook: what streamed so far was empty.
            streamed = "";
          } else if (event.type === "token" && onDraft) {
            streamed += event.text;
            // Once: the label and a loading state. The answer itself arrives whole, with the result.
            if (!draft) {
              draft = streamedDraft(streamed, context.latestTurn, Date.now());
              if (draft) onDraft(draft);
            }
          } else if (event.type === "result") {
            result = event.suggestion;
          }
        },
        signal,
      )
        .catch(() => undefined)
        .finally(() => resolve(signal.aborted ? null : objectionCard(result, Date.now(), context.latestTurn)));
    }),
};

/**
 * Every source asked after the other side speaks. Battle cards join this list as
 * their own AssistSource once the playbook endpoint exists; the panel needs no change.
 */
export const ASSIST_SOURCES: AssistSource[] = [objectionSource];
