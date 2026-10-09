/**
 * The contact a detected call is with, for the Mac notch island.
 *
 * The island reads the CRM page on screen; POST /live-calls/preview turns it
 * into the contact. No `@/` imports: this file runs under node --test.
 */

export interface CallPreview {
  provider: "hubspot" | "pipedrive" | null;
  contact_id: string | null;
  contact_name: string | null;
  needs_contact: boolean;
  /** The CRM record on screen, when it is one (null for lists and other accounts). */
  record?: { provider: string; object_type: "contact" | "company" | "deal"; record_id: string; account_id: string | null } | null;
  /** Who the record can be called at (CRMs Vocify can call; HubSpot today). */
  callee?: { contact_id: string; name: string | null; phone: string | null } | null;
  contacts_count?: number;
}

/** `shell:state` callContact: the name to show, or null to keep the app name. */
export function islandCallContact(preview: CallPreview | null | undefined): { name: string } | null {
  const name = preview?.contact_id ? preview.contact_name?.trim() : "";
  return name ? { name } : null;
}

/**
 * Keeps only the answer to the latest call: an older lookup that resolves
 * after a newer one must not overwrite it.
 */
export function latestOnly() {
  let latest = 0;
  return {
    next(): number {
      latest += 1;
      return latest;
    },
    isLatest(ticket: number): boolean {
      return ticket === latest;
    },
  };
}
