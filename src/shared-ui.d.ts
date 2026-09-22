declare module "@shared/ui/brief.js" {
  export function visibleBrief(brief: { text?: string | null; lines?: { text?: string | null }[] }): string[];
  export function briefForContact(contactId: string | null, cached: { contactId: string; brief: unknown } | null): unknown;
  export function briefOnContact(input: { objectType?: string; captureActive?: boolean; brief?: { text?: string | null; lines?: { text?: string | null }[] } | null }): string[];
  export function briefRequest(contactId: string, connectionId?: string): string;
}

declare module "@shared/ui/compose.js" {
  export type ComposeResult =
    | { ok: true; url: string }
    | { ok: false; reason: "no_email" | "no_phone" | "too_long"; fallback?: string };
  export function composeTarget(draft: {
    channel: "email" | "whatsapp";
    to?: string;
    phone?: string;
    subject?: string;
    body?: string;
    mailClient?: "default" | "gmail" | "outlook";
  }): ComposeResult;
}

declare namespace JSX {
  interface IntrinsicElements {
    "v-followup": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
  }
}
