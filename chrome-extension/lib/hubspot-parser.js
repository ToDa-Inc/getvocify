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
export function parseHubSpotUrl(url) {
  if (!url || typeof url !== 'string') {
    return null;
  }

  // Match HubSpot URL pattern
  // Groups: region (eu1/na1), hubId, objectTypeId (0-1, 0-2, 0-3), recordId
  const regex = /app(?:-(\w+))?\.hubspot\.com\/contacts\/(\d+)\/record\/([\d-]+)\/(\d+)/;
  const match = url.match(regex);

  if (!match) {
    return null;
  }

  const [, region, hubId, objectTypeId, recordId] = match;

  // Map object type IDs to names
  const objectTypes = {
    '0-1': 'contact',
    '0-2': 'company',
    '0-3': 'deal',
  };

  return {
    region: region || 'na1', // Default to na1 if no region specified
    hubId,
    objectTypeId,
    objectType: objectTypes[objectTypeId] || 'unknown',
    recordId,
  };
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
