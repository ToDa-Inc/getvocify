import type { PublishState } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Class strings the playbook screens share, so the quiet actions look the same everywhere. */

/** "+ Paso", "+ Tipo de llamada", "Añadir desde un documento": a text action, not a button. */
export const linkButton =
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground";

/** The colour of a call type's state word, the same in the list and in its header. */
export const PUBLISH_TONE: Record<PublishState, string> = {
  live: "text-success",
  changes: "text-beige",
  unpublished: "text-beige",
  paused: "text-muted-foreground",
  empty: "text-muted-foreground",
};

/** An item's bold name and its one line (DocRow), as editable fields or as text. */
export const itemTitle = `${THEME_TOKENS.typography.itemTitle} py-0.5`;
export const itemBody = `${THEME_TOKENS.typography.itemBody} py-0.5`;
