import { api } from "@/shared/lib/api-client";
import { createLiveTicketCache, type LiveTicket } from "@/lib/live-ticket";

/** The live transcription pass for this session of the app: shared by a call that rings and the live session it starts. */
export const liveTickets = createLiveTicketCache(() => api.post<LiveTicket>("/transcription/ticket"));
