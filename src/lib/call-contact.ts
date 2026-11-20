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
  if (!crm) return null;
  if (preview.contact_id) return { hubspotId: preview.contact_id, name: preview.contact_name?.trim() || null };
  // A deal or company page: the person it is called at (Pipedrive works by deal; the call is with the deal's person).
  const callee = preview.callee;
  return callee?.contact_id ? { hubspotId: callee.contact_id, name: callee.name?.trim() || null } : null;
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

/** When a call's CRM page lookup was asked: the recording count then, and the recording live then (if any). */
export interface LookupAsk {
  seq: number;
  draftId: string | null;
}

/**
 * Where the answer to a CRM page lookup goes, so a call's contact only ever reaches the recording it was asked for:
 * - "offer": asked while no recording ran, and none has started since: the call on offer (the next Record takes it);
 * - "draft": asked for the recording still live, or asked during an offer whose Record was pressed before the answer came;
 * - "drop": the recording it was for has ended, or more than one has started or ended since: it belongs to no call now.
 * `seq` counts every recording start and every recording end. Movertis, 2026-11-20: a contact left over from one call
 * reached the next recording, and a call with Marc Ferré was saved on Pilar Torrija's deal.
 */
export function lookupTarget(asked: LookupAsk, now: LookupAsk): "offer" | "draft" | "drop" {
  if (asked.draftId !== null) return now.draftId === asked.draftId ? "draft" : "drop";
  if (now.seq === asked.seq) return now.draftId === null ? "offer" : "draft";
  return now.seq === asked.seq + 1 && now.draftId !== null ? "draft" : "drop";
}
