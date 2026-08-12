import { api } from "@/shared/lib/api-client";

export interface VoiceEnrollmentStatus {
  enrolled: boolean;
  rep_label: string;
  sample_count: number;
  consented_at: string | null;
  consent_version: string | null;
  script: string;
}

export async function fetchVoiceEnrollmentStatus(): Promise<VoiceEnrollmentStatus> {
  return api.get<VoiceEnrollmentStatus>("/voice-enrollment/status");
}

export async function saveVoiceEnrollment(input: {
  speaker_identifiers: string[];
  consent: boolean;
  sample_count?: number;
}): Promise<VoiceEnrollmentStatus> {
  return api.post<VoiceEnrollmentStatus>("/voice-enrollment/save", input);
}

export async function deleteVoiceEnrollment(): Promise<void> {
  await api.delete("/voice-enrollment/me");
}
