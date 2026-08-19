import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  visibleCrmUpdates,
  formatTaskDueLabel,
  shouldCreateHubSpotNote,
  taskRowsFromPreview,
  TRANSCRIPT_DETAILS_OPEN_DEFAULT,
  crmFieldDisplayLabel,
  crmFieldValueLabel,
  crmFieldWasLabel,
  crmFieldInputKind,
  crmFieldGroups,
  addFieldOptionLabel,
  shouldShowCrmFieldsSection,
  crmFieldTone,
} from './review-insights.js';

describe('visibleCrmUpdates', () => {
  it('hides email/phone and leaves a real job title change', () => {
    const out = visibleCrmUpdates([
      { object_type: 'contacts', field_name: 'email', new_value: 'a@b.com', current_value: 'a@b.com' },
      { object_type: 'contacts', field_name: 'phone', new_value: '+34', current_value: '+34' },
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired', current_value: 'Sales Director' },
      { object_type: 'task', field_name: 'next_step_task_0', new_value: 'Follow up' },
    ]);
    assert.equal(out.length, 1);
    assert.equal(out[0].field_name, 'jobtitle');
  });

  it('returns empty when the call only had a note and tasks', () => {
    assert.equal(visibleCrmUpdates([]).length, 0);
  });
});

describe('crm field rows', () => {
  it('uses the HubSpot field name only — no object stamp, no extra fetch', () => {
    assert.equal(
      crmFieldDisplayLabel({
        object_type: 'contacts',
        field_name: 'jobtitle',
        field_label: 'Job title',
      }),
      'Job title',
    );
    assert.equal(
      crmFieldDisplayLabel({ object_type: 'contacts', field_name: 'jobtitle' }),
      'jobtitle',
    );
  });

  it('shows the option label for enum values, not the internal id', () => {
    const update = {
      field_name: 'hs_lead_status',
      field_label: 'Lead status',
      new_value: 'UNQUALIFIED',
      current_value: 'NEW',
      options: [
        { value: 'NEW', label: 'New' },
        { value: 'UNQUALIFIED', label: 'Unqualified' },
      ],
    };
    assert.equal(crmFieldValueLabel(update), 'Unqualified');
    assert.equal(crmFieldWasLabel(update), 'New');
    assert.equal(crmFieldInputKind(update), 'select');
  });

  it('hides Was when HubSpot had nothing; uses date/text inputs from the field itself', () => {
    assert.equal(
      crmFieldWasLabel({ field_name: 'jobtitle', new_value: 'Retired', current_value: '(empty)' }),
      '',
    );
    assert.equal(
      crmFieldInputKind({ field_name: 'closedate', field_type: 'date', new_value: '2026-09-01' }),
      'date',
    );
    assert.equal(
      crmFieldInputKind({ field_name: 'jobtitle', field_type: 'string', new_value: 'Retired' }),
      'text',
    );
    assert.equal(
      crmFieldTone({ field_name: 'jobtitle', new_value: 'Retired', current_value: '(empty)' }),
      'new',
    );
    assert.equal(
      crmFieldTone({
        field_name: 'jobtitle',
        new_value: 'Retired',
        current_value: 'Sales Director',
      }),
      'override',
    );
  });

  it('does not promote deal stage/amount — groups only when objects are mixed', () => {
    const contactOnly = crmFieldGroups([
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired' },
      { object_type: 'contacts', field_name: 'lifecyclestage', field_label: 'Lifecycle stage', new_value: 'opportunity' },
    ]);
    assert.equal(contactOnly.length, 1);
    assert.equal(contactOnly[0].label, null);
    assert.deepEqual(contactOnly[0].updates.map((u) => u.field_name), ['jobtitle', 'lifecyclestage']);

    const mixed = crmFieldGroups([
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired' },
      { object_type: 'companies', field_name: 'industry', field_label: 'Industry', new_value: 'Chemicals' },
      { object_type: 'deals', field_name: 'amount', field_label: 'Amount', new_value: '12' },
    ]);
    assert.deepEqual(mixed.map((g) => g.label), ['Contact', 'Company', 'Deal']);
    assert.equal(mixed[2].updates[0].field_name, 'amount');
  });

  it('labels Add field with just the name unless objects are mixed', () => {
    const field = { name: 'jobtitle', label: 'Job title', object_type: 'contacts' };
    assert.equal(addFieldOptionLabel(field, { mixedObjects: false }), 'Job title');
    assert.equal(addFieldOptionLabel(field, { mixedObjects: true }), 'Contact · Job title');
  });

  it('keeps the Fields section when there is nothing proposed but fields can still be added', () => {
    assert.equal(shouldShowCrmFieldsSection({ updates: [], availableCount: 4 }), true);
    assert.equal(shouldShowCrmFieldsSection({ updates: [], availableCount: 0 }), false);
    assert.equal(
      shouldShowCrmFieldsSection({
        updates: [{ field_name: 'jobtitle', new_value: 'Retired' }],
        availableCount: 0,
      }),
      true,
    );
  });

  it('keeps a field the user just added so they can fill it', () => {
    const out = visibleCrmUpdates([
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: '', userAdded: true },
    ]);
    assert.equal(out.length, 1);
  });
});

describe('tasks and note', () => {
  it('pairs nextSteps with schedule ISO dates', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Follow up with ops', 'Send one-pager'],
      nextStepSchedules: ['2026-08-20', ''],
    });
    assert.equal(rows[0].dueDate, '2026-08-20');
    assert.equal(rows[1].dueDate, null);
    assert.equal(rows[0].checked, true);
  });

  it('uses the preview due date when the LLM schedule is a spoken phrase', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Contactar a Aritzel Expuru'],
      nextStepSchedules: ['martes 18:00'],
      proposedUpdates: [
        {
          object_type: 'task',
          field_name: 'next_step_task_0',
          new_value: 'Contactar a Aritzel Expuru',
          due_date: '2026-08-20',
        },
      ],
    });
    assert.equal(rows[0].dueDate, '2026-08-20');
    assert.equal(rows[0].text, 'Contactar a Aritzel Expuru');
  });

  it('does not invent a date when the LLM did not detect one', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Send one-pager'],
      nextStepSchedules: [''],
      proposedUpdates: [
        { object_type: 'task', field_name: 'next_step_task_0', new_value: 'Send one-pager' },
      ],
    });
    assert.equal(rows[0].dueDate, null);
  });

  it('formats a due date as a short weekday chip', () => {
    assert.equal(
      formatTaskDueLabel('2026-08-20', { today: '2026-08-18' }),
      'Thu 20',
    );
  });

  it('always creates a note when there is a summary', () => {
    assert.equal(shouldCreateHubSpotNote({ summary: 'Retired.', transcript: '' }), true);
    assert.equal(shouldCreateHubSpotNote({ summary: '', transcript: '' }), false);
  });

  it('keeps the transcript collapsed by default', () => {
    assert.equal(TRANSCRIPT_DETAILS_OPEN_DEFAULT, false);
  });
});
