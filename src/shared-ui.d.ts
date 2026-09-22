declare module "@shared/ui/components/v-followup.js";

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
