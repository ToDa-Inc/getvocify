/**
 * Sync targets for extension review/approve.
 *
 * The HubSpot page record is the write target. Stale IDs from a previous
 * record and auto-attached linked deals/contacts are not used.
 */

export function associatedContactsFromContext(ctx) {
  if (!ctx) return [];
  if (ctx.objectType === 'company' && Array.isArray(ctx.companyContacts)) {
    return ctx.companyContacts.filter(Boolean);
  }
  if (ctx.objectType === 'deal' && Array.isArray(ctx.dealContacts)) {
    return ctx.dealContacts.filter(Boolean);
  }
  return [];
}

export function needsAssociatedContactPick(ctx, contactId) {
  return associatedContactsFromContext(ctx).length > 1 && !contactId;
}

function contactIdForAssociatedRecord(ctx, userContactId) {
  if (userContactId) return userContactId;
  const list = associatedContactsFromContext(ctx);
  if (list.length > 1) return null;
  if (list.length === 1) return list[0].contact_id || ctx.contactId || null;
  return ctx.contactId || null;
}

export function formatSyncTargetLabel({
  contactName = null,
  dealName = null,
  skipDeal = false,
  needsContactPick = false,
} = {}) {
  if (needsContactPick) return 'Pick a contact first';
  const contact = contactName ? String(contactName).trim() : '';
  const deal = dealName ? String(dealName).trim() : '';
  if (skipDeal && contact) return contact;
  if (deal && contact) return `${deal} · ${contact}`;
  return deal || contact || null;
}

export function resolveReviewTargets({
  pageContext = null,
  userDealId = null,
  userContactId = null,
  createNewDeal = false,
} = {}) {
  const ctx = pageContext || {};
  const type = ctx.objectType;
  const recordId = ctx.recordId || null;

  if (type === 'contact' && recordId) {
    const dealId = createNewDeal ? null : (userDealId || null);
    return {
      dealId,
      contactId: recordId,
      companyId: ctx.companyId || null,
      skipDeal: !dealId && !createNewDeal,
    };
  }

  if (type === 'deal' && recordId) {
    const dealId = createNewDeal ? null : (userDealId || recordId);
    const contactId = dealId === recordId
      ? contactIdForAssociatedRecord(ctx, userContactId)
      : (userContactId || null);
    return {
      dealId,
      contactId,
      companyId: dealId === recordId ? (ctx.companyId || null) : null,
      skipDeal: false,
    };
  }

  if (type === 'company' && recordId) {
    const contactId = contactIdForAssociatedRecord(ctx, userContactId);
    const dealId = createNewDeal ? null : (userDealId || null);
    return {
      dealId,
      contactId,
      companyId: recordId,
      skipDeal: !dealId && !createNewDeal,
    };
  }

  const dealId = createNewDeal ? null : (userDealId || null);
  const contactId = userContactId || null;
  return {
    dealId,
    contactId,
    companyId: ctx.companyId || null,
    skipDeal: !dealId && !createNewDeal && !!contactId,
  };
}

export function bindPreviewIds({
  requestedDealId = null,
  requestedContactId = null,
  preview = null,
  adoptPreviewContact = true,
} = {}) {
  const previewContact = preview?.selected_contact?.contact_id || null;
  const previewCompany = preview?.selected_contact?.company_id || null;
  const contactId = requestedContactId || (adoptPreviewContact ? previewContact : null);
  return {
    dealId: requestedDealId || null,
    contactId,
    companyId: previewCompany || null,
  };
}

export function pickContextTab(tabs, { lastActiveTabId = null } = {}) {
  const list = Array.isArray(tabs) ? tabs.filter((t) => t && t.id != null) : [];
  if (!list.length) return null;
  if (lastActiveTabId != null) {
    const last = list.find((t) => t.id === lastActiveTabId);
    if (last) return last;
  }
  const activeHubSpot = list.find(
    (t) => t.active && t.url && /hubspot\.com/i.test(String(t.url))
  );
  if (activeHubSpot) return activeHubSpot;
  return list.find((t) => t.active) || null;
}
