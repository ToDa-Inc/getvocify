/**
 * Sync targets for extension review/approve.
 *
 * Write the current process (memo + explicit picks). The HubSpot table is a
 * view of that process. A later focused contact/deal does not become the
 * write target unless the user clicks “Use this record”.
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
  processDealId = null,
  processContactId = null,
} = {}) {
  const ctx = pageContext || {};
  const type = ctx.objectType;
  const recordId = ctx.recordId || null;

  if (type === 'contact' && recordId) {
    const dealId = createNewDeal ? null : (userDealId || processDealId || null);
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
      ? contactIdForAssociatedRecord(ctx, userContactId || processContactId)
      : (userContactId || processContactId || null);
    return {
      dealId,
      contactId,
      companyId: dealId === recordId ? (ctx.companyId || null) : null,
      skipDeal: false,
    };
  }

  if (type === 'company' && recordId) {
    const contactId = contactIdForAssociatedRecord(ctx, userContactId || processContactId);
    const dealId = createNewDeal ? null : (userDealId || processDealId || null);
    return {
      dealId,
      contactId,
      companyId: recordId,
      skipDeal: !dealId && !createNewDeal,
    };
  }

  const dealId = createNewDeal ? null : (userDealId || processDealId || null);
  const contactId = userContactId || processContactId || null;
  return {
    dealId,
    contactId,
    companyId: ctx.companyId || null,
    skipDeal: !dealId && !createNewDeal && !!contactId,
  };
}

/**
 * Never keep a matcher-selected deal from another HubSpot record.
 * Page deal / explicit pick only. Closing a deal or opening a contact
 * drops selected_deal so field updates cannot show the previous deal.
 */
export function bindPreviewToPage({
  preview = null,
  requestedDealId = null,
  requestedContactId = null,
  createNewDeal = false,
  pageType = null,
} = {}) {
  const base = preview && typeof preview === 'object' ? { ...preview } : {};
  if (requestedDealId) {
    const selectedId = base.selected_deal?.deal_id;
    if (selectedId && String(selectedId) !== String(requestedDealId)) {
      base.selected_deal = null;
    }
    base.skip_deal = false;
    base.is_new_deal = false;
    return base;
  }
  if (createNewDeal) {
    return { ...base, selected_deal: null, is_new_deal: true, skip_deal: false };
  }
  const contactScoped =
    !!requestedContactId || pageType === 'contact' || pageType === 'company' || !pageType;
  if (contactScoped) {
    return { ...base, selected_deal: null, skip_deal: true, is_new_deal: false };
  }
  return { ...base, selected_deal: null, skip_deal: true, is_new_deal: false };
}

export function proposedUpdatesForPage(preview) {
  const updates = Array.isArray(preview?.proposed_updates) ? preview.proposed_updates : [];
  if (preview?.skip_deal && !preview?.selected_deal) {
    return updates.filter((u) => (u?.object_type || 'deals') !== 'deals');
  }
  return updates;
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
