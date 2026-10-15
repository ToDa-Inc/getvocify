import { api } from "@/shared/lib/api-client";
import type { DemoTurn } from "@/lib/demo-session";

export type DemoLanguage = "es" | "en";

export interface DemoPersona {
  name: string;
  role: string;
  company: string;
  background: string;
}

export interface DemoClip {
  id: string;
  label: string;
  line: string;
  audio_b64: string;
}

export interface DemoScenario {
  persona: DemoPersona;
  voice: string;
  language: DemoLanguage;
  opening: DemoClip;
  objections: DemoClip[];
}

export interface DemoScenarioRequest {
  offer: string;
  niche: string;
  company: string | null;
  prospect_name: string | null;
  language: DemoLanguage;
}

export interface DemoReply {
  line: string;
  audio_b64: string;
}

export const demoBuyerApi = {
  createScenario: (body: DemoScenarioRequest) => api.post<DemoScenario>("/demo/scenario", body),
  reply: (scenario: DemoScenario, history: DemoTurn[], sellerText: string) =>
    api.post<DemoReply>("/demo/reply", {
      persona: scenario.persona,
      language: scenario.language,
      voice: scenario.voice,
      history,
      seller_text: sellerText,
    }),
};
