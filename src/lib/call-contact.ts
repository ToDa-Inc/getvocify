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
  record?: { provider: string; object_type: "contact" | "company" | "deal" | "lead"; record_id: string; account_id: string | null } | null;
  /** Who the record can be called at (CRMs Vocify can call: HubSpot and Pipedrive). */
  callee?: { contact_id: string; name: string | null; phone: string | null } | null;
  contacts_count?: number;
}

/** `shell:state` callContact: the name to show, or null to keep the app name. */
export function islandCallContact(preview: CallPreview | null | undefined): { name: string } | null {
  const name = preview?.contact_id ? preview.contact_name?.trim() : "";
  return name ? { name } : null;
}

/**
 * The contact a recording started from the island's Record takes: the one of the detected call, else the CRM
 * contact the island offers on screen (HubSpot contact or Pipedrive person; memos keep either id in the same column,
 * the account's one connected CRM says which). A record with several contacts has none.
 */
export function islandRecordContact(
  detected: { hubspotId: string; name: string | null } | null,
  onScreen: CallPreview | null,
): { hubspotId: string; name: string | null } | null {
  if (detected) return detected;
  const callee = onScreen?.provider === "hubspot" || onScreen?.provider === "pipedrive" ? onScreen.callee : null;
  return callee?.contact_id ? { hubspotId: callee.contact_id, name: callee.name?.trim() || null } : null;
}

/**
 * The deal or company open on screen when a recording starts: the call is saved there (and on its contact).
 * HubSpot and Pipedrive record ids only; anything else (a list, a lead, another account) gives none.
 */
export function onScreenRecord(onScreen: CallPreview | null | undefined): { dealId?: string; companyId?: string } | undefined {
  const record = onScreen?.record;
  if (!record || (record.provider !== "hubspot" && record.provider !== "pipedrive") || !/^\d{1,32}$/.test(record.record_id)) return undefined;
  if (record.object_type === "deal") return { dealId: record.record_id };
  if (record.object_type === "company") return { companyId: record.record_id };
  return undefined;
}

/**
 * The contact a detected call (Mac app + CRM page) is with, for the recording that follows. HubSpot contact or
 * Pipedrive person: the memo keeps either id in the same column.
 */
export function detectedCallContact(preview: CallPreview): { hubspotId: string; name: string | null } | null {
  const crm = preview.provider === "hubspot" || preview.provider === "pipedrive";
  return crm && preview.contact_id ? { hubspotId: preview.contact_id, name: preview.contact_name?.trim() || null } : null;
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
