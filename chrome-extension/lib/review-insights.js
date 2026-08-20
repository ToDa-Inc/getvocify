/**
 * What Review & sync should show vs hide.
 * Note + tasks are the copilot. CRM identity noise and unchanged email/phone
 * do not earn space.
 */

import { isInsightsField } from './extraction-omit.js';

export const TRANSCRIPT_DETAILS_OPEN_DEFAULT = false;

const IDENTITY_NOISE = new Set([
  'contact_name',
  'company_name',
  'dealname',
  'email',
  'phone',
  'firstname',
  'lastname',
]);

function norm(value) {
  return String(value ?? '').trim();
}

export function isIdentityNoiseField(update) {
  const name = String(update?.field_name || '');
  return IDENTITY_NOISE.has(name);
}

function valuesMatch(update) {
  const a = norm(update?.current_value);
  const b = norm(update?.new_value);
  if (!a || a === '(empty)') return false;
  if (String(update?.field_name || '').toLowerCase() === 'email') {
    return a.toLowerCase() === b.toLowerCase();
  }
  return a === b;
}

export function visibleCrmUpdates(updates) {
  const list = Array.isArray(updates) ? updates : [];
  return list.filter((u) => {
    if (!u || !u.field_name) return false;
    if (isIdentityNoiseField(u)) return false;
    if (isInsightsField(u.field_name)) return false;
    if (u.object_type === 'task') return false;
    if (!norm(u.new_value) && !u.userAdded) return false;
    if (valuesMatch(u)) return false;
    return true;
  });
}

export function crmUpdatesSummaryCount(updates) {
  return visibleCrmUpdates(updates).length;
}

const OBJECT_KICKERS = {
  contacts: 'Contact',
  companies: 'Company',
  deals: 'Deal',
};

export function crmFieldDisplayLabel(update) {
  const label = String(update?.field_label || '').trim();
  if (label) return label;
  return String(update?.field_name || '').trim();
}

function optionLabel(options, value) {
  const v = String(value ?? '');
  const hit = (Array.isArray(options) ? options : []).find((o) => String(o?.value ?? '') === v);
  if (!hit) return v;
  return String(hit.label || hit.value || v);
}

export function crmFieldValueLabel(update) {
  if (Array.isArray(update?.options) && update.options.length) {
    return optionLabel(update.options, update.new_value) || '—';
  }
  return norm(update?.new_value) || '—';
}

export function crmFieldWasLabel(update) {
  const current = update?.current_value;
  if (!norm(current) || norm(current) === '(empty)') return '';
  if (Array.isArray(update?.options) && update.options.length) {
    return optionLabel(update.options, current);
  }
  return norm(current);
}

export function crmFieldTone(update) {
  return crmFieldWasLabel(update) ? 'override' : 'new';
}

export function crmFieldInputKind(update) {
  if (Array.isArray(update?.options) && update.options.length) return 'select';
  const t = String(update?.field_type || '').toLowerCase();
  if (t === 'number' || t === 'currency') return 'number';
  if (t === 'date' || t === 'datetime') return 'date';
  const n = String(update?.field_name || '').toLowerCase();
  if (n.includes('closedate') || n === 'closed_date') return 'date';
  return 'text';
}

export function crmFieldGroups(updates) {
  const list = Array.isArray(updates) ? updates.filter(Boolean) : [];
  const types = [...new Set(list.map((u) => u.object_type || 'deals'))];
  if (types.length <= 1) {
    return [{ objectType: types[0] || null, label: null, updates: list }];
  }
  const groups = [];
  for (const update of list) {
    const objectType = update.object_type || 'deals';
    const last = groups[groups.length - 1];
    if (last && last.objectType === objectType) {
      last.updates.push(update);
      continue;
    }
    groups.push({
      objectType,
      label: OBJECT_KICKERS[objectType] || objectType,
      updates: [update],
    });
  }
  return groups;
}

export function addFieldOptionLabel(field, { mixedObjects = false } = {}) {
  const name = String(field?.label || field?.name || '').trim();
  if (!mixedObjects) return name;
  const objectType = field?.object_type || 'deals';
  return `${OBJECT_KICKERS[objectType] || objectType} · ${name}`;
}

export function shouldShowCrmFieldsSection({ updates = [], availableCount = 0 } = {}) {
  if (Number(availableCount) > 0) return true;
  return visibleCrmUpdates(updates).length > 0;
}

function isoDateOrNull(value) {
  const raw = String(value || '').trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10);
  return null;
}

export function taskRowsFromPreview({
  proposedUpdates = [],
  nextSteps = null,
  nextStepSchedules = [],
  dueDatesByIndex = [],
} = {}) {
  const previewTasks = (Array.isArray(proposedUpdates) ? proposedUpdates : [])
    .filter((u) => u && String(u.field_name || '').startsWith('next_step_task_'));
  const dueForIndex = (i) => isoDateOrNull(
    dueDatesByIndex[i]
    || previewTasks[i]?.due_date
    || nextStepSchedules[i],
  );

  const steps = Array.isArray(nextSteps)
    ? nextSteps.map((s) => String(s || '').trim()).filter(Boolean)
    : [];
  if (steps.length) {
    return steps.map((text, i) => ({
      id: i + 1,
      text: String(previewTasks[i]?.new_value || text).trim(),
      checked: true,
      dueDate: dueForIndex(i) || null,
    }));
  }
  return previewTasks
    .map((u, i) => ({
      id: i + 1,
      text: String(u.new_value || '').trim(),
      checked: true,
      dueDate: dueForIndex(i) || null,
    }))
    .filter((row) => row.text);
}

export function formatTaskDueLabel(isoDate, { today = '' } = {}) {
  const day = isoDateOrNull(isoDate);
  if (!day) return '';
  const todayIso = isoDateOrNull(today);
  if (todayIso && day === todayIso) return 'Today';
  const d = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return '';
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });
  const dateNum = d.getUTCDate();
  return `${weekday} ${dateNum}`;
}

export function shouldCreateHubSpotNote({ summary = '', transcript = '' } = {}) {
  return Boolean(norm(summary) || norm(transcript));
}
