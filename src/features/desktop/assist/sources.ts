import { streamObjectionSuggestion } from "@/features/copilot";
import type { ObjectionSuggestion } from "@/features/copilot/types";
import { draftCard, draftType, objectionCard, type AssistSource } from "@/lib/live-assist";

/** Live objection handling from /copilot/suggest (meeting mode, the rep's saved offer). */
const objectionSource: AssistSource = {
  id: "objection",
  request: (context, signal, onDraft) =>
    new Promise((resolve) => {
      let result: ObjectionSuggestion | null = null;
      let streamed = "";
      let drafted = false;
      void streamObjectionSuggestion(
        {
          transcript_window: context.transcriptWindow,
          latest_turn: context.latestTurn,
          call_mode: "meeting",
          speaker_role: "prospect",
          ...(context.contactId && { contact_id: context.contactId }),
        },
        (event) => {
          if (event.type === "token" && !drafted && onDraft) {
            streamed += event.text;
            const type = draftType(streamed);
            if (type) {
              drafted = true;
              onDraft(draftCard(type, context.latestTurn, Date.now()));
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
