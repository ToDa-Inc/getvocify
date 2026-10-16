import { api } from "@/shared/lib/api-client";
import type { DemoTurn } from "@/lib/demo-session";

export type DemoLanguage = "es" | "en";

export interface DemoPersona {
  name: string;
  gender: "male" | "female";
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
  /** False when live help could not be set to answer as the demoed company (the migration is missing). */
  profile_saved?: boolean;
  profile_error?: string;
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
  /** The company being demoed, as read from its website: live help answers as it. */
  seller_company: string | null;
  knowledge: DemoKnowledge | null;
  facts: string[];
  language: DemoLanguage;
}

export interface DemoReply {
  line: string;
  audio_b64: string;
}

export interface DemoKnowledge {
  value_short: string;
  differentiators: string[];
  proofs: { customer: string; change: string }[];
}

export interface DemoUrlAnalysis {
  company: string;
  offer: string;
  /** Who the company sells to. */
  buyer: string;
  knowledge: DemoKnowledge;
  facts: string[];
}

export const demoBuyerApi = {
  analyzeUrl: (url: string) => api.post<DemoUrlAnalysis>("/demo/analyze-url", { url }),
  clearProfile: () => api.post<{ ok: boolean }>("/demo/profile/clear"),
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
