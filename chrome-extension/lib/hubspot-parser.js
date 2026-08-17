/**
 * HubSpot URL Parser
 * 
 * Extracts context from HubSpot URLs to enable auto-association of memos with deals/contacts.
 * 
 * Example URLs:
 * - https://app-eu1.hubspot.com/contacts/147506535/record/0-3/420466980027
 * - https://app.hubspot.com/contacts/123456/record/0-1/789012
 */

/**
 * Parse HubSpot URL to extract context
 * 
 * @param {string} url - The HubSpot URL
 * @returns {Object|null} Parsed context or null if not a HubSpot URL
 */
const OBJECT_TYPES = {
  '0-1': 'contact',
  '0-2': 'company',
  '0-3': 'deal',
};

const LEGACY_PATH_TYPES = {
  contact: { objectTypeId: '0-1', objectType: 'contact' },
  company: { objectTypeId: '0-2', objectType: 'company' },
  deal: { objectTypeId: '0-3', objectType: 'deal' },
};

function parseRegion(hostMatch) {
  return hostMatch || 'na1';
}

export function parseHubSpotUrl(url) {
  if (!url || typeof url !== 'string') {
    return null;
  }

  // Current CRM record URL:
  // https://app-eu1.hubspot.com/contacts/{hubId}/record/0-1/{recordId}/
  const recordMatch = url.match(
    /app(?:-(\w+))?\.hubspot\.com\/contacts\/(\d+)\/record\/([\d-]+)\/(\d+)/
  );
  if (recordMatch) {
    const [, region, hubId, objectTypeId, recordId] = recordMatch;
    return {
      region: parseRegion(region),
      hubId,
      objectTypeId,
      objectType: OBJECT_TYPES[objectTypeId] || 'unknown',
      recordId,
    };
  }

  // Legacy CRM URLs: /contacts/{hubId}/contact/{recordId}
  const legacyMatch = url.match(
    /app(?:-(\w+))?\.hubspot\.com\/contacts\/(\d+)\/(contact|company|deal)\/(\d+)/
  );
  if (legacyMatch) {
    const [, region, hubId, pathType, recordId] = legacyMatch;
    const mapped = LEGACY_PATH_TYPES[pathType];
    return {
      region: parseRegion(region),
      hubId,
      objectTypeId: mapped.objectTypeId,
      objectType: mapped.objectType,
      recordId,
    };
  }

  return null;
}

/**
 * Build HubSpot deep link URL
 * 
 * @param {Object} params - URL parameters
 * @param {string} params.region - HubSpot region (eu1, na1, etc.)
 * @param {string} params.hubId - Portal ID
 * @param {string} params.objectTypeId - Object type ID (0-1, 0-2, 0-3)
 * @param {string} params.recordId - Record ID
 * @returns {string} Complete HubSpot URL
 */
export function buildHubSpotUrl({ region, hubId, objectTypeId, recordId }) {
  const regionPrefix = region && region !== 'na1' ? `-${region}` : '';
  return `https://app${regionPrefix}.hubspot.com/contacts/${hubId}/record/${objectTypeId}/${recordId}`;
}
