export type {
  ObjectionSuggestion,
  ObjectionType,
  CallMode,
  SuggestRequest,
} from "./types";
export {
  DEFAULT_PRODUCT_CONTEXT,
  PRODUCT_CONTEXT_STORAGE_KEY,
} from "./types";
export { streamObjectionSuggestion } from "./api/suggest";
export { useTurnDetector } from "./hooks/useTurnDetector";
export type { SpeakerRole, TurnMeta } from "./hooks/useTurnDetector";
export { useObjectionSuggestions } from "./hooks/useObjectionSuggestions";
export { SuggestionCard } from "./components/SuggestionCard";
export { CopilotControls } from "./components/CopilotControls";
export { VoiceEnrollmentPanel } from "./components/VoiceEnrollmentPanel";
export {
  fetchVoiceEnrollmentStatus,
  saveVoiceEnrollment,
  deleteVoiceEnrollment,
} from "./api/voiceEnrollment";
export type { VoiceEnrollmentStatus } from "./api/voiceEnrollment";
